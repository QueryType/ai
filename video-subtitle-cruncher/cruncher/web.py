"""`crunch web` — local HTML UI over the inference phases (describe / summarize / ask).

Stdlib-only server (no new dependencies). Serves a single-page UI plus a small
JSON API that wraps the same functions the CLI uses. Snapshot/record stay on
the CLI — this covers everything that talks to the model.
"""

import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from . import generate
from .manifest import Job
from .provider import DEFAULT_BASE_URL, DEFAULT_MODEL, ProviderError, VisionProvider
from .timeline import TRANSCRIPT_WINDOW, build_timeline

UI_PATH = Path(__file__).parent / "webui.html"


def _job_info(path: Path) -> dict:
    job = Job(path)
    m = job.load_manifest()
    phases = m.get("phases", {})
    described = None
    if job.timeline_path.exists():
        described = len(json.loads(job.timeline_path.read_text()))
    outputs_dir = path / "outputs"
    outputs = sorted((p.name for p in outputs_dir.glob("*.md")), reverse=True) \
        if outputs_dir.is_dir() else []
    return {
        "name": path.name,
        "created": m.get("created", ""),
        "duration": m.get("video", {}).get("duration", 0),
        "source_type": m.get("video", {}).get("source_type", "video"),
        "frames": phases.get("snapshot", {}).get("kept"),
        "transcript_source": phases.get("transcript", {}).get("source"),
        "transcript_segments": phases.get("transcript", {}).get("segments", 0),
        "described": described,
        "outputs": outputs,
    }


class Handler(BaseHTTPRequestHandler):
    jobs_dir: Path  # set on the class by serve()

    # ---- plumbing -------------------------------------------------------

    def log_message(self, fmt, *args):  # quieter default log
        print(f"  {self.address_string()} {fmt % args}")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, code: int = 200) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False).encode(),
                   "application/json; charset=utf-8")

    def _error(self, msg: str, code: int = 400) -> None:
        self._json({"error": msg}, code)

    def _open_job(self, name: str) -> Job:
        # reject anything that could escape jobs_dir
        if not name or "/" in name or "\\" in name or name.startswith("."):
            raise FileNotFoundError(f"bad job name: {name!r}")
        return Job.open(self.jobs_dir, name)

    def _provider(self, params: dict) -> VisionProvider:
        return VisionProvider(params.get("base_url") or DEFAULT_BASE_URL,
                              params.get("model") or DEFAULT_MODEL)

    # ---- GET ------------------------------------------------------------

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            self._route_get(url.path, q)
        except FileNotFoundError as e:
            self._error(str(e), 404)
        except Exception as e:
            traceback.print_exc()
            self._error(f"{type(e).__name__}: {e}", 500)

    def _route_get(self, path: str, q: dict) -> None:
        if path == "/":
            self._send(200, UI_PATH.read_bytes(), "text/html; charset=utf-8")

        elif path == "/api/jobs":
            jobs = [_job_info(p) for p in sorted(self.jobs_dir.iterdir())
                    if (p / "manifest.json").exists()] \
                if self.jobs_dir.is_dir() else []
            self._json({"jobs": jobs,
                        "defaults": {"base_url": DEFAULT_BASE_URL,
                                     "model": DEFAULT_MODEL}})

        elif path == "/api/models":
            base_url = (q.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
            try:
                resp = httpx.get(f"{base_url}/models", timeout=5.0,
                                 headers={"Authorization": "Bearer local"})
                resp.raise_for_status()
                ids = [m.get("id", "") for m in resp.json().get("data", [])]
                self._json({"models": ids})
            except httpx.HTTPError as e:
                self._error(f"endpoint not reachable: {e}", 502)

        elif path == "/api/output":
            job = self._open_job(q.get("job", ""))
            name = q.get("file", "")
            target = (job.outputs_dir / name).resolve()
            if "/" in name or not target.is_file():
                raise FileNotFoundError(f"no output {name!r}")
            self._json({"file": name, "text": target.read_text()})

        elif path.startswith("/frames/"):
            # /frames/<job>/<file> — keyframe images for the outputs viewer
            _, _, job_name, *rest = path.split("/")
            fname = rest[0] if len(rest) == 1 else ""
            job = self._open_job(job_name)
            target = (job.frames_dir / fname).resolve()
            if "/" in fname or not target.is_file():
                raise FileNotFoundError(f"no frame {fname!r}")
            self._send(200, target.read_bytes(), "image/jpeg")

        else:
            self._error(f"no route {path}", 404)

    # ---- POST -----------------------------------------------------------

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            params = json.loads(self.rfile.read(length) or b"{}")
            self._route_post(urlparse(self.path).path, params)
        except FileNotFoundError as e:
            self._error(str(e), 404)
        except ProviderError as e:
            self._error(str(e), 502)
        except Exception as e:
            traceback.print_exc()
            self._error(f"{type(e).__name__}: {e}", 500)

    def _route_post(self, path: str, p: dict) -> None:
        if path == "/api/describe":
            job = self._open_job(p.get("job", ""))
            provider = self._provider(p)
            timeline = build_timeline(job, provider,
                                      window=float(p.get("window") or TRANSCRIPT_WINDOW))
            job.update_manifest(phases={"timeline": {"entries": len(timeline)}})
            self._json({"entries": len(timeline)})

        elif path == "/api/summarize":
            job = self._open_job(p.get("job", ""))
            style = p.get("style", "short")
            if style not in generate.STYLE_PROMPTS:
                return self._error(f"unknown style {style!r}")
            out = generate.summarize(job, self._provider(p), style)
            self._json({"file": out.name, "text": out.read_text()})

        elif path == "/api/ask":
            job = self._open_job(p.get("job", ""))
            question = (p.get("question") or "").strip()
            if not question:
                return self._error("empty question")
            answer, out = generate.ask(job, self._provider(p), question)
            self._json({"file": out.name, "text": answer})

        else:
            self._error(f"no route {path}", 404)


def serve(jobs_dir: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    Handler.jobs_dir = Path(jobs_dir)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"crunch web ui: http://{host}:{port}  (jobs dir: {jobs_dir})")
    print("Ctrl-C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
