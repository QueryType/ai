import os
from dotenv import load_dotenv
load_dotenv()
os.environ["HF_XET_HIGH_PERFORMANCE"] = "1"
import json
import math
import tempfile
import urllib.request
import urllib.error
import torch
import numpy as np
import soundfile as sf
import librosa
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
import transformers
transformers.logging.set_verbosity_error()
from transformers import WhisperProcessor, WhisperForConditionalGeneration

MODEL_ID  = os.getenv("MODEL_ID",      "Trelis/whisper-hinglish-preview")
LLM_BASE  = os.getenv("LLM_BASE_URL",  "http://192.168.1.2:7890")
LLM_MODEL = os.getenv("LLM_MODEL",     "google/gemma-4-26b-a4b-qat")

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
DTYPE  = torch.float16 if DEVICE == "mps" else torch.float32

CHUNK_SAMPLES  = 20 * 16000
STRIDE_SAMPLES = 0

app = Flask(__name__, static_folder="static")

processor = None
model     = None


def get_model():
    global processor, model
    if model is None:
        print(f"Loading model on {DEVICE} ({DTYPE})...")
        processor = WhisperProcessor.from_pretrained(MODEL_ID)
        model = WhisperForConditionalGeneration.from_pretrained(
            MODEL_ID, torch_dtype=DTYPE
        ).to(DEVICE).eval()
        print("Model ready.")
    return processor, model


