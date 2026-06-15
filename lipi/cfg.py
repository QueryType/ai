#!/usr/bin/env python3
"""
cfg.py — CLI to view/set/unset values in config.yaml

Usage:
  python cfg.py                                    # show all
  python cfg.py get harness.profile                # get one value
  python cfg.py set harness.profile analyst         # set a value
  python cfg.py unset harness.profile              # revert to default
  python cfg.py profile --url URL --model MODEL    # update all profiles
  python cfg.py profile --url URL --only coder     # update one profile
"""

import argparse
import sys
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"

DEFAULTS = {
    "harness": {
        "profile": "coder",
        "max_iterations": 30,
        "max_tool_output": 6000,
        "compaction_threshold": 0.8,
        "mid_turn_warn": 0.90,
        "mid_turn_abort": 0.95,
        "shell_timeout": 60,
        "allowed_write_paths": ["~/projects", "~/harness", "/tmp"],
        "confirm_commands": [
            "rm -rf", "sudo", "pip install", "brew install",
            "git push", "curl | bash", "wget | bash",
        ],
        "confirm_writes": True,
        "locked_paths": [
            "/etc/*", "/System/*", "/Library/*", "/usr/*", "/bin/*",
            "/sbin/*", "/var/*", "/private/*", "/boot/*",
            "~/.ssh/*", "~/.gnupg/*", "~/.bash_profile", "~/.zshrc", "~/.zprofile",
        ],
        "vision_profile": "vision",
        "duckdb_path": "~/projects/breadth/breadth.duckdb",
        "sessions_dir": "~/.harness/sessions",
        "save_sessions": True,
        "stream_output": True,
        "show_tool_calls": True,
        "show_timings": False,
        "render_markdown": True,
    },
}


def _load() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def _save(data: dict):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _get_nested(data: dict, dotpath: str):
    keys = dotpath.split(".")
    cur = data
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _set_nested(data: dict, dotpath: str, value):
    keys = dotpath.split(".")
    cur = data
    for k in keys[:-1]:
        if k not in cur or not isinstance(cur[k], dict):
            cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value


def _del_nested(data: dict, dotpath: str) -> bool:
    keys = dotpath.split(".")
    cur = data
    for k in keys[:-1]:
        if not isinstance(cur, dict) or k not in cur:
            return False
        cur = cur[k]
    if isinstance(cur, dict) and keys[-1] in cur:
        del cur[keys[-1]]
        return True
    return False


def _coerce(value_str: str):
    if value_str.lower() == "true":
        return True
    if value_str.lower() == "false":
        return False
    try:
        return int(value_str)
    except ValueError:
        pass
    try:
        return float(value_str)
    except ValueError:
        pass
    return value_str


# ── Display ──────────────────────────────────────────────────────────────────

DIM = "\033[2m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
BOLD = "\033[1m"
R = "\033[0m"


def _fmt_value(v) -> str:
    if isinstance(v, bool):
        return f"{GREEN}{v}{R}"
    if isinstance(v, (int, float)):
        return f"{YELLOW}{v}{R}"
    if isinstance(v, str):
        return f"{CYAN}{v}{R}"
    if isinstance(v, list):
        items = ", ".join(str(i) for i in v)
        return f"{DIM}[{R}{items}{DIM}]{R}"
    return str(v)


def _show_all(data: dict):
    for section, values in data.items():
        print(f"\n{BOLD}{section}{R}")
        if isinstance(values, dict):
            if section == "profiles":
                for pname, pcfg in values.items():
                    print(f"  {CYAN}{pname}{R}")
                    for k, v in pcfg.items():
                        print(f"    {k}: {_fmt_value(v)}")
            else:
                for k, v in values.items():
                    print(f"  {k}: {_fmt_value(v)}")
        else:
            print(f"  {_fmt_value(values)}")
    print()


