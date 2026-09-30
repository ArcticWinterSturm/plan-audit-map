#!/usr/bin/env python3
"""
mtd_shared.py — shared infrastructure for the MapThinkDo desk bar, launcher and viewer.

Everything in here is stdlib-only so the whole desk-band stack runs on a stock
Windows Python with no pip install.

Responsibilities
----------------
  * path / config discovery (~/.plan-audit-map, overrides via env vars)
  * the `raw_mcp_events` schema (the "conversation" table the viewer expects
    but that the upstream server never creates)
  * a crash-safe, multi-process-safe writer for that table (WAL + retry)
  * the "recent activity" feed shared by the taskbar bar and the viewer

The upstream plan-audit-map server (`geeknik/plan-audit-map`) only ever creates
five tables: thoughts, sessions, outcomes, confidence_calibration,
learning_patterns.  The viewer you already have ships a "Raw Events" tab that
queries `raw_mcp_events`, and a JSON export option named "JSON with raw
events" — but nothing in the server ever creates or fills that table, so the
tab is permanently stuck on "(no raw_mcp_events table found)".  This module
owns that missing half.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

__all__ = [
    "desk_dir",
    "config_dir",
    "db_path",
    "bar_config_path",
    "load_bar_config",
    "save_bar_config",
    "DEFAULT_BAR_CONFIG",
    "iso_now",
    "parse_ts",
    "format_ts",
    "human_ago",
    "RawEventStore",
    "ActivityReader",
]

APP_NAME = "planauditmap-desk"

# Environment overrides (checked in this order for the data directory).
HOME_ENV_VARS = ("PLAN_AUDIT_MAP_HOME", "PLAN_AUDIT_MAP_CONFIG_DIR")
DB_ENV_VARS = ("PLAN_AUDIT_MAP_DB", "PLAN_AUDIT_MAP_MEMORY_DB")

RAW_EVENTS_TABLE = "raw_mcp_events"

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------


def desk_dir() -> Path:
    """Directory this package lives in."""
    return Path(__file__).resolve().parent


def _home() -> Path:
    # os.path.expanduser handles %USERPROFILE% on Windows and ~ everywhere else.
    return Path(os.path.expanduser("~"))


def config_dir(create: bool = False) -> Path:
    """Return ~/.plan-audit-map (or whatever PLAN_AUDIT_MAP_HOME points at)."""
    for var in HOME_ENV_VARS:
        val = os.environ.get(var)
        if val:
            p = Path(os.path.expandvars(os.path.expanduser(val)))
            if create:
                p.mkdir(parents=True, exist_ok=True)
            return p

    home = _home()
    for name in (".plan-audit-map", ".code-reasoning"):
        p = home / name
        if p.is_dir():
            return p

    p = home / ".plan-audit-map"
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    """Path of the MapThinkDo SQLite memory database."""
    for var in DB_ENV_VARS:
        val = os.environ.get(var)
        if val:
            return Path(os.path.expandvars(os.path.expanduser(val)))
    return config_dir() / "memory.db"


def bar_config_path() -> Path:
    return config_dir(create=True) / "desk-bar.json"


def _default_python() -> str:
    """Best-guess interpreter for launching sibling scripts."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return sys.executable or "python"


DEFAULT_BAR_CONFIG: Dict[str, Any] = {
    # ---- desk bar -------------------------------------------------------
    "enabled": True,
    "bar_height": 30,
    "dock_edge": "bottom",          # bottom | top
    "sit_above_taskbar": True,      # keeps a striped taskbar visible
    "opacity": 0.96,
    "bar_port": 38457,              # localhost IPC for the launcher tap
    "poll_seconds": 3,
    "activity_limit": 60,
    "autostart_with_server": True,
    # ---- SQL viewer -----------------------------------------------------
    "viewer_script": "planauditmap_viewer.py",
    "python_exe": "",               # empty -> auto-detect at launch
    "pythonw_exe": "",              # empty -> auto-detect at launch
    # ---- launcher -------------------------------------------------------
    "server_command": "",           # e.g. ["node", "C:/src/plan-audit-map/dist/index.js"]
    "log_raw_events": True,
    "provider": "",                 # auto-detected from the client env
    "transport": "stdio",
    "mirror_jsonl": True,
    "max_payload_bytes": 262144,    # truncate monster payloads before storing
    # ---- intervention paste bar -------------------------------------------
    "intervention": {
        "skills_dir": "",              # "" -> <desk>/skills, then ~/.plan-audit-map/skills
        "embedding_provider": "auto",  # auto | ollama | lmstudio | nomic | local
        "embedding_endpoint": "",      # e.g. http://127.0.0.1:11434
        "embedding_model": "nomic-embed-text",
        "top_k": 3,
        "min_score": 0.04,
        "max_chunk_chars": 1400,
        "max_message_chars": 3000,
        "min_paste_chars": 40,
        "max_paste_chars": 12000,
    },
}

