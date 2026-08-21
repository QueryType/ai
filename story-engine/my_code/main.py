"""Story Engine — entry point.

Usage:
    python -m my_code.main examples/ashenveil_scene1.md
    python -m my_code.main --file examples/ashenveil_scene1.md
    python -m my_code.main --file examples/ashenveil_scene1.md --verbose
"""

from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv


def main():
    load_dotenv()

    from my_code.agents.orchestrator import skip_eval_env_default, skip_memory_env_default

    parser = argparse.ArgumentParser(description="Story Engine — agentic narrative generator")
    parser.add_argument("file", nargs="?", help="Path to the scene .md file")
    parser.add_argument("--file", "-f", dest="file_flag", help="Path to the scene .md file (alternative)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        default=skip_eval_env_default(),
        help="Bypass the evaluator — accept narrator output unchecked, no retries "
        "(default from STORY_ENGINE_SKIP_EVAL env var)",
    )
    parser.add_argument(
        "--skip-memory",
        action="store_true",
        default=skip_memory_env_default(),
        help="Bypass Story Memory — no cross-file fact extraction or retrieval this run "
        "(default from STORY_ENGINE_SKIP_MEMORY env var)",
    )

    args = parser.parse_args()

    file_path = args.file or args.file_flag
    if not file_path:
        parser.error("Please provide a scene file path")

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    from my_code.agents.orchestrator import run_scene

    print(f"\n🎭 Story Engine")
    print(f"   Scene: {file_path}\n")

    try:
        output_path = run_scene(file_path, skip_eval=args.skip_eval, skip_memory=args.skip_memory)
        print(f"\n✅ Done! Output: {output_path}")
    except KeyboardInterrupt:
        print("\n\n⏹ Interrupted by user.")
        sys.exit(1)
    except Exception as e:
        logging.getLogger(__name__).exception("Fatal error")
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
