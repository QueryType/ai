"""crunch — CLI for the video subtitle cruncher."""

import argparse
import sys
import time
from pathlib import Path

from . import screen as scr
from . import snapshot as snap
from . import transcript as tr
from .manifest import DEFAULT_JOBS_DIR, Job
from .provider import DEFAULT_BASE_URL, DEFAULT_MODEL, ProviderError, VisionProvider


def _get_provider(args) -> VisionProvider | None:
    if args.no_cc:
        return None
    provider = VisionProvider(args.base_url, args.model)
    if not provider.ping():
        print(f"  vision endpoint not reachable at {args.base_url} — "
              f"skipping CC detection")
        return None
    return provider


def _process_samples(job: Job, samples: list, fps: float, args,
                     asr_video: Path | None = None) -> None:
    """Shared tail of phase 1: CC detection → dedup → transcript → manifest.

    `asr_video` enables the ASR fallback (video jobs only; screen has no audio).
    """
    band = None
    provider = _get_provider(args)
    if provider:
        print("detecting burned-in captions ...")
        try:
            band = tr.detect_caption_band(samples, provider)
        except ProviderError as e:
            print(f"  cc detection failed: {e}")
            band = None
        print(f"  captions: {'yes, band ' + str(band) if band else 'none detected'}")

    print(f"dedup (threshold {args.threshold}"
          f"{', caption band masked' if band else ''}) ...")
    kept = snap.dedup(samples, job.frames_dir, args.threshold, band)
    print(f"  kept {len(kept)}/{len(samples)} frames")

    segments, source = [], "none"
    if band and provider:
        print("reading captions ...")
        segments, source = tr.extract_cc(samples, fps, band, provider), "cc"
    elif asr_video is not None and not args.no_asr:
        print(f"transcribing audio (faster-whisper {args.asr_model}) ...")
        segments, source = tr.asr(asr_video, args.asr_model), "asr"
    else:
        print("no transcript source (no captions detected"
              f"{'' if asr_video is not None else ', no audio channel'})")
    job.write_transcript(source, segments)
    print(f"  {len(segments)} transcript segments ({source})")

    job.update_manifest(
        settings={"fps": fps, "threshold": args.threshold,
                  "long_edge": args.long_edge, "caption_band": band},
        phases={"snapshot": {"samples": len(samples), "kept": len(kept)},
                "transcript": {"source": source, "segments": len(segments)}},
        frames=kept,
    )
    if not args.keep_samples:
        job.drop_samples()
    print("done.")


def cmd_snapshot(args) -> int:
    video = Path(args.video)
    if not video.exists():
        print(f"error: no such file: {video}", file=sys.stderr)
        return 1

    job = Job.create(Path(args.jobs_dir), video, name=args.name, force=args.force)
    print(f"job: {job.root}")

    info = snap.probe(video)
    print(f"video: {info['duration']:.0f}s, {info['width']}x{info['height']}, "
          f"audio={'yes' if info['has_audio'] else 'no'}")

    print(f"sampling at {args.fps} fps ...")
    samples = snap.extract_samples(video, job.samples_dir, args.fps, args.long_edge)
    print(f"  {len(samples)} samples")

    job.update_manifest(video=info)
    _process_samples(job, samples, args.fps, args,
                     asr_video=video if info["has_audio"] else None)
    return 0


def cmd_pick(args) -> int:
    from .pick import pick_region
    region = pick_region()
    if not region:
        print("cancelled")
        return 1
    spec = f"{region['left']},{region['top']},{region['width']},{region['height']}"
    print(f"region: {spec}")
    print(f"crunch record --region {spec}")
    return 0


def cmd_record(args) -> int:
    if args.pick:
        from .pick import pick_region
        region = pick_region()
        if not region:
            print("cancelled")
            return 1
        args.region = (f"{region['left']},{region['top']},"
                       f"{region['width']},{region['height']}")
        print(f"picked region: {args.region}")
        if args.countdown:
            for i in range(args.countdown, 0, -1):
                print(f"  recording in {i} ...", end="\r")
                time.sleep(1)
            print()
        region = scr.parse_region(args.region)
    else:
        region = scr.parse_region(args.region) if args.region else None
    name = args.name or f"screen-{time.strftime('%Y%m%d-%H%M%S')}"
    job = Job.create(Path(args.jobs_dir), Path(name), name=name, force=args.force)
    print(f"job: {job.root}")
    print(f"recording {'region ' + args.region if region else 'primary screen'} "
          f"every {args.interval}s"
          f"{f' for {args.duration:.0f}s' if args.duration else ' — Ctrl-C to stop'} ...")

    samples = scr.record(job.samples_dir, region, args.interval,
                         args.duration, args.long_edge)
    print(f"  {len(samples)} captures")
    if not samples:
        print("nothing captured — removing job")
        import shutil
        shutil.rmtree(job.root)
        return 1

    job.update_manifest(video={"duration": samples[-1].t, "source_type": "screen",
                               "region": args.region})
    _process_samples(job, samples, 1.0 / args.interval, args)
    return 0


