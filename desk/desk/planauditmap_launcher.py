#!/usr/bin/env python3
"""
planauditmap_launcher.py — MapThinkDo MCP launcher, wire tap and desk-bar starter.

Drop this in front of the real plan-audit-map server in your MCP client config.
It does three things and otherwise gets out of the way:

  1. It is a byte-transparent stdio proxy.  Everything your MCP client writes
     to stdin is forwarded to the server verbatim; everything the server writes
     to stdout is forwarded back verbatim.  Nothing is ever written to stdout
     that did not come from the server, so the JSON-RPC stream stays clean.

  2. It taps that stream and writes every JSON-RPC request/response pair into
     the `raw_mcp_events` table of the memory database.  That is the
     "conversation" table the SQL viewer expects but that the upstream server
     never creates — this is what makes the viewer's Raw Events / Conversation
     tabs come alive.  Every event is also mirrored to
     `~/.plan-audit-map/raw-mcp-events.jsonl` in case the DB is locked.

  3. On Windows it starts (or wakes) the taskbar desk bar, and streams live
     activity to it over a localhost socket.

Usage
-----
    python planauditmap_launcher.py [--config PATH] [--no-bar] [--no-log]
                                  [--client NAME] [--] <server command> [args...]

If no command is given on the command line, `server_command` from the config
file is used.  Special modes:

    python planauditmap_launcher.py --start-bar      start only the desk bar
    python planauditmap_launcher.py --stop-bar       ask the desk bar to quit
    python planauditmap_launcher.py --print-mcp-config
                                                   print a ready-to-paste
                                                   mcpServers entry

NOTE: run this with `python.exe`, not `pythonw.exe` — it needs real stdio.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mtd_shared  # noqa: E402

APP = "planauditmap-launcher"


def _log(msg: str) -> None:
    """All diagnostics go to stderr — stdout belongs to the MCP protocol."""
    try:
        sys.stderr.write(f"[{APP}] {msg}\n")
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Desk-bar IPC
# ---------------------------------------------------------------------------

class BarLink:
    """Best-effort localhost link to a running desk bar."""

    def __init__(self, port: int) -> None:
        self.port = port
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()

    def probe(self) -> bool:
        """True if a bar is already listening."""
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=0.35):
                return True
        except OSError:
            return False

    def send(self, payload: Dict[str, Any]) -> bool:
        line = (json.dumps(payload, ensure_ascii=False, default=str) + "\n").encode("utf-8")
        with self._lock:
            for attempt in (0, 1):
                try:
                    if self._sock is None:
                        self._sock = socket.create_connection(
                            ("127.0.0.1", self.port), timeout=0.5)
                        self._sock.settimeout(0.5)
                    self._sock.sendall(line)
                    return True
                except OSError:
                    self._close()
                    if attempt == 1:
                        return False
                    time.sleep(0.05)
        return False

    def _close(self) -> None:
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass
        self._sock = None

    def close(self) -> None:
        with self._lock:
            self._close()


def _find_interpreter(prefer_windowed: bool) -> str:
    """Locate python.exe / pythonw.exe next to the running interpreter."""
    exe = sys.executable or ""
    if prefer_windowed and exe:
        candidate = Path(exe).with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
        # A venv may not ship pythonw; fall back to the base install.
        base = Path(exe).parent.parent / "pythonw.exe"
        if base.exists():
            return str(base)
    return exe or "python"


def start_bar(cfg: Dict[str, Any], desk: Path) -> bool:
    """Start the desk bar detached. Returns True if it is up afterwards."""
    port = int(cfg.get("bar_port") or 38457)
    link = BarLink(port)
    if link.probe():
        link.send({"type": "wake"})
        return True

    script = desk / "planauditmap_bar.pyw"
    if not script.exists():
        script = desk / "planauditmap_bar.py"
    if not script.exists():
        _log(f"desk bar script not found next to {desk}; skipping")
        return False

    pythonw = cfg.get("pythonw_exe") or _find_interpreter(prefer_windowed=True)
    creationflags = 0
    startupinfo = None
    if os.name == "nt":
        creationflags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        subprocess.Popen(
            [pythonw, str(script)],
            creationflags=creationflags,
            startupinfo=startupinfo,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError as exc:
        _log(f"could not start desk bar: {exc}")
        return False

    for _ in range(40):  # wait up to ~4s for the listener
        time.sleep(0.1)
        if link.probe():
            return True
    _log("desk bar did not report ready in time")
    return False


# ---------------------------------------------------------------------------
# JSON-RPC tap
# ---------------------------------------------------------------------------

class MessageTap:
    """Accumulates a byte stream and hands out complete JSON-RPC messages."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> List[Dict[str, Any]]:
        self._buf.extend(chunk)
        messages: List[Dict[str, Any]] = []
        while True:
            idx = self._buf.find(b"\n")
            if idx < 0:
                break
            line = bytes(self._buf[:idx])
            del self._buf[: idx + 1]
            msg = self._decode(line)
            if msg is not None:
                messages.append(msg)
        return messages

    @staticmethod
    def _decode(line: bytes) -> Optional[Dict[str, Any]]:
        text = line.strip()
        if not text or text[:1] not in (b"{", b"["):
            return None
        try:
            obj = json.loads(text.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return obj if isinstance(obj, dict) else None


def _direction_for(message: Dict[str, Any], stream: str) -> str:
    """Classify a JSON-RPC message as request / response / notification.

    stream is "in" (client -> server) or "out" (server -> client / stderr).
    Server-initiated requests (method + id on the outbound stream, e.g.
    sampling/createMessage roots/list_changed pings) are tagged
    "server-request" so they never pollute the request/response pairing.
    """
    has_id = "id" in message and message.get("id") is not None
    has_method = "method" in message
    if stream == "in":
        if has_id:
            return "request"
        return "notification"  # method without id == client notification
    if has_id and not has_method:
        return "response"
    if has_id and has_method:
        return "server-request"
    return "notification"


def _summarise(message: Dict[str, Any]) -> Dict[str, Any]:
    """A compact view of a message for the desk bar ticker."""
    out: Dict[str, Any] = {
        "method": message.get("method"),
        "id": message.get("id"),
    }
    if message.get("method") == "tools/call":
        params = message.get("params") or {}
        out["tool"] = params.get("name")
        args = params.get("arguments") or {}
        if isinstance(args, dict):
            if args.get("thought"):
                out["text"] = str(args["thought"])[:180]
            out["thought_number"] = args.get("thought_number")
            out["total_thoughts"] = args.get("total_thoughts")
    sid = mtd_shared.extract_session_id(message)
    if sid:
        out["session_id"] = sid
    if "error" in message:
        out["error"] = str(message["error"])[:200]
    return out


# ---------------------------------------------------------------------------
# Proxy
# ---------------------------------------------------------------------------

def _read_some(src, n: int = 8192) -> bytes:
    """Read whatever is available from a stream without blocking for `n`.

    CRITICAL: sys.stdin.buffer is a BufferedReader whose read(8192) blocks
    until the FULL 8192 bytes arrive (or EOF).  MCP stdio frames are small
    (~100 bytes), so the old code deadlocked the client->server direction —
    nothing reached the server until 8 KiB accumulated.  A raw os.read()
    returns as soon as any bytes are available, which is what a proxy needs.
    """
    try:
        fd = src.fileno()
    except (AttributeError, OSError, ValueError):
        return src.read(n)  # last-resort fallback (may block for n bytes)
    return os.read(fd, n)


def _pipe(src, dst, tap: MessageTap, stream: str, store, link: BarLink,
          stop: threading.Event) -> None:
    """Copy src -> dst byte for byte, tapping JSON-RPC messages on the way."""
    if src is None:
        # stdio absent (e.g. started under pythonw): nothing to pump, but a
        # previous version crashed here with AttributeError.  Just idle.
        stop.wait()
        return
    try:
        while not stop.is_set():
            try:
                chunk = _read_some(src)
            except (ValueError, OSError):
                break
            if not chunk:
                break
            if dst is not None:
                try:
                    dst.write(chunk)
                    dst.flush()
                except (BrokenPipeError, OSError, ValueError):
                    break
            for message in tap.feed(chunk):
                try:
                    direction = _direction_for(message, stream)
                    if store is not None:
                        store.log_message(message, direction)
                    link.send({"type": "mcp", "direction": direction,
                               "stream": stream, **_summarise(message)})
                except Exception as exc:  # noqa: BLE001
                    _log(f"tap error: {exc}")
    finally:
        try:
            if dst is not None:
                dst.flush()
        except Exception:  # noqa: BLE001
            pass
        # Half-close: when the CLIENT side hits EOF, close the child's stdin
        # so it sees EOF too.  Without this the launcher held the pipe open
        # forever and neither process ever exited (the old code only closed
        # proc.stdin long after the loop that could never finish).
        if stream == "in" and dst is not None:
            try:
                dst.close()
            except Exception:  # noqa: BLE001
                pass


def run_proxy(argv: List[str], cfg: Dict[str, Any], desk: Path) -> int:
    store = None
    if cfg.get("log_raw_events", True):
        store = mtd_shared.RawEventStore(
            path=mtd_shared.db_path(),
            provider=cfg.get("provider") or "",
            transport=cfg.get("transport") or "stdio",
            client=cfg.get("client_name") or "",
            mirror_jsonl=bool(cfg.get("mirror_jsonl", True)),
            max_payload_bytes=int(cfg.get("max_payload_bytes") or 262144),
            log=_log,
        )
        store.connect()

    link = BarLink(int(cfg.get("bar_port") or 38457))

    # stdin/stdout may be absent under pythonw; degrade gracefully.
    stdin = getattr(sys.stdin, "buffer", None)
    stdout = getattr(sys.stdout, "buffer", None)
    stderr = getattr(sys.stderr, "buffer", None)

    popen_kwargs: Dict[str, Any] = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "bufsize": 0,
    }
    if os.name == "nt":
        # Keep the server quiet on Windows: no extra console window.
        popen_kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        popen_kwargs["startupinfo"] = info

    try:
        proc = subprocess.Popen(argv, **popen_kwargs)
    except (OSError, ValueError) as exc:
        _log(f"failed to start server {argv!r}: {exc}")
        return 127

    _log(f"started server pid={proc.pid}: {' '.join(argv)}")
    link.send({"type": "server", "state": "up", "pid": proc.pid,
               "command": argv})

    stop = threading.Event()
    threads = [
        threading.Thread(target=_pipe,
                         args=(stdin, proc.stdin, MessageTap(), "in", store, link, stop),
                         name="stdin", daemon=True),
        threading.Thread(target=_pipe,
                         args=(proc.stdout, stdout, MessageTap(), "out", store, link, stop),
                         name="stdout", daemon=True),
        threading.Thread(target=_pipe,
                         args=(proc.stderr, stderr, MessageTap(), "err", None, link, stop),
                         name="stderr", daemon=True),
    ]
    for t in threads:
        t.start()

    exit_code = 0
    try:
        while proc.poll() is None:
            if threads[0].is_alive() or threads[1].is_alive():
                time.sleep(0.15)
            else:
                break
        # stdin closed or stdout ended: stop pumping and let the server finish.
        stop.set()
        try:
            exit_code = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                exit_code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                exit_code = proc.wait()
    except KeyboardInterrupt:
        stop.set()
        proc.terminate()
        exit_code = proc.wait()
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=1.0)
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        if store is not None:
            store.close()
        link.send({"type": "server", "state": "down", "exit_code": exit_code})
        link.close()

    _log(f"server exited with {exit_code}")
    return exit_code


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _mcp_config_snippet(desk: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    python = mtd_shared._default_python()
    cmd = cfg.get("server_command") or ["node", "<PATH TO>/plan-audit-map/dist/index.js"]
    return {
        "mcpServers": {
            "plan-audit-map": {
                "command": python,
                "args": [str(desk / "planauditmap_launcher.py"), "--"] + list(cmd),
                "env": {},
            }
        }
    }


def main(argv: Optional[List[str]] = None) -> int:
    desk = mtd_shared.desk_dir()
    cfg = mtd_shared.load_bar_config()

    parser = argparse.ArgumentParser(
        prog="planauditmap_launcher.py",
        description="MapThinkDo MCP launcher / wire tap / desk-bar starter.",
    )
    parser.add_argument("--config", help="path to desk-bar.json")
    parser.add_argument("--no-bar", action="store_true", help="do not start the desk bar")
    parser.add_argument("--no-log", action="store_true",
                        help="do not record raw MCP events")
    parser.add_argument("--client", default="", help="client name to record")
    parser.add_argument("--start-bar", action="store_true",
                        help="start the desk bar and exit")
    parser.add_argument("--stop-bar", action="store_true",
                        help="ask a running desk bar to quit")
    parser.add_argument("--open-intervention", action="store_true",
                        help="open the desk bar's Intervention paste bar"
                             " (starts the bar if needed) and exit")
    parser.add_argument("--print-mcp-config", action="store_true",
                        help="print an mcpServers snippet and exit")
    parser.add_argument("server", nargs=argparse.REMAINDER,
                        help="server command, e.g. -- node C:/.../dist/index.js")
    args = parser.parse_args(argv)

    if args.config:
        cfg = mtd_shared.load_bar_config()
        try:
            cfg.update(json.loads(Path(args.config).read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            _log(f"could not read --config {args.config}: {exc}")
    cfg["client_name"] = args.client
    if args.no_log:
        cfg["log_raw_events"] = False
    # Env override beats sniffing (set by the generated Qwen/Claude JSONs).
    env_provider = (os.environ.get("PLAN_AUDIT_MAP_PROVIDER")
                    or os.environ.get("MAPTHINKDO_PROVIDER") or "").strip()
    if env_provider and not cfg.get("provider"):
        cfg["provider"] = env_provider

    if args.print_mcp_config:
        print(json.dumps(_mcp_config_snippet(desk, cfg), indent=2))
        return 0

    link = BarLink(int(cfg.get("bar_port") or 38457))

    if args.stop_bar:
        ok = link.send({"type": "quit"})
        _log("quit signal sent" if ok else "no desk bar listening")
        return 0 if ok else 1

    if args.start_bar:
        return 0 if start_bar(cfg, desk) else 1

    if args.open_intervention:
        if not link.send({"type": "intervene"}):
            if start_bar(cfg, desk):
                time.sleep(0.4)
                ok = link.send({"type": "intervene"})
                _log("intervention pane requested" if ok else
                     "bar is up but did not answer")
                return 0 if ok else 1
            _log("could not start the desk bar")
            return 1
        _log("intervention pane requested")
        return 0

    # ---- start the desk bar (Windows only by default) --------------------
    want_bar = bool(cfg.get("autostart_with_server", True)) and not args.no_bar
    if want_bar and sys.platform.startswith("win") and bool(cfg.get("enabled", True)):
        threading.Thread(target=start_bar, args=(cfg, desk),
                         name="start-bar", daemon=True).start()
    elif want_bar and not sys.platform.startswith("win"):
        _log("desk bar is Windows-only; skipping")

    # ---- resolve the real server command ---------------------------------
    server: List[str] = []
    if args.server:
        server = [a for a in args.server if a != "--"]
    if not server:
        server = list(cfg.get("server_command") or [])
    if not server:
        _log("no server command given. Pass it after '--', or set "
             "server_command in desk-bar.json. Example:")
        _log("  python planauditmap_launcher.py -- node C:/src/plan-audit-map/dist/index.js")
        return 2

    return run_proxy(server, cfg, desk)


if __name__ == "__main__":
    sys.exit(main())
