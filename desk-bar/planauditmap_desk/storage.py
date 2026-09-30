from __future__ import annotations

import json
import socket
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Dict, Iterator, List, Optional

ISO_UTC = "%Y-%m-%dT%H:%M:%S.%f%z"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime(ISO_UTC)


def parse_ts(value: str) -> datetime:
    return datetime.strptime(value, ISO_UTC)


@dataclass
class LaunchRecord:
    id: int
    agent: str
    provider: str
    instance_key: str
    pid: Optional[int]
    command: str
    cwd: str
    venv_path: str
    project_path: str
    started_at: str
    heartbeat_at: str
    ended_at: Optional[str]
    exit_code: Optional[int]
    hostname: str
    metadata: Dict[str, Any]


class DeskDatabase:
    def __init__(self, db_path: Path | str) -> None:
        self.path = Path(db_path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    @property
    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._conn.execute("PRAGMA busy_timeout=5000;")
        return self._conn

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = self._connection
        yield conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __del__(self) -> None:
        self.close()

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_launches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT '',
                    instance_key TEXT NOT NULL UNIQUE,
                    pid INTEGER,
                    command TEXT NOT NULL DEFAULT '',
                    cwd TEXT NOT NULL DEFAULT '',
                    venv_path TEXT NOT NULL DEFAULT '',
                    project_path TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    ended_at TEXT,
                    exit_code INTEGER,
                    hostname TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_agent_launches_agent_started
                ON agent_launches(agent, started_at DESC);

                CREATE INDEX IF NOT EXISTS idx_agent_launches_ended_heartbeat
                ON agent_launches(ended_at, heartbeat_at DESC);

                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def record_launch(
        self,
        *,
        agent: str,
        provider: str = "",
        instance_key: Optional[str] = None,
        pid: Optional[int] = None,
        command: str = "",
        cwd: str = "",
        venv_path: str = "",
        project_path: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LaunchRecord:
        key = instance_key or str(uuid.uuid4())
        now = utc_now()
        host = socket.gethostname()
        meta_json = json.dumps(metadata or {}, sort_keys=True)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_launches (
                    agent, provider, instance_key, pid, command, cwd, venv_path,
                    project_path, started_at, heartbeat_at, hostname, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(instance_key) DO UPDATE SET
                    heartbeat_at=excluded.heartbeat_at,
                    ended_at=NULL,
                    exit_code=NULL,
                    pid=COALESCE(excluded.pid, agent_launches.pid),
                    command=COALESCE(NULLIF(excluded.command, ''), agent_launches.command),
                    cwd=COALESCE(NULLIF(excluded.cwd, ''), agent_launches.cwd),
                    venv_path=COALESCE(NULLIF(excluded.venv_path, ''), agent_launches.venv_path),
                    project_path=COALESCE(NULLIF(excluded.project_path, ''), agent_launches.project_path),
                    metadata_json=excluded.metadata_json
                """,
                (
                    agent,
                    provider,
                    key,
                    pid,
                    command,
                    cwd,
                    venv_path,
                    project_path,
                    now,
                    now,
                    host,
                    meta_json,
                ),
            )
            row = conn.execute(
                "SELECT * FROM agent_launches WHERE instance_key = ?",
                (key,),
            ).fetchone()
        return self._row_to_launch(row)

    def heartbeat(self, instance_key: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE agent_launches SET heartbeat_at = ? WHERE instance_key = ?",
                (utc_now(), instance_key),
            )

    def finish(self, instance_key: str, exit_code: int = 0) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE agent_launches
                SET heartbeat_at = ?, ended_at = ?, exit_code = ?
                WHERE instance_key = ?
                """,
                (now, now, exit_code, instance_key),
            )

    def get_state(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set_state(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_state(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def latest_launch_id(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM agent_launches").fetchone()
        return int(row[0] or 0)

    def unseen_launches(self, after_id: int = 0) -> List[LaunchRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_launches WHERE id > ? ORDER BY id ASC",
                (after_id,),
            ).fetchall()
        return [self._row_to_launch(row) for row in rows]

    def recent_launches(self, limit: int = 50) -> List[LaunchRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_launches ORDER BY started_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_launch(row) for row in rows]

    def active_launches(self, live_timeout_seconds: int = 75) -> List[LaunchRecord]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=live_timeout_seconds)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_launches WHERE ended_at IS NULL ORDER BY started_at ASC, id ASC"
            ).fetchall()
        result: List[LaunchRecord] = []
        for row in rows:
            if parse_ts(row["heartbeat_at"]) >= cutoff:
                result.append(self._row_to_launch(row))
        return result

    def agent_summaries(self, live_timeout_seconds: int = 75) -> List[Dict[str, Any]]:
        active_keys = {r.instance_key for r in self.active_launches(live_timeout_seconds)}
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    agent,
                    COUNT(*) AS launch_count,
                    MAX(started_at) AS last_started_at
                FROM agent_launches
                GROUP BY agent
                ORDER BY last_started_at DESC, agent ASC
                """
            ).fetchall()
        summaries: List[Dict[str, Any]] = []
        for row in rows:
            agent = row["agent"]
            active_count = self._active_count_for_agent(agent, active_keys)
            summaries.append(
                {
                    "agent": agent,
                    "launch_count": int(row["launch_count"]),
                    "active_count": active_count,
                    "last_started_at": row["last_started_at"],
                }
            )
        return summaries

    def _active_count_for_agent(self, agent: str, active_keys: set[str]) -> int:
        if not active_keys:
            return 0
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM agent_launches
                WHERE agent = ? AND instance_key IN ({})
                """.format(
                    ",".join("?" for _ in active_keys)
                ),
                (agent, *active_keys),
            ).fetchone()
        return int(row[0] or 0)

    @staticmethod
    def _row_to_launch(row: sqlite3.Row) -> LaunchRecord:
        return LaunchRecord(
            id=int(row["id"]),
            agent=row["agent"],
            provider=row["provider"],
            instance_key=row["instance_key"],
            pid=row["pid"],
            command=row["command"],
            cwd=row["cwd"],
            venv_path=row["venv_path"],
            project_path=row["project_path"],
            started_at=row["started_at"],
            heartbeat_at=row["heartbeat_at"],
            ended_at=row["ended_at"],
            exit_code=row["exit_code"],
            hostname=row["hostname"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )
