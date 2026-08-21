"""Facts server — small read-only HTTP endpoint over the Story Memory fact
store, for browser tools (scene-builder.html) that can't read a server-side
SQLite file directly.

No new dependencies — stdlib http.server only, matching this project's
dependency-light conventions. Read-only: GET requests, no mutation, so no
auth. Binds to 0.0.0.0 by default to match the LAN setup already used for
the narrator/evaluator servers (see CLAUDE.md .env configuration).

Usage:
    python -m my_code.facts_server
    python -m my_code.facts_server --port 8082 --output-dir output

Design: docs/STORY_MEMORY_SPEC.md.
"""

from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from my_code.tools import fact_store

_STORY_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _list_story_ids(output_dir: Path) -> list[str]:
    """Story ids with a facts db present in output_dir, e.g. '.story.facts.db' -> 'story'."""
    ids = []
    for p in output_dir.glob(".*.facts.db"):
        # ".<story_id>.facts.db" -> story_id
        name = p.name[1:]  # strip leading dot
        if name.endswith(".facts.db"):
            ids.append(name[: -len(".facts.db")])
    return sorted(ids)


class FactsHandler(BaseHTTPRequestHandler):
    output_dir: Path = Path("output")  # overridden by main() before serving

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # CORS preflight
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/health":
            self._send_json(200, {"ok": True})
            return

        if parsed.path == "/stories":
            self._send_json(200, {"stories": _list_story_ids(self.output_dir)})
            return

        if parsed.path == "/facts":
            story_id = (params.get("story_id") or [""])[0]
            through_scene_raw = (params.get("through_scene") or [""])[0]

            if not story_id or not _STORY_ID_RE.match(story_id):
                self._send_json(400, {"error": "story_id is required and must match [A-Za-z0-9_-]+"})
                return
            try:
                through_scene = int(through_scene_raw)
            except ValueError:
                self._send_json(400, {"error": "through_scene is required and must be an integer"})
                return

            db_path = self.output_dir / f".{story_id}.facts.db"
            if not db_path.exists():
                self._send_json(404, {"error": f"no facts db for story_id={story_id!r}"})
                return

            # Everything established through the end of through_scene (inclusive) —
            # same bound extend.py uses server-side: before=(scene_index+1, 0).
            facts_by_entity = fact_store.query_all_facts(
                db_path, story_id, before=(through_scene + 1, 0)
            )
            self._send_json(200, {"story_id": story_id, "through_scene": through_scene, "facts": facts_by_entity})
            return

        self._send_json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args) -> None:
        print(f"[facts_server] {self.address_string()} - {fmt % args}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Read-only HTTP server over the Story Memory fact store.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8082, help="Bind port (default: 8082)")
    parser.add_argument("--output-dir", default="output", help="Directory containing .facts.db files (default: output)")
    args = parser.parse_args(argv)

    FactsHandler.output_dir = Path(args.output_dir)
    server = ThreadingHTTPServer((args.host, args.port), FactsHandler)
    print(f"Facts server: http://{args.host}:{args.port}  (output_dir={FactsHandler.output_dir})")
    print("Routes: GET /health, GET /stories, GET /facts?story_id=...&through_scene=...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
