from __future__ import annotations

import argparse
import json
from pathlib import Path

from .app import run_desk_app
from .autostart import autostart_status, install_autostart, remove_autostart
from .config import ensure_config
from .tracker import add_tracker_arguments, tracker_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="planauditmap-desk")
    sub = parser.add_subparsers(dest="command")

    desk = sub.add_parser("desk", help="Run the cross-agent desk bar UI")
    desk.add_argument("--config", default="")

    autostart = sub.add_parser("autostart", help="Install or inspect OS login autostart")
    autostart.add_argument("action", choices=["install", "remove", "status"])
    autostart.add_argument("--config", default="")

    config_cmd = sub.add_parser("config", help="Create or print the default desk-bar.json")
    config_cmd.add_argument("--config", default="")
    config_cmd.add_argument("--print", action="store_true")

    tracker = sub.add_parser("track", help="Launch-tracking utilities")
    add_tracker_arguments(tracker)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "desk":
        cfg = ensure_config(args.config or None)
        return run_desk_app(str(cfg.config_path))

    if args.command == "autostart":
        cfg = ensure_config(args.config or None)
        if args.action == "install":
            path = install_autostart(cfg)
            print(path)
            return 0
        if args.action == "remove":
            print("removed" if remove_autostart(cfg) else "not-installed")
            return 0
        if args.action == "status":
            print(autostart_status(cfg))
            return 0

    if args.command == "config":
        cfg = ensure_config(args.config or None)
        if args.print:
            print(json.dumps(cfg.to_dict(), indent=2))
        else:
            print(cfg.config_path)
        return 0

    if args.command == "track":
        return tracker_main(args)

    parser.print_help()
    return 1