def load_audio(path):
    audio, sr = sf.read(path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != 16000:
        audio = librosa.resample(audio.astype(np.float32), orig_sr=sr, target_sr=16000)
    return audio.astype(np.float32)


def parse_timestamp_segments(token_ids, tokenizer, prompt_len, time_offset):
    timestamp_begin = tokenizer.convert_tokens_to_ids("<|0.00|>")
    generated = token_ids[prompt_len:]
    segments, seg_start, text_ids = [], None, []
    for tid in generated:
        if tid == tokenizer.eos_token_id:
            break
        if tid >= timestamp_begin:
            t = round((tid - timestamp_begin) * 0.02 + time_offset, 2)
            if seg_start is None:
                seg_start = t
            else:
                text = tokenizer.decode(text_ids, skip_special_tokens=True).strip()
                if text:
                    segments.append({"start": seg_start, "end": t, "text": text})
                seg_start, text_ids = t, []
        else:
            if seg_start is not None:
                text_ids.append(tid)
    if seg_start is not None and text_ids:
        text = tokenizer.decode(text_ids, skip_special_tokens=True).strip()
        if text:
            segments.append({"start": seg_start, "end": round(seg_start + 2.0, 2), "text": text})
    return segments


def make_segments_approx(text, chunk_start, chunk_end):
    text = text.strip()
    if not text:
        return []
    return [{"start": round(chunk_start, 2), "end": round(chunk_end, 2), "text": text}]


def _sse(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def free_device_cache():
    if DEVICE == "mps":
        torch.mps.empty_cache()
    elif DEVICE == "cuda":
        torch.cuda.empty_cache()


def stream_transcription(audio_path, lang, mixed, sync):
    try:
        proc, mdl = get_model()
        audio = load_audio(audio_path)

        tok = proc.tokenizer
        ids = lambda t: tok.convert_tokens_to_ids(t)
        notimestamps_id = ids("<|notimestamps|>")

        base_prompt = [ids("<|startoftranscript|>"), ids(f"<|{lang}|>")]
        if mixed:
            base_prompt.extend(tok("<|mixedcode|>", add_special_tokens=False).input_ids)
        base_prompt.append(ids("<|transcribe|>"))

        prompt = base_prompt if sync else base_prompt + [notimestamps_id]
        decoder_ids = torch.tensor([prompt], device=DEVICE)
        max_new_tokens = 448 - decoder_ids.shape[1]

        step  = CHUNK_SAMPLES - STRIDE_SAMPLES
        total = math.ceil(len(audio) / step)

        for i, start in enumerate(range(0, len(audio), step)):
            chunk    = audio[start: start + CHUNK_SAMPLES]
            features = proc.feature_extractor(
                chunk, sampling_rate=16000, return_tensors="pt"
            ).input_features.to(DEVICE, DTYPE)

            with torch.no_grad():
                out = mdl.generate(
                    input_features=features,
                    decoder_input_ids=decoder_ids,
                    max_new_tokens=max_new_tokens,
                    suppress_tokens=[notimestamps_id] if sync else None,
                )

            if sync:
                token_list = out[0].tolist()
                segments   = parse_timestamp_segments(token_list, tok, len(prompt), start / 16000)
                source     = "timestamps"
                if not segments:
                    text        = tok.decode(out[0], skip_special_tokens=True)
                    chunk_start = start / 16000
                    chunk_end   = min((start + CHUNK_SAMPLES) / 16000, len(audio) / 16000)
                    segments    = make_segments_approx(text, chunk_start, chunk_end)
                    source      = "approx"
                print(f"[chunk {i+1}/{total}] source={source} segments={len(segments)}")
                yield _sse({"chunk": i + 1, "total": total, "segments": segments})
            else:
                text = tok.decode(out[0], skip_special_tokens=True)
                yield _sse({"chunk": i + 1, "total": total, "text": text})

            del features, out  # release MPS activation memory between chunks

        yield _sse({"done": True})
    except Exception as e:
        yield _sse({"error": str(e)})
    finally:
        os.unlink(audio_path)
        free_device_cache()
        print("[memory] device cache cleared after transcription")


def _strip_code_fence(text):
    """Remove markdown code fences an LLM may wrap around JSON."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1 if lines[0].startswith("```") else 0
        end   = -1 if lines[-1].strip() == "```" else len(lines)
        text  = "\n".join(lines[start:end]).strip()
    return text


@app.route("/translate", methods=["POST"])
def translate_text():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    segments    = data.get("segments")   # list[{start,end,text}] or None
    plain_text  = data.get("text")       # str or None
    target_lang = data.get("target_lang", "English")
    source_lang = data.get("source_lang", "Hinglish")

    llm_url = LLM_BASE.rstrip("/") + "/v1/chat/completions"

    if segments is not None:
        user_msg = (
            f'Translate only the "text" field in each object from {source_lang} to {target_lang}. '
            f'Return a JSON array with the exact same structure. '
            f'Do not change "start" or "end" values. Return only the JSON array, no explanation.\n\n'
            + json.dumps(segments, ensure_ascii=False)
        )
    elif plain_text:
        user_msg = (
            f"Translate the following from {source_lang} to {target_lang}. "
            f"Return only the translated text, no explanation.\n\n{plain_text}"
        )
    else:
        return jsonify({"error": "Provide either segments or text"}), 400

    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": user_msg}],
        "temperature": 0.1,
    }, ensure_ascii=False).encode()

    try:
        req = urllib.request.Request(
            llm_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())

        content = result["choices"][0]["message"]["content"]

        if segments is not None:
            translated = json.loads(_strip_code_fence(content))
            # Always restore original timestamps — LLM must not change them
            for orig, tr in zip(segments, translated):
                tr["start"] = orig["start"]
                tr["end"]   = orig["end"]
            return jsonify({"segments": translated})
        else:
            return jsonify({"text": content.strip()})

    except urllib.error.URLError as e:
        return jsonify({"error": f"LLM unreachable: {e.reason}"}), 502
    except json.JSONDecodeError as e:
        return jsonify({"error": f"LLM returned invalid JSON: {e}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/transcribe", methods=["POST"])
def transcribe():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    f     = request.files["audio"]
    lang  = request.form.get("lang",  "hi")
    mixed = request.form.get("mixed", "true").lower() == "true"
    sync  = request.form.get("sync",  "true").lower() == "true"

    suffix = os.path.splitext(f.filename)[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    return Response(
        stream_with_context(stream_transcription(tmp_path, lang, mixed, sync)),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5050))
    print(f"Starting Hinglish Whisper server at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
