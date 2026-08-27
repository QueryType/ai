"""LLM call layer: OpenAI-compatible chat completions with retry, plus JSON extraction."""

from __future__ import annotations

import json
import re
import sys
import time

import requests

DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 2.0


def call_llm(
    llm_url: str,
    model: str,
    system: str,
    user: str,
    api_key: str = "not-needed",
    temperature: float = 0.7,
    retries: int = DEFAULT_RETRIES,
) -> str:
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                f"{llm_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temperature,
                },
                timeout=600,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except (requests.RequestException, KeyError, IndexError) as e:
            last_exc = e
            if attempt < retries:
                wait = DEFAULT_BACKOFF_SECONDS * (2 ** (attempt - 1))
                print(f"      LLM call failed (attempt {attempt}/{retries}): {e}. Retrying in {wait:.0f}s...", file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"LLM call failed after {retries} attempts: {last_exc}") from last_exc


def call_llm_json(
    llm_url: str,
    model: str,
    system: str,
    user: str,
    extractor,
    api_key: str = "not-needed",
    temperature: float = 0.7,
    json_retries: int = 2,
):
    """call_llm + a JSON extractor, retrying the whole LLM call (not just the
    parse) if the model returns malformed JSON -- a fresh sample usually
    fixes a one-off glitch like an unescaped quote or stray delimiter."""
    last_exc: Exception | None = None
    for attempt in range(1, json_retries + 2):
        raw = call_llm(llm_url, model, system, user, api_key=api_key, temperature=temperature)
        try:
            return extractor(raw)
        except (ValueError, KeyError) as e:
            last_exc = e
            if attempt <= json_retries:
                print(
                    f"      LLM returned unparseable JSON (attempt {attempt}/{json_retries + 1}): {e}. Retrying...",
                    file=sys.stderr,
                )
    raise ValueError(f"LLM returned unparseable JSON after {json_retries + 1} attempts: {last_exc}") from last_exc


def extract_json_array(text: str) -> list:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1:
            text = text[start:end + 1]
    return json.loads(text)


def extract_json_object(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
    return json.loads(text)