def cmd_describe(args) -> int:
    from .timeline import build_timeline
    job = Job.open(Path(args.jobs_dir), args.job)
    provider = VisionProvider(args.base_url, args.model)
    if not provider.ping():
        print(f"error: vision endpoint not reachable at {args.base_url}",
              file=sys.stderr)
        return 1
    print(f"describing frames for {job.root} ...")
    timeline = build_timeline(job, provider, window=args.window)
    job.update_manifest(phases={"timeline": {"entries": len(timeline)}})
    print(f"wrote {job.timeline_path}")
    return 0


def _output_provider(args) -> VisionProvider | None:
    provider = VisionProvider(args.base_url, args.model)
    if not provider.ping():
        print(f"error: endpoint not reachable at {args.base_url}", file=sys.stderr)
        return None
    return provider


def cmd_summarize(args) -> int:
    from . import generate
    job = Job.open(Path(args.jobs_dir), args.job)
    provider = _output_provider(args)
    if provider is None:
        return 1
    print(f"generating {args.style} summary for {job.root} ...")
    path = generate.summarize(job, provider, args.style)
    print(f"wrote {path}\n")
    print(path.read_text())
    return 0


def cmd_ask(args) -> int:
    from . import generate
    job = Job.open(Path(args.jobs_dir), args.job)
    provider = _output_provider(args)
    if provider is None:
        return 1
    answer, path = generate.ask(job, provider, args.question)
    print(answer)
    print(f"\n(saved to {path})")
    return 0


def cmd_web(args) -> int:
    from .web import serve
    serve(Path(args.jobs_dir), host=args.host, port=args.port)
    return 0


def cmd_list(args) -> int:
    jobs_dir = Path(args.jobs_dir)
    if not jobs_dir.is_dir():
        print("no jobs yet")
        return 0
    for path in sorted(jobs_dir.iterdir()):
        if not (path / "manifest.json").exists():
            continue
        m = Job(path).load_manifest()
        phases = m.get("phases", {})
        snap_info = phases.get("snapshot", {})
        tr_info = phases.get("transcript", {})
        outputs = len(list((path / "outputs").glob("*"))) if (path / "outputs").is_dir() else 0
        print(f"{path.name:30} {m.get('video', {}).get('duration', 0):6.0f}s  "
              f"frames={snap_info.get('kept', '-'):>4}  "
              f"transcript={tr_info.get('source', '-')}({tr_info.get('segments', 0)})  "
              f"outputs={outputs}  [{m.get('created', '')}]")
    return 0


def _add_pipeline_flags(p) -> None:
    p.add_argument("--name", help="job name")
    p.add_argument("--threshold", type=int, default=8,
                   help="phash hamming distance to count as a new frame")
    p.add_argument("--long-edge", type=int, default=1024)
    p.add_argument("--no-cc", action="store_true",
                   help="skip burned-in caption detection")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--keep-samples", action="store_true")
    p.add_argument("--force", action="store_true", help="redo an existing job")


def main() -> int:
    parser = argparse.ArgumentParser(prog="crunch",
                                     description="video/screen → keyframes + transcript → context")
    parser.add_argument("--jobs-dir", default=str(DEFAULT_JOBS_DIR))
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("snapshot", help="phase 1 from a video file")
    p.add_argument("video")
    p.add_argument("--fps", type=float, default=1.0)
    p.add_argument("--no-asr", action="store_true", help="skip ASR fallback")
    p.add_argument("--asr-model", default="small")
    _add_pipeline_flags(p)
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("record", help="phase 1 from live screen capture")
    p.add_argument("--region", help="X,Y,W,H in screen points; omit for full screen")
    p.add_argument("--pick", action="store_true",
                   help="drag-select the region on screen before recording")
    p.add_argument("--countdown", type=int, default=3,
                   help="seconds to wait after --pick before recording starts")
    p.add_argument("--interval", type=float, default=1.0,
                   help="seconds between captures")
    p.add_argument("--duration", type=float,
                   help="stop after N seconds (default: run until Ctrl-C)")
    _add_pipeline_flags(p)
    p.set_defaults(func=cmd_record, no_asr=True, asr_model="small")

    p = sub.add_parser("pick", help="drag-select a screen region, print its X,Y,W,H")
    p.set_defaults(func=cmd_pick)

    p = sub.add_parser("describe", help="phase 2: vision descriptions + timeline.json")
    p.add_argument("job", help="job name (see `crunch list`)")
    p.add_argument("--window", type=float, default=15.0,
                   help="transcript window (s) either side of each frame")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.set_defaults(func=cmd_describe)

    p = sub.add_parser("summarize", help="phase 3: summary from stored timeline")
    p.add_argument("job")
    p.add_argument("--style", choices=["short", "detailed", "chapters"],
                   default="short")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.set_defaults(func=cmd_summarize)

    p = sub.add_parser("ask", help="phase 3: question over stored timeline")
    p.add_argument("job")
    p.add_argument("question")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("web", help="local HTML UI for describe/summarize/ask")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_web)

    p = sub.add_parser("list", help="show processed jobs")
    p.set_defaults(func=cmd_list)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
