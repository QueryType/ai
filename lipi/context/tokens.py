"""
context/tokens.py — Local token estimation
Estimates token counts from message char lengths.
Auto-calibrates when the API reports actual prompt_tokens.
"""

import json

_chars_per_token: float = 3.8


def estimate_tokens(messages: list[dict]) -> int:
    total_chars = sum(len(json.dumps(m)) for m in messages)
    return int(total_chars / _chars_per_token)


def calibrate(messages: list[dict], actual_prompt_tokens: int) -> None:
    global _chars_per_token
    total_chars = sum(len(json.dumps(m)) for m in messages)
    if actual_prompt_tokens < 1:
        return
    observed = total_chars / actual_prompt_tokens
    _chars_per_token = 0.7 * _chars_per_token + 0.3 * observed


def context_usage(messages: list[dict], context_window: int) -> float:
    if context_window <= 0:
        return 0.0
    return estimate_tokens(messages) / context_window