def _show_value(dotpath: str, value):
    if isinstance(value, dict):
        print(f"{BOLD}{dotpath}{R}")
        for k, v in value.items():
            if isinstance(v, dict):
                print(f"  {CYAN}{k}{R}")
                for k2, v2 in v.items():
                    print(f"    {k2}: {_fmt_value(v2)}")
            else:
                print(f"  {k}: {_fmt_value(v)}")
    else:
        print(f"{dotpath}: {_fmt_value(value)}")


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_show(args):
    data = _load()
    if not data:
        print("config.yaml is empty or missing.")
        return
    _show_all(data)


def cmd_get(args):
    data = _load()
    value = _get_nested(data, args.key)
    if value is None:
        print(f"{args.key}: {DIM}(not set){R}")
        default = _get_nested(DEFAULTS, args.key)
        if default is not None:
            print(f"  default: {_fmt_value(default)}")
    else:
        _show_value(args.key, value)


def cmd_set(args):
    data = _load()
    value = _coerce(args.value)
    old = _get_nested(data, args.key)
    _set_nested(data, args.key, value)
    _save(data)
    if old is not None:
        print(f"{args.key}: {_fmt_value(old)} -> {_fmt_value(value)}")
    else:
        print(f"{args.key}: {_fmt_value(value)} {DIM}(new){R}")


def cmd_unset(args):
    data = _load()
    old = _get_nested(data, args.key)
    default = _get_nested(DEFAULTS, args.key)

    if old is None:
        print(f"{args.key}: {DIM}(already not set){R}")
        return

    if default is not None:
        _set_nested(data, args.key, default)
        _save(data)
        print(f"{args.key}: {_fmt_value(old)} -> {_fmt_value(default)} {DIM}(default){R}")
    else:
        _del_nested(data, args.key)
        _save(data)
        print(f"{args.key}: {_fmt_value(old)} -> {DIM}(removed){R}")


def cmd_profile(args):
    if not args.url and not args.model:
        print("Nothing to update. Use --url and/or --model.")
        return

    data = _load()
    profiles = data.get("profiles", {})
    if not profiles:
        print("No profiles found in config.yaml.")
        return

    targets = [args.only] if args.only else list(profiles.keys())
    for name in targets:
        if name not in profiles:
            print(f"  {YELLOW}skip{R} {name} — not found")
            continue
        changes = []
        if args.url:
            old = profiles[name].get("base_url", "")
            profiles[name]["base_url"] = args.url
            changes.append(f"url: {DIM}{old}{R} -> {CYAN}{args.url}{R}")
        if args.model:
            old = profiles[name].get("model", "")
            profiles[name]["model"] = args.model
            changes.append(f"model: {DIM}{old}{R} -> {CYAN}{args.model}{R}")
        print(f"  {GREEN}{name}{R}  {', '.join(changes)}")

    _save(data)
    print(f"\nUpdated {len(targets)} profile(s).")


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="View and edit config.yaml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("show", help="Show all config values (default)")

    p_get = sub.add_parser("get", help="Get a config value")
    p_get.add_argument("key", help="Dot-separated key (e.g. harness.profile)")

    p_set = sub.add_parser("set", help="Set a config value")
    p_set.add_argument("key", help="Dot-separated key")
    p_set.add_argument("value", help="Value to set")

    p_unset = sub.add_parser("unset", help="Revert a config value to default")
    p_unset.add_argument("key", help="Dot-separated key")

    p_prof = sub.add_parser("profile", help="Update base_url/model across profiles")
    p_prof.add_argument("--url", help="Set base_url for profiles")
    p_prof.add_argument("--model", help="Set model for profiles")
    p_prof.add_argument("--only", metavar="NAME", help="Only update this profile")

    args = parser.parse_args()

    commands = {
        "get": cmd_get,
        "set": cmd_set,
        "unset": cmd_unset,
        "profile": cmd_profile,
        "show": cmd_show,
    }

    handler = commands.get(args.command, cmd_show)
    handler(args)


if __name__ == "__main__":
    main()