_CONFIG_LOCK = threading.Lock()


def load_bar_config() -> Dict[str, Any]:
    """Load desk-bar config, merged over defaults. Never raises."""
    cfg = dict(DEFAULT_BAR_CONFIG)
    path = bar_config_path()
    try:
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg.update(loaded)
                # one-level deep merge for known nested sections so a partial
                # user edit (e.g. only "top_k") doesn't wipe the other keys
                for key in ("intervention",):
                    user = loaded.get(key)
                    base = DEFAULT_BAR_CONFIG.get(key)
                    if isinstance(user, dict) and isinstance(base, dict):
                        merged = dict(base)
                        merged.update(user)
                        cfg[key] = merged
    except Exception as exc:  # noqa: BLE001 - config must never crash startup
        print(f"[{APP_NAME}] ignoring unreadable config {path}: {exc}", file=sys.stderr)
    return cfg


def save_bar_config(cfg: Dict[str, Any]) -> Path:
    path = bar_config_path()
    with _CONFIG_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

_TS_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?\s*"
    r"(Z|[+-]\d{2}:?\d{2})?$"
)


def parse_ts(value: Any) -> Optional[datetime]:
    """Parse the several timestamp shapes that end up in the DB.

    The Node server writes `new Date().toISOString()` (…Z), SQLite defaults
    write "YYYY-MM-DD HH:MM:SS" (no zone), and some code paths write local
    time.  Sorting those as strings puts UTC 'Z' rows *before* local rows for
    the same instant, which is what makes the viewer's "recent" ordering look
    scrambled; everything funnels through here instead.
    """
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None

    m = _TS_RE.match(text)
    if not m:
        return None

    year, month, day, hour, minute, second, frac, zone = m.groups()
    micro = 0
    if frac:
        micro = int((frac + "000000")[:6])

    tzinfo: Optional[timezone] = None
    if zone:
        if zone == "Z":
            tzinfo = timezone.utc
        else:
            sign = 1 if zone[0] == "+" else -1
            bare = zone[1:].replace(":", "")
            try:
                tzinfo = timezone(sign * timedelta_from_hhmm(bare))
            except ValueError:
                tzinfo = None
    try:
        dt = datetime(int(year), int(month), int(day), int(hour), int(minute),
                      int(second), micro, tzinfo=tzinfo)
    except ValueError:
        return None

    # Naive timestamps are stored in local time by every writer we care about.
    return dt if tzinfo else dt.replace(tzinfo=None)


def timedelta_from_hhmm(bare: str):
    from datetime import timedelta

    hours = int(bare[:2] or 0)
    minutes = int(bare[2:4] or 0)
    return timedelta(hours=hours, minutes=minutes)


def _sort_key(value: Any) -> Tuple[int, float]:
    """Sort key that always puts parseable timestamps above unparseable ones
    and compares them as UTC epochs."""
    dt = parse_ts(value)
    if dt is None:
        return (0, 0.0)
    if dt.tzinfo is None:
        return (1, dt.timestamp())
    return (1, dt.timestamp())


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def format_ts(value: Any, style: str = "dt") -> str:
    """Human rendering of a DB timestamp. `style`: dt | time | date."""
    dt = parse_ts(value)
    if dt is None:
        return str(value or "—")
    local = dt.astimezone() if dt.tzinfo else dt
    if style == "time":
        return local.strftime("%H:%M:%S")
    if style == "date":
        return local.strftime("%Y-%m-%d")
    return local.strftime("%Y-%m-%d %H:%M:%S")


