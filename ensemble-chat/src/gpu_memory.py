"""macOS unified-memory GPU ceiling — Apple Silicon only.

macOS caps how much unified memory the GPU can use (`iogpu.wired_limit_mb`),
leaving room for the OS. Local MLX/llama.cpp/MPS inference is bound by that
ceiling. It resets to the system default on every reboot, so this checks it
at startup and offers to raise it, leaving `headroom_gb` for the OS.
"""
from __future__ import annotations

import platform
import subprocess
import sys


def _is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def _sysctl_int(name: str) -> int:
    out = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, check=True)
    return int(out.stdout.strip())


def ensure_gpu_memory_limit(headroom_gb: float) -> None:
    """No-op off Apple Silicon, or if the ceiling already meets the target.

    A reading of `0` for `iogpu.wired_limit_mb` means "macOS's built-in
    default" (not "no limit") — usually more conservative than this app
    wants for local inference, so it's treated the same as any other
    below-target reading.
    """
    if not _is_apple_silicon():
        return
    try:
        total_mb = _sysctl_int("hw.memsize") // (1024 * 1024)
        current_mb = _sysctl_int("iogpu.wired_limit_mb")
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return

    target_mb = total_mb - int(headroom_gb * 1024)
    if current_mb >= target_mb:
        return

    current_desc = "macOS default" if current_mb == 0 else f"{current_mb} MB"
    print(
        f"GPU memory ceiling is {current_desc}; raising to {target_mb} MB "
        f"(leaves {headroom_gb:.0f} GB for the OS) needs sudo, and only lasts "
        f"until reboot."
    )
    try:
        answer = input("Raise it now? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("Skipped — continuing with the current limit.")
        return
    if answer != "y":
        print("Skipped — continuing with the current limit.")
        return

    result = subprocess.run(["sudo", "sysctl", f"iogpu.wired_limit_mb={target_mb}"])
    if result.returncode != 0:
        print("Could not raise the limit — continuing with the current one.")
