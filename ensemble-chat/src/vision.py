"""Vision: probe capability, save an attachment once, hydrate at request time.

The model must already be multimodal — no second vision-only model, no dual
endpoint. `Engine.history` only ever stores a lightweight file reference
(`{"type": "image_ref", "path": ...}`), never the raw bytes, so `session.json`
stays small regardless of how many images accumulate. Hydration builds the
outbound request payload fresh from that reference; it never rewrites
`Engine.history` — same append-only discipline as everything else, just
applied to what gets *sent*, not what's *stored*.

The image is downscaled once, at ingestion (`save_attachment`), so every
later hydration reads identical bytes and produces an identical base64
string — re-deriving a different encoding per read would defeat the
request-prefix stability the whole cache story depends on.
"""
from __future__ import annotations

import base64
import io
import struct
import uuid
import zlib
from pathlib import Path

from openai import AsyncOpenAI
from PIL import Image

_MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}


def synthetic_png(rgb: tuple[int, int, int], size: int = 32) -> bytes:
    """A tiny single-color PNG, built without any image library — real pixel
    content to ask a model about when a real photo isn't the point. Used by
    the capability probe below, and by the harness's `vision` suite."""

    def chunk(name: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    row = b"\x00" + bytes(rgb) * size
    idat = chunk(b"IDAT", zlib.compress(row * size))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


async def probe_vision(client: AsyncOpenAI, model: str) -> bool:
    """One request, cheap either way: a real answer means the model can see."""
    b64 = base64.b64encode(synthetic_png((255, 0, 0))).decode()
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "What color is this image? One word."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
            max_tokens=10,
        )
        return bool((resp.choices[0].message.content or "").strip())
    except Exception:
        return False


def save_attachment(data: bytes, dest_dir: Path, max_dimension: int) -> Path:
    """Downscale to a bounded longest edge and save once as JPEG.

    The bound is a context/latency budget, the same idea as `reply_max_tokens`
    — an un-downscaled photo would cost an unpredictable, possibly large
    number of tokens on every single future turn that includes it.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((max_dimension, max_dimension))
    path = dest_dir / f"{uuid.uuid4().hex}.jpg"
    img.save(path, format="JPEG", quality=85)
    return path


def image_ref(path: Path, dest_dir: Path) -> dict:
    return {"type": "image_ref", "path": path.relative_to(dest_dir).as_posix()}


def _hydrate_content(content, base_dir: Path):
    if isinstance(content, str):
        return content
    out = []
    for part in content:
        if part.get("type") == "image_ref":
            data = (base_dir / part["path"]).read_bytes()
            mime = _MIME.get(Path(part["path"]).suffix.lstrip(".").lower(), "image/jpeg")
            b64 = base64.b64encode(data).decode()
            out.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        else:
            out.append(part)
    return out


def hydrate(messages: list[dict], base_dir: Path) -> list[dict]:
    """Read-time transform for an outbound request. Returns a new list —
    never mutates `messages` or anything referenced inside it."""
    return [{**m, "content": _hydrate_content(m["content"], base_dir)} for m in messages]