def human_ago(value: Any) -> str:
    dt = parse_ts(value)
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        delta = datetime.now() - dt
    else:
        delta = datetime.now(timezone.utc) - dt
    secs = int(delta.total_seconds())
    if secs < 0:
        return "just now"
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


# ---------------------------------------------------------------------------
# raw_mcp_events — the missing conversation table
# ---------------------------------------------------------------------------

CREATE_RAW_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS raw_mcp_events (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    planauditmap_session_id   TEXT,
    client                  TEXT,
    provider                TEXT,
    transport               TEXT,
    direction               TEXT,
    method                  TEXT,
    tool_name               TEXT,
    jsonrpc_id              TEXT,
    request_json            TEXT,
    response_json           TEXT,
    request_timestamp       TEXT,
    response_timestamp      TEXT,
    duration_ms             REAL,
    ok                      INTEGER,
    error                   TEXT,
    process_id              INTEGER,
    created_at              TEXT
)
"""

CREATE_RAW_EVENTS_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_raw_events_session ON raw_mcp_events(planauditmap_session_id)",
    "CREATE INDEX IF NOT EXISTS idx_raw_events_time ON raw_mcp_events(request_timestamp)",
)


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return json.dumps({"_unserialisable": str(value)[:2000]})


def _truncate(text: str, limit: int) -> str:
    if limit and len(text) > limit:
        return text[:limit] + f'…[truncated {len(text) - limit} chars]'
    return text


def extract_session_id(payload: Any) -> Optional[str]:
    """Dig a plan-audit-map session id out of a tool call or its result."""
    if isinstance(payload, dict):
        for key in ("session_id", "sessionId"):
            val = payload.get(key)
            if isinstance(val, str) and val:
                return val

        # MCP tool result: the content array lives under `result` in a normal
        # JSON-RPC response (the old code only looked at the message top
        # level, which matched sampling-style messages but never real
        # tool-call responses — so sessions were never linked to their wire
        # events).
        for holder in (payload.get("result"), payload):
            if not isinstance(holder, dict):
                continue
            content = holder.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text")
                        if isinstance(text, str):
                            try:
                                inner = json.loads(text)
                            except json.JSONDecodeError:
                                continue
                            if isinstance(inner, dict):
                                sid = inner.get("session_id") or inner.get("sessionId")
                                if isinstance(sid, str) and sid:
                                    return sid
        # tool call args
        args = payload.get("arguments") or payload.get("params")
        if isinstance(args, dict):
            sid = args.get("session_id")
            if isinstance(sid, str) and sid:
                return sid
    return None


class RawEventStore:
    """Thread-safe, multi-process-safe writer for `raw_mcp_events`.

    The Node server keeps the same database open in WAL mode, so a second
    writer is fine as long as we set a busy timeout and never hold a
    transaction open.  Every write is also mirrored to a JSONL file so the
    conversation survives even if the DB is locked, read-only or missing.
    """

    def __init__(
        self,
        path: Optional[Path] = None,
        provider: str = "",
        transport: str = "stdio",
        client: str = "",
        mirror_jsonl: bool = True,
        max_payload_bytes: int = 262144,
        enabled: bool = True,
        log=print,
    ) -> None:
        self.path = Path(path) if path else db_path()
        self.provider = provider or self._detect_provider()
        self.transport = transport
        self.client = client
        self.mirror_jsonl = mirror_jsonl
        self.max_payload_bytes = max_payload_bytes
        self.enabled = enabled
        self.log = (lambda msg: None) if log is None else log

        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._orphans: Dict[str, int] = {}  # id -> response-only row id
        self._ready = False
        self._failed = False
        self.pid = os.getpid()

    # -- lifecycle --------------------------------------------------------

    @staticmethod
    def _detect_provider() -> str:
        env = os.environ
        # 1. Explicit override always wins (the generated connection JSONs
        #    for Qwen set PLAN_AUDIT_MAP_PROVIDER=qwen-desktop).
        for var in ("PLAN_AUDIT_MAP_PROVIDER", "MAPTHINKDO_PROVIDER", "MTD_PROVIDER"):
            val = env.get(var)
            if val:
                return val.lower()
        # 2. Claude Desktop / Claude Code set recognisable env vars.
        markers = {
            "CLAUDE_DESKTOP": "claude-desktop",
            "CLAUDECODE": "claude-code",
            "ANTHROPIC_API_KEY": "anthropic",
        }
        for var, name in markers.items():
            if env.get(var):
                return name
        # 3. qwen-studio (Tauri) exports TAURI_ENV_* to every child it
        #    spawns, including node mcp-bridge.mjs and anything the bridge
        #    starts.  That marker propagates to us through the environment.
        for var in ("TAURI_ENV_PLATFORM", "TAURI_ENV_ARCH", "TAURI_ENV_FAMILY"):
            if env.get(var):
                return "qwen-desktop"
        # 4. Last resort: scan our own command line (weaker signal).
        argv = " ".join(sys.argv).lower()
        if "mcp-bridge" in argv:
            return "qwen-desktop"
        if "qwen" in argv:
            return "qwen-desktop"
        return "unknown"

    def connect(self) -> bool:
        if not self.enabled or self._failed:
            return False
        with self._lock:
            if self._conn is not None:
                return True
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(self.path), timeout=10.0,
                                       isolation_level=None,
                                       check_same_thread=False)
                # check_same_thread=False: the connection is created on the
                # main thread but log_message() runs on the pipe threads.
                # All access is serialised by self._lock, so this is safe.
                # (Without it, every insert raised "SQLite objects created in
                # a thread can only be used in that same thread" and the
                # wire tap silently wrote nothing to the DB.)
                conn.execute("PRAGMA busy_timeout = 8000")
                try:
                    conn.execute("PRAGMA journal_mode = WAL")
                except sqlite3.Error:
                    pass
                conn.executescript(CREATE_RAW_EVENTS_SQL)
                for stmt in CREATE_RAW_EVENTS_INDEXES:
                    try:
                        conn.execute(stmt)
                    except sqlite3.Error:
                        pass
                self._conn = conn
                self._ready = True
                return True
            except sqlite3.Error as exc:
                self._failed = True
                self.log(f"[{APP_NAME}] raw_mcp_events unavailable ({exc}); "
                         f"falling back to JSONL mirror")
                return False

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.Error:
                    pass
                self._conn = None

    # -- writing ----------------------------------------------------------

    def log_message(self, message: Dict[str, Any], direction: str) -> Optional[int]:
        """Record one JSON-RPC message. Returns the row id for requests."""
        if not self.enabled:
            return None
        self._mirror(message, direction)
        if not self._ready and not self.connect():
            return None

        method = message.get("method")
        msg_id = message.get("id")
        key = "" if msg_id is None else str(msg_id)
        now = iso_now()

        try:
            with self._lock:
                if direction == "request":
                    tool_name = ""
                    if method == "tools/call":
                        tool_name = (message.get("params") or {}).get("name") or ""
                    session_id = extract_session_id(message)
                    row = {
                        "planauditmap_session_id": session_id,
                        "client": self.client,
                        "provider": self.provider,
                        "transport": self.transport,
                        "direction": "request",
                        "method": method,
                        "tool_name": tool_name,
                        "jsonrpc_id": key,
                        "request_json": _truncate(_json_dumps(message),
                                                  self.max_payload_bytes),
                        "response_json": None,
                        "request_timestamp": now,
                        "response_timestamp": None,
                        "duration_ms": None,
                        "ok": None,
                        "error": None,
                        "process_id": self.pid,
                        "created_at": now,
                    }
                    return self._insert(row, key)

                # response / notification
                row = {
                    "planauditmap_session_id": extract_session_id(message),
                    "client": self.client,
                    "provider": self.provider,
                    "transport": self.transport,
                    "direction": "response" if msg_id is not None else "notification",
                    "method": method,
                    "tool_name": "",
                    "jsonrpc_id": key,
                    "request_json": None,
                    "response_json": _truncate(_json_dumps(message),
                                               self.max_payload_bytes),
                    "request_timestamp": now,
                    "response_timestamp": now,
                    "duration_ms": None,
                    "ok": 1 if "error" not in message else 0,
                    "error": _json_dumps(message["error"]) if "error" in message else None,
                    "process_id": self.pid,
                    "created_at": now,
                }

                if key and key in self._pending:
                    started = self._pending.pop(key)
                    row["planauditmap_session_id"] = (
                        row["planauditmap_session_id"] or started.get("session_id")
                    )
                    row["tool_name"] = started.get("tool_name", "")
                    row["method"] = started.get("method") or method
                    row["request_json"] = started.get("request_json")
                    row["request_timestamp"] = started.get("request_timestamp")
                    try:
                        row["duration_ms"] = round(
                            (_sort_key(now)[1] - _sort_key(
                                started.get("request_timestamp"))[1]) * 1000.0, 2
                        )
                    except Exception:  # noqa: BLE001
                        row["duration_ms"] = None
                    return self._update(started.get("row_id"), row)
                # unmatched response: remember it briefly in case its own
                # request row is committed a moment later (tap thread race)
                row_id = self._insert(row, None)
                if key and row_id is not None:
                    self._orphans[key] = row_id
                    while len(self._orphans) > 256:
                        self._orphans.pop(next(iter(self._orphans)))
                return row_id
        except Exception as exc:  # noqa: BLE001 - logging must never kill the proxy
            self.log(f"[{APP_NAME}] raw event log failed: {exc}")
            return None

    def _insert(self, row: Dict[str, Any], key: Optional[str]) -> Optional[int]:
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        sql = f"INSERT INTO {RAW_EVENTS_TABLE} ({cols}) VALUES ({marks})"
        try:
            # Race repair: the response is sometimes tapped before its own
            # request row is committed (both pipe threads log concurrently).
            # If we already hold a response-only row for this jsonrpc id,
            # fold the request half into it instead of adding a duplicate.
            if (key and row.get("direction") == "request"
                    and key in self._orphans):
                orphan_id = self._orphans.pop(key)
                update = {c: v for c, v in row.items()
                          if c not in ("id", "created_at", "direction",
                                       "response_json",
                                       "response_timestamp", "ok", "error",
                                       "duration_ms")}
                return self._update(orphan_id, update) or orphan_id
            cur = self._conn.execute(sql, tuple(row.values()))
        except sqlite3.Error as exc:
            self.log(f"[{APP_NAME}] raw event insert failed: {exc}")
            return None
        row_id = cur.lastrowid
        if key:
            self._pending[key] = {
                "row_id": row_id,
                "request_timestamp": row.get("request_timestamp"),
                "session_id": row.get("planauditmap_session_id"),
                "tool_name": row.get("tool_name", ""),
                "method": row.get("method"),
                "request_json": row.get("request_json"),
            }
        # Bound the pending map (a client that never answers shouldn't leak).
        # Drop the oldest half rather than everything: clearing the whole map
        # throws away still-in-flight requests whenever a chatty client
        # exceeds the cap (batched tool calls easily do).
        while len(self._pending) > 512:
            self._pending.pop(next(iter(self._pending)))
        return row_id

    def _update(self, row_id: Optional[int], row: Dict[str, Any]) -> Optional[int]:
        if not row_id:
            return self._insert(row, None)
        assignments = ", ".join(f"{c} = ?" for c in row)
        sql = f"UPDATE {RAW_EVENTS_TABLE} SET {assignments} WHERE id = ?"
        try:
            self._conn.execute(sql, tuple(row.values()) + (row_id,))
        except sqlite3.Error as exc:
            self.log(f"[{APP_NAME}] raw event update failed: {exc}")
            return None
        return row_id

    # -- JSONL mirror -----------------------------------------------------

    def _mirror(self, message: Dict[str, Any], direction: str) -> None:
        if not self.mirror_jsonl:
            return
        try:
            path = self.path.parent / "raw-mcp-events.jsonl"
            record = {
                "ts": iso_now(),
                "direction": direction,
                "provider": self.provider,
                "transport": self.transport,
                "session_id": extract_session_id(message),
                "message": message,
            }
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Activity feed (shared by the taskbar bar and the viewer's overview)
# ---------------------------------------------------------------------------


class ActivityReader:
    """Read-only queries against a MapThinkDo memory database."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else db_path()

    def _connect(self, readonly: bool = True) -> sqlite3.Connection:
        if readonly and self.path.exists():
            uri = f"file:{self.path.as_posix()}?mode=ro"
            try:
                conn = sqlite3.connect(uri, uri=True, timeout=5.0)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA busy_timeout = 5000")
                return conn
            except sqlite3.Error:
                pass
        conn = sqlite3.connect(str(self.path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def has_table(self, name: str) -> bool:
        if not self.path.exists():
            return False
        try:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
                    " AND name = ?",
                    (name,),
                ).fetchone()
                return row is not None
            finally:
                conn.close()
        except sqlite3.Error:
            return False

    def table_names(self) -> List[str]:
        if not self.path.exists():
            return []
        try:
            conn = self._connect()
            try:
                return [r["name"] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
                    " ORDER BY name")]
            finally:
                conn.close()
        except sqlite3.Error:
            return []

    def stats(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "db_path": str(self.path),
            "exists": self.path.exists(),
            "sessions": 0,
            "thoughts": 0,
            "outcomes": 0,
            "raw_events": 0,
            "active_session": None,
            "last_activity": None,
            "db_size_mb": 0.0,
        }
        if not self.path.exists():
            return out
        try:
            out["db_size_mb"] = round(self.path.stat().st_size / (1024 * 1024), 2)
        except OSError:
            pass
        try:
            conn = self._connect()
        except sqlite3.Error:
            return out
        try:
            def count(table: str) -> int:
                if not self.has_table(table):
                    return 0
                try:
                    return conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
                except sqlite3.Error:
                    return 0

            out["sessions"] = count("sessions")
            out["thoughts"] = count("thoughts")
            out["outcomes"] = count("outcomes")
            out["raw_events"] = count(RAW_EVENTS_TABLE)

            if self.has_table("thoughts"):
                # rowid order == insertion order; the timestamp column mixes
                # UTC "…Z" and naive local strings, so ordering by it scrambles.
                rows = conn.execute(
                    "SELECT session_id, timestamp FROM thoughts"
                    " ORDER BY rowid DESC LIMIT 20"
                ).fetchall()
                if rows:
                    newest = max(rows, key=lambda r: _sort_key(r["timestamp"]))
                    out["active_session"] = newest["session_id"]
                    out["last_activity"] = newest["timestamp"]
            if self.has_table("sessions") and out["last_activity"] is None:
                rows = conn.execute(
                    "SELECT start_time FROM sessions ORDER BY rowid DESC LIMIT 20"
                ).fetchall()
                if rows:
                    newest = max(rows, key=lambda r: _sort_key(r["start_time"]))
                    out["last_activity"] = newest["start_time"]
        except sqlite3.Error:
            pass
        finally:
            conn.close()
        return out

    def recent_thoughts(self, limit: int = 40, session_id: Optional[str] = None
                        ) -> List[Dict[str, Any]]:
        if not self.has_table("thoughts"):
            return []
        sql = ("SELECT id, session_id, thought_number, total_thoughts, timestamp,"
               " confidence, domain, objective, is_revision, branch_id,"
               " substr(COALESCE(thought, ''), 1, 240) AS snippet"
               " FROM thoughts")
        args: List[Any] = []
        if session_id:
            sql += " WHERE session_id = ?"
            args.append(session_id)
        # rowid (insertion order) — see stats() note about mixed timezones.
        sql += " ORDER BY rowid DESC LIMIT ?"
        args.append(limit)
        try:
            conn = self._connect()
            try:
                return [dict(r) for r in conn.execute(sql, args)]
            finally:
                conn.close()
        except sqlite3.Error:
            return []

    def recent_tool_calls(self, limit: int = 40) -> List[Dict[str, Any]]:
        if not self.has_table(RAW_EVENTS_TABLE):
            return []
        sql = ("SELECT id, planauditmap_session_id, direction, method, tool_name,"
               " request_timestamp, response_timestamp, duration_ms, ok, error,"
               " substr(COALESCE(request_json, ''), 1, 400) AS request_excerpt"
               " FROM raw_mcp_events"
               " WHERE direction IN ('request', 'response')"
               " ORDER BY id DESC LIMIT ?")
        try:
            conn = self._connect()
            try:
                return [dict(r) for r in conn.execute(sql, (limit,))]
            finally:
                conn.close()
        except sqlite3.Error:
            return []

    def recent_sessions(self, limit: int = 25) -> List[Dict[str, Any]]:
        if not self.has_table("sessions"):
            return []
        sql = ("SELECT s.id, s.start_time, s.end_time, s.objective, s.domain,"
               " s.goal_achieved, s.confidence_level, s.total_thoughts,"
               " s.revision_count, s.branch_count,"
               " (SELECT COUNT(*) FROM thoughts t WHERE t.session_id = s.id) AS thought_count,"
               " (SELECT MAX(t.timestamp) FROM thoughts t WHERE t.session_id = s.id) AS last_thought"
               " FROM sessions s"
               " ORDER BY s.rowid DESC LIMIT ?")
        try:
            conn = self._connect()
            try:
                return [dict(r) for r in conn.execute(sql, (limit,))]
            finally:
                conn.close()
        except sqlite3.Error:
            return []

    def recent_activity(self, limit: int = 60) -> List[Dict[str, Any]]:
        """Merged, newest-first activity feed.

        Blends three sources so the bar shows something useful even before any
        raw MCP events have been captured:
          * tool calls (raw_mcp_events)        -> "tool" / "error"
          * thoughts                            -> "thought"
          * sessions                            -> "session"
        """
        items: List[Dict[str, Any]] = []

        for row in self.recent_tool_calls(limit):
            tool = row.get("tool_name") or row.get("method") or "mcp"
            ok = row.get("ok")
            if row.get("direction") == "request":
                kind = "call"
                detail = f"→ {tool}"
            elif ok == 0:
                kind = "error"
                detail = f" {tool}"
            else:
                kind = "result"
                dur = row.get("duration_ms")
                detail = f"← {tool}" + (f"  {dur:.0f}ms" if dur else "")
            items.append({
                "kind": kind,
                "ts": row.get("response_timestamp") or row.get("request_timestamp"),
                "session": row.get("planauditmap_session_id") or "",
                "detail": detail,
                "text": _summarise_arguments(row.get("request_excerpt")),
            })

        for row in self.recent_thoughts(limit):
            tn = row.get("thought_number")
            tt = row.get("total_thoughts")
            prefix = "#{}/{}".format(tn if tn is not None else "?",
                                     tt if tt is not None else "?")
            if row.get("is_revision"):
                prefix += " rev"
            elif row.get("branch_id"):
                prefix += " branch"
            items.append({
                "kind": "thought",
                "ts": row.get("timestamp"),
                "session": row.get("session_id") or "",
                "detail": prefix,
                "text": (row.get("snippet") or "").replace("\n", " ").strip(),
            })

        for row in self.recent_sessions(limit):
            items.append({
                "kind": "session",
                "ts": row.get("start_time"),
                "session": row.get("id") or "",
                "detail": "session start",
                "text": (row.get("objective") or "").replace("\n", " ").strip()[:200],
            })

        items.sort(key=lambda i: _sort_key(i["ts"]), reverse=True)
        return items[:limit]


_ARG_RE = re.compile(r'"thought"\s*:\s*"(.*?)"', re.DOTALL)


def _summarise_arguments(excerpt: Optional[str]) -> str:
    """Pull the human-readable bit out of a stored tool-call request."""
    if not excerpt:
        return ""
    try:
        payload = json.loads(excerpt)
    except json.JSONDecodeError:
        # excerpt is a truncated JSON fragment; fall back to a regex.
        m = _ARG_RE.search(excerpt)
        if m:
            return _unescape_fragment(m.group(1))[:200]
        return excerpt[:200].replace("\n", " ")
    if isinstance(payload, dict):
        args = payload.get("params", {}).get("arguments") or payload.get("arguments") or {}
        for key in ("thought", "feedback", "outcome", "query"):
            val = args.get(key)
            if isinstance(val, str):
                return val.replace("\n", " ")[:200]
        return json.dumps(args, ensure_ascii=False, default=str)[:200]
    return str(payload)[:200]


def _unescape_fragment(fragment: str) -> str:
    try:
        return json.loads('"' + fragment + '"')
    except json.JSONDecodeError:
        return fragment
