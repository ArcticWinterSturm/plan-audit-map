from __future__ import annotations

import argparse
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Iterable, Optional

from .config import AppConfig, ensure_config, load_config
from .storage import DeskDatabase, LaunchRecord


def normalize_agent_name(raw: str) -> str:
    value = (raw or "unknown").strip().lower()
    aliases = {
        "claude": "Claude Code",
        "claude-code": "Claude Code",
        "claude_code": "Claude Code",
        "codex": "Codex",
        "opencode": "OpenCode",
        "hermes": "Hermes",
        "chatgpt": "ChatGPT",
        "openai": "ChatGPT",
    }
    return aliases.get(value, raw.strip() or "Unknown")


def infer_venv() -> str:
    return os.environ.get("VIRTUAL_ENV", "")


def infer_project_path(cwd: Optional[str] = None) -> str:
    return str(Path(cwd or os.getcwd()).resolve())


def make_database(config: AppConfig) -> DeskDatabase:
    return DeskDatabase(config.db_path)


def record_launch(
    config: AppConfig,
    *,
    agent: str,
    instance_key: Optional[str] = None,
    pid: Optional[int] = None,
    provider: str = "",
    command: str = "",
    cwd: str = "",
    venv_path: str = "",
    project_path: str = "",
) -> LaunchRecord:
    db = make_database(config)
    return db.record_launch(
        agent=normalize_agent_name(agent),
        instance_key=instance_key,
        pid=pid,
        provider=provider,
        command=command,
        cwd=cwd or os.getcwd(),
        venv_path=venv_path or infer_venv(),
        project_path=project_path or infer_project_path(cwd),
    )


def send_heartbeat(config: AppConfig, instance_key: str) -> None:
    make_database(config).heartbeat(instance_key)


def finish_launch(config: AppConfig, instance_key: str, exit_code: int) -> None:
    make_database(config).finish(instance_key, exit_code=exit_code)


class AgentProcessRunner:
    def __init__(
        self,
        config: AppConfig,
        *,
        agent: str,
        command: list[str],
        cwd: Optional[str] = None,
        provider: str = "",
        heartbeat_seconds: float = 10.0,
    ) -> None:
        self.config = config
        self.agent = normalize_agent_name(agent)
        self.command = command
        self.cwd = cwd or os.getcwd()
        self.provider = provider
        self.heartbeat_seconds = heartbeat_seconds
        self.instance_key = str(uuid.uuid4())
        self._stop = threading.Event()
        self.process: Optional[subprocess.Popen[int]] = None

    def run(self) -> int:
        shell_command = shlex.join(self.command)
        record_launch(
            self.config,
            agent=self.agent,
            instance_key=self.instance_key,
            pid=None,
            provider=self.provider,
            command=shell_command,
            cwd=self.cwd,
        )
        kwargs = {
            "cwd": self.cwd,
            "env": os.environ.copy(),
        }
        if os.name != "nt":
            kwargs["preexec_fn"] = os.setsid
        self.process = subprocess.Popen(self.command, **kwargs)
        send_heartbeat(self.config, self.instance_key)
        make_database(self.config).record_launch(
            agent=self.agent,
            instance_key=self.instance_key,
            pid=self.process.pid,
            provider=self.provider,
            command=shell_command,
            cwd=self.cwd,
            venv_path=infer_venv(),
            project_path=infer_project_path(self.cwd),
        )
        hb = threading.Thread(target=self._heartbeat_loop, name="agent-heartbeat", daemon=True)
        hb.start()
        self._wire_signals()
        rc = self.process.wait()
        self._stop.set()
        hb.join(timeout=max(self.heartbeat_seconds, 1.0))
        finish_launch(self.config, self.instance_key, rc)
        return rc

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            try:
                send_heartbeat(self.config, self.instance_key)
            except Exception:
                pass

    def _wire_signals(self) -> None:
        if self.process is None:
            return

        def handler(signum, _frame):
            try:
                if self.process is None:
                    return
                if os.name == "nt":
                    self.process.send_signal(signal.SIGTERM)
                else:
                    os.killpg(os.getpgid(self.process.pid), signum)
            finally:
                self._stop.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handler)
            except Exception:
                continue


def add_tracker_arguments(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="tracker_command")

    launch = sub.add_parser("launch", help="Record a launch event")
    _common_tracker_args(launch)
    launch.add_argument("--instance-key", default="")

    heartbeat = sub.add_parser("heartbeat", help="Send a heartbeat for a running instance")
    heartbeat.add_argument("--config", default="")
    heartbeat.add_argument("--instance-key", required=True)

    finish = sub.add_parser("finish", help="Mark an instance as finished")
    finish.add_argument("--config", default="")
    finish.add_argument("--instance-key", required=True)
    finish.add_argument("--exit-code", type=int, default=0)

    run_agent = sub.add_parser("run-agent", help="Wrap a real agent process with launch tracking")
    _common_tracker_args(run_agent)
    run_agent.add_argument("--heartbeat-seconds", type=float, default=10.0)
    run_agent.add_argument("command", nargs=argparse.REMAINDER)


def _common_tracker_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="")
    parser.add_argument("--agent", required=True)
    parser.add_argument("--provider", default="")
    parser.add_argument("--cwd", default="")


def tracker_main(args: argparse.Namespace) -> int:
    command = args.tracker_command
    cfg = ensure_config(args.config) if getattr(args, "config", "") else ensure_config()

    if command == "launch":
        record = record_launch(
            cfg,
            agent=args.agent,
            provider=args.provider,
            instance_key=args.instance_key or None,
            pid=os.getpid(),
            cwd=args.cwd or os.getcwd(),
            command="",
        )
        print(record.instance_key)
        return 0

    if command == "heartbeat":
        send_heartbeat(cfg, args.instance_key)
        return 0

    if command == "finish":
        finish_launch(cfg, args.instance_key, args.exit_code)
        return 0

    if command == "run-agent":
        tail = list(args.command)
        if tail and tail[0] == "--":
            tail = tail[1:]
        if not tail:
            raise SystemExit("run-agent requires a command after --")
        runner = AgentProcessRunner(
            cfg,
            agent=args.agent,
            command=tail,
            cwd=args.cwd or os.getcwd(),
            provider=args.provider,
            heartbeat_seconds=args.heartbeat_seconds,
        )
        return runner.run()

    raise SystemExit(f"Unknown tracker command: {command}")
