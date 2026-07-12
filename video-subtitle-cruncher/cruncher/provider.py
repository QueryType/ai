"""OpenAI-compatible chat client for local vision runtimes.

Works against llama-server, LM Studio, and omlx — anything exposing
POST {base_url}/chat/completions with image content parts.
"""

import base64
import io
import os
from pathlib import Path

import httpx
from PIL import Image

DEFAULT_BASE_URL = os.environ.get("CRUNCH_BASE_URL", "http://localhost:8080/v1")
DEFAULT_MODEL = os.environ.get("CRUNCH_MODEL", "")


class ProviderError(RuntimeError):
    pass


def _to_data_url(image) -> str:
    if isinstance(image, (str, Path)):
        image = Image.open(image)
    if image.mode != "RGB":
        image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    b64 = base64.standard_b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


class VisionProvider:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL,
                 api_key: str = "local", timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.Client(
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def chat(self, messages: list[dict], max_tokens: int = 1024,
             temperature: float = 0.0) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            resp = self.client.post(f"{self.base_url}/chat/completions", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderError(f"vision endpoint failed ({self.base_url}): {e}") from e
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as e:
            raise ProviderError(f"unexpected response shape: {data}") from e

    def ask_image(self, image, prompt: str, max_tokens: int = 512) -> str:
        messages = [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": _to_data_url(image)}},
                {"type": "text", "text": prompt},
            ],
        }]
        return self.chat(messages, max_tokens=max_tokens)

    def ping(self) -> bool:
        """Cheap reachability check so we can fall back gracefully."""
        try:
            resp = self.client.get(f"{self.base_url}/models", timeout=5.0)
            return resp.status_code < 500
        except httpx.HTTPError:
            return False
