"""Vision capability probe — checks whether the loaded model accepts image inputs.

Env override: STORY_ENGINE_VISION_CAPABLE=true|false skips the probe entirely.
Otherwise sends a 1×1 red pixel PNG and checks for a non-error response.
"""

from __future__ import annotations

import base64
import os
import struct
import zlib


def _red_png(size: int = 64) -> str:
    """Build a solid red size×size PNG from stdlib only, return as base64.

    64×64 is the minimum that works reliably across vision models — some
    implementations crash on sub-pixel or very small images.
    """

    def chunk(name: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    # Each row: filter_byte=0 then size × RGB(255, 0, 0)
    row = b"\x00" + b"\xff\x00\x00" * size
    idat = chunk(b"IDAT", zlib.compress(row * size))
    iend = chunk(b"IEND", b"")
    return base64.b64encode(sig + ihdr + idat + iend).decode()


def probe_vision(base_url: str, model_id: str, api_key: str) -> bool:
    """Return True if the model at base_url accepts image inputs.

    Checks STORY_ENGINE_VISION_CAPABLE env var first (true/false override).
    Falls back to a live probe: sends a 1×1 PNG and expects any valid response.
    On any error (HTTP 400, unsupported media, timeout) returns False.
    """
    override = os.environ.get("STORY_ENGINE_VISION_CAPABLE", "").strip().lower()
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
                        {"type": "text", "text": "What color is this image? Answer in one word."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
            max_tokens=20,
        )
        content = (resp.choices[0].message.content or "").strip() if resp.choices else ""
        return len(content) > 0
    except Exception:
        return False
