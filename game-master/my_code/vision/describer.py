"""Image description — converts an image file to narrative prose via the vision model.

The description is generated once and the image bytes are discarded. Only the
returned text string is used downstream.
"""

from __future__ import annotations

import base64
from pathlib import Path

_MIME_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}

_DESCRIBE_PROMPT = (
    "You are a narrator for a text adventure game. "
    "The image provided represents: {label}.\n\n"
    "Describe it in 2–3 vivid sentences suitable for fantasy prose. "
    "Focus on atmosphere, key visual elements, colours, and mood. "
    "Write as prose — do not list items, do not say 'the image shows', "
    "do not break the fourth wall."
)


def describe_image(
    image_path: str,
    label: str,
    base_url: str,
    model_id: str,
    api_key: str,
) -> str:
    """Describe an image file as atmospheric prose for use in a text adventure.

    Args:
        image_path: Filesystem path to the image.
        label:      Player-supplied context (e.g. "a tattered map found in the ruins").
        base_url:   OpenAI-compat API base URL.
        model_id:   Model identifier.
        api_key:    API key (may be a placeholder for local servers).

    Returns:
        A 2–3 sentence prose description.

    Raises:
        FileNotFoundError: If image_path does not exist.
        RuntimeError:      If the API call fails.
    """
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
                        {
                            "type": "text",
                            "text": _DESCRIBE_PROMPT.format(label=label),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ],
                }
            ],
            max_tokens=250,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        raise RuntimeError(f"Vision description failed: {exc}") from exc
