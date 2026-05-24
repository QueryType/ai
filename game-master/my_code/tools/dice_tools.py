"""Dice tools — standard notation roller for adventure game mechanics."""

from __future__ import annotations

import json
import random
import re


def roll_dice(notation: str) -> str:
    """Roll dice using standard notation. Returns a JSON string.

    Supports: NdS, NdS+M, NdS-M (e.g. "3d20", "2d6+5", "1d100-10").
    """
    notation = notation.strip().lower()
    match = re.fullmatch(r"(\d+)d(\d+)([+-]\d+)?", notation)
    if not match:
        return json.dumps({"error": f"Invalid dice notation: {notation!r}. Use NdS or NdS+M."})

    num_dice = int(match.group(1))
    sides = int(match.group(2))
    modifier = int(match.group(3)) if match.group(3) else 0

    if num_dice < 1 or sides < 2:
        return json.dumps({"error": "num_dice >= 1 and sides >= 2 required"})
    if num_dice > 100:
        return json.dumps({"error": "Maximum 100 dice per roll"})

    rolls = [random.randint(1, sides) for _ in range(num_dice)]
    total = sum(rolls) + modifier

    return json.dumps({"notation": notation, "rolls": rolls, "modifier": modifier, "total": total})
