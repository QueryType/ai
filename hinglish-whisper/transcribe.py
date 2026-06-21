"""
Hinglish Whisper local inference — optimized for Apple Silicon (MPS).
Model: Trelis/whisper-hinglish-preview (whisper-large-v3 fine-tuned)

Usage:
    python transcribe.py audio.wav
    python transcribe.py audio.wav --lang hi          # force Hindi
    python transcribe.py audio.wav --lang en          # force English
    python transcribe.py audio.wav --mixed            # Hinglish code-switched
    python transcribe.py audio.wav --mixed --timestamps
"""

import os
from dotenv import load_dotenv
load_dotenv()
import sys
import math
import argparse
import torch
import soundfile as sf
import numpy as np
import librosa
from transformers import WhisperProcessor, WhisperForConditionalGeneration

MODEL_ID = os.getenv("MODEL_ID", "Trelis/whisper-hinglish-preview")

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
# MPS supports float16; bfloat16 has limited MPS support
DTYPE = torch.float16 if DEVICE == "mps" else torch.float32


def load_model():
    print(f"Loading model on {DEVICE} ({DTYPE})...")
    processor = WhisperProcessor.from_pretrained(MODEL_ID)
    model = WhisperForConditionalGeneration.from_pretrained(
        MODEL_ID,
        torch_dtype=DTYPE,
    ).to(DEVICE).eval()
    print("Model ready.")
    return processor, model


def load_audio(path: str) -> np.ndarray:
    audio, sr = sf.read(path)
    # Convert stereo to mono
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    # Resample to 16kHz if needed
    if sr != 16000:
        audio = librosa.resample(audio.astype(np.float32), orig_sr=sr, target_sr=16000)
    return audio.astype(np.float32)


def build_prompt(processor, lang: str, mixed: bool, timestamps: bool) -> list[int]:
    tok = processor.tokenizer
    ids = lambda t: tok.convert_tokens_to_ids(t)

    prompt = [ids("<|startoftranscript|>")]

    lang_token = f"<|{lang}|>"
    prompt.append(ids(lang_token))

    if mixed:
        mc_ids = tok("<|mixedcode|>", add_special_tokens=False).input_ids
        prompt.extend(mc_ids)

    prompt.append(ids("<|transcribe|>"))

    if not timestamps:
        prompt.append(ids("<|notimestamps|>"))

    return prompt


CHUNK_SAMPLES = 30 * 16000
STRIDE_SAMPLES = 2 * 16000


def transcribe(audio_path: str, lang: str = "hi", mixed: bool = True, timestamps: bool = False):
    processor, model = load_model()
    audio = load_audio(audio_path)

    prompt = build_prompt(processor, lang, mixed, timestamps)
    decoder_ids = torch.tensor([prompt], device=DEVICE)
    max_new_tokens = 448 - decoder_ids.shape[1]

    step = CHUNK_SAMPLES - STRIDE_SAMPLES
    total = math.ceil(len(audio) / step)
    parts = []
    for i, start in enumerate(range(0, len(audio), step)):
        print(f"[{i+1}/{total}] ", end="", flush=True)
        chunk = audio[start: start + CHUNK_SAMPLES]
        features = processor.feature_extractor(
            chunk, sampling_rate=16000, return_tensors="pt"
        ).input_features.to(DEVICE, DTYPE)
        with torch.no_grad():
            output_ids = model.generate(
                input_features=features,
                decoder_input_ids=decoder_ids,
                max_new_tokens=max_new_tokens,
            )
        text = processor.tokenizer.decode(output_ids[0], skip_special_tokens=not timestamps)
        print(text, flush=True)
        parts.append(text)

    return " ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Hinglish Whisper transcription")
    parser.add_argument("audio", help="Path to audio file (WAV, MP3, FLAC, etc.)")
    parser.add_argument("--lang", default="hi", choices=["hi", "en"],
                        help="Language token: hi (Hindi/Hinglish) or en (English). Default: hi")
    parser.add_argument("--mixed", action="store_true", default=True,
                        help="Insert <|mixedcode|> token for Hinglish code-switching (default: on)")
    parser.add_argument("--no-mixed", dest="mixed", action="store_false",
                        help="Disable the mixedcode token (pure Hindi or pure English)")
    parser.add_argument("--timestamps", action="store_true",
                        help="Include word/segment timestamps in output")
    args = parser.parse_args()

    result = transcribe(args.audio, lang=args.lang, mixed=args.mixed, timestamps=args.timestamps)
    print("\n--- Transcription ---")
    print(result)


if __name__ == "__main__":
    main()
