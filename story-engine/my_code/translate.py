"""translate.py — translate a large story text file paragraph by paragraph.

Usage:
    python -m my_code.translate input.md --target Hindi
    python -m my_code.translate input.md --target French --source English
    python -m my_code.translate input.md --target Hinglish --hint "Write in Roman script (Latin alphabet), not Devanagari"
    python -m my_code.translate input.md --target Urdu --hint "Use Arabic script"
    python -m my_code.translate input.md --target Hindi --output /tmp/out.md
"""

from __future__ import annotations

import argparse
import gc
import logging
import sys
from pathlib import Path

from my_code.agents.translator import create_translator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_CONTEXT_WINDOW = 2


def _split_paragraphs(text: str) -> list[str]:
    blocks = text.split("\n\n")
    return [b.strip() for b in blocks if b.strip()]


def _detect_language(first_paragraph: str, target_lang: str, hint: str | None) -> str:
    log.info("Detecting source language...")
    agent = create_translator(source_lang="auto", target_lang=target_lang, hint=hint)
    prompt = (
        "Identify the language of the following text. "
        "Reply with only the full language name in English (e.g. 'English', 'Hindi', 'French').\n\n"
        f"{first_paragraph}"
    )
    result = agent(prompt)
    detected = str(result).strip().splitlines()[0].strip(" .,")
    log.info("Detected source language: %s", detected)
    return detected


def _build_context_block(recent: list[str]) -> str:
    if not recent:
        return ""
    joined = "\n\n".join(recent)
    return (
        "[Prior translated context — do not retranslate]\n"
        f"{joined}\n"
        "[End of prior context]\n\n"
    )


def _translate_paragraph(
    paragraph: str,
    context: list[str],
    source_lang: str,
    target_lang: str,
    hint: str | None,
    index: int,
    total: int,
) -> str:
    gc.collect()
    agent = create_translator(source_lang=source_lang, target_lang=target_lang, hint=hint)
    context_block = _build_context_block(context)
    prompt = f"{context_block}Translate the following paragraph:\n\n{paragraph}"
    log.info("Paragraph %d/%d → translating (%d context paragraphs)", index, total, len(context))
    result = agent(prompt)
    translated = str(result).strip()
    log.info("Paragraph %d/%d ← done (%d chars)", index, total, len(translated))
    return translated


def run_translation(
    input_path: Path,
    target_lang: str,
    source_lang: str | None,
    context_paragraphs: int,
    hint: str | None,
    output_path: Path | None,
) -> Path:
    text = input_path.read_text(encoding="utf-8")
    paragraphs = _split_paragraphs(text)
    total = len(paragraphs)
    log.info("Input: %s — %d paragraphs", input_path.name, total)

    if not source_lang:
        source_lang = _detect_language(paragraphs[0], target_lang, hint)

    translated: list[str] = []
    rolling_context: list[str] = []

    for i, para in enumerate(paragraphs, start=1):
        result = _translate_paragraph(
            paragraph=para,
            context=rolling_context[-context_paragraphs:],
            source_lang=source_lang,
            target_lang=target_lang,
            hint=hint,
            index=i,
            total=total,
        )
        translated.append(result)
        rolling_context.append(result)

    if output_path is None:
        output_path = input_path.with_suffix(f".translated{input_path.suffix}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n\n".join(translated), encoding="utf-8")
    log.info("Written to %s", output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate a story file paragraph by paragraph.")
    parser.add_argument("input", type=Path, help="Input text or markdown file")
    parser.add_argument("--target", required=True, help="Target language (e.g. Hindi, French, Hinglish)")
    parser.add_argument("--source", default=None, help="Source language (auto-detected if omitted)")
    parser.add_argument(
        "--context-paragraphs",
        type=int,
        default=_CONTEXT_WINDOW,
        help=f"Number of prior translated paragraphs to carry as context (default: {_CONTEXT_WINDOW})",
    )
    parser.add_argument(
        "--hint",
        default=None,
        help='Extra instructions appended to the system prompt, e.g. "Use Roman script" or "Use Arabic script"',
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: <input>.translated.<ext>)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        log.error("File not found: %s", args.input)
        sys.exit(1)

    output = run_translation(
        input_path=args.input,
        target_lang=args.target,
        source_lang=args.source,
        context_paragraphs=args.context_paragraphs,
        hint=args.hint,
        output_path=args.output,
    )
    print(f"\nTranslation complete: {output}")


if __name__ == "__main__":
    main()
