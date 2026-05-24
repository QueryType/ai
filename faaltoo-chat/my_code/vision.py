"""Vision probe and image description — adapted from game-master."""
from __future__ import annotations

import base64
import os
import struct
import zlib
from pathlib import Path

_MIME_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}

_DESCRIBE_PROMPT = (
    "The image represents: {label}.\n\n"
    "Describe what you see in 1-2 natural sentences, as if you're telling a friend about it. "
    "Be casual and direct. Don't say 'the image shows'."
)


def _red_png(size: int = 64) -> str:
    def chunk(name: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    row = b"\x00" + b"\xff\x00\x00" * size
    idat = chunk(b"IDAT", zlib.compress(row * size))
    iend = chunk(b"IEND", b"")
    return base64.b64encode(sig + ihdr + idat + iend).decode()


def probe_vision(base_url: str, model_id: str, api_key: str) -> bool:
    override = os.environ.get("FAALTOO_VISION_CAPABLE", "").strip().lower()
    if override == "true":
        return True
    if override == "false":
        return False

    try:
        from openai import OpenAI

        client = OpenAI(base_url=base_url, api_key=api_key, timeout=15.0)
        b64 = _red_png()
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What color is this image? One word."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }
            ],
            max_tokens=10,
        )
        content = (resp.choices[0].message.content or "").strip() if resp.choices else ""
        return len(content) > 0
    except Exception:
        return False


def describe_image(
    image_path: str,
    label: str,
    base_url: str,
    model_id: str,
    api_key: str,
) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    ext = path.suffix.lower().lstrip(".")
    mime = _MIME_MAP.get(ext, "image/jpeg")
    b64 = base64.b64encode(path.read_bytes()).decode()

    try:
        from openai import OpenAI

        client = OpenAI(base_url=base_url, api_key=api_key, timeout=30.0)
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _DESCRIBE_PROMPT.format(label=label)},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                }
            ],
            max_tokens=150,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        raise RuntimeError(f"Vision description failed: {exc}") from exc
