#!/usr/bin/env python3
"""
MapThinkDo Viewer — Tkinter desktop app for inspecting MapThinkDo reasoning sessions.

Reads the MapThinkDo SQLite memory database (normally ~/.plan-audit-map/memory.db)
and provides session browsing, thought timeline, detail inspection, FTS search,
branch/revision graph visualization, analytics, bookmarks, and Markdown/JSON export.

Usage:
    python planauditmap_viewer.py                        # auto-detect DB
    python planauditmap_viewer.py /path/to/memory.db     # explicit DB path
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import textwrap
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import (
    BOTH,
    END,
    HORIZONTAL,
    LEFT,
    NONE,
    RIGHT,
    VERTICAL,
    WORD,
    X,
    Y,
)
from tkinter import filedialog, messagebox, simpledialog
from tkinter import ttk
from typing import Any, Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

JSON_COLUMNS_THOUGHTS = [
    "context",
    "tags",
    "patterns_detected",
    "similar_thoughts",
    "context_trace",
]

JSON_COLUMNS_SESSIONS = [
    "cognitive_roles_used",
    "lessons_learned",
    "successful_strategies",
    "failed_approaches",
    "tags",
]

JSON_COLUMNS_PATTERNS = [
    "domains",
    "insights",
]

APP_TITLE = "MapThinkDo Viewer"
DEFAULT_WIN_SIZE = "1500x900"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def default_db_candidates() -> List[Path]:
    """Return ordered list of likely memory.db locations."""
    candidates = []
    home = Path.home()
    candidates.append(home / ".plan-audit-map" / "memory.db")
    candidates.append(home / ".code-reasoning" / "memory.db")
    # also check XDG-style
    xdg_data = os.environ.get("XDG_DATA_HOME", "")
    if xdg_data:
        candidates.append(Path(xdg_data) / "plan-audit-map" / "memory.db")
    # explicit env override (same vars the desk bar honours)
    for var in ("PLAN_AUDIT_MAP_DB", "PLAN_AUDIT_MAP_MEMORY_DB"):
        val = os.environ.get(var)
        if val:
            candidates.insert(0, Path(os.path.expandvars(os.path.expanduser(val))))
    return candidates


def parse_db_ts(value: Any):
    """Best-effort timestamp parser for the shapes stored in memory.db.

    The Node server writes ISO-8601 UTC ("…Z"), SQLite defaults write
    "YYYY-MM-DD HH:MM:SS" (no zone).  Sorting those as strings mixes zones
    and scrambles "recent" ordering, so everything user-facing sorts through
    this instead.  Returns an aware datetime (naive values are assumed local)
    or None.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(" ", "T", 1) if " " in text[:11] else text
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()  # interpret naive local timestamps as local
    return dt


def ts_sort_key(value: Any):
    """Sort key: parseable timestamps first (newest later), junk first."""
    dt = parse_db_ts(value)
    if dt is None:
        return (0, 0.0)
    return (1, dt.timestamp())


def safe_json(value: Any, fallback: Any = None) -> Any:
    """Parse JSON string safely; return fallback on failure."""
    if value is None:
        return fallback
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return fallback
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return fallback


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert sqlite3.Row to plain dict."""
    return {k: row[k] for k in row.keys()}


def format_timestamp(ts: Optional[str]) -> str:
    """Truncate ISO timestamp to readable form."""
    if not ts:
        return ""
    return ts[:19].replace("T", " ")


def bool_display(val: Any) -> str:
    """Display boolean-ish value."""
    if val is None:
        return "—"
    try:
        return "" if int(val) else ""
    except (ValueError, TypeError):
        return "—"


def clean_fts_query(q: str) -> str:
    """Sanitize user query for FTS5 MATCH."""
    terms = re.findall(r"[A-Za-z0-9_]+", q)
    if not terms:
        return ""
    return " OR ".join(terms)


# ──────────────────────────────────────────────────────────────────────────────
# Database Layer
# ──────────────────────────────────────────────────────────────────────────────

class MapThinkDoDB:
    """Read-only access to the MapThinkDo SQLite memory database."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.conn: Optional[sqlite3.Connection] = None
        self.is_readonly = False

    # ── open / close ──────────────────────────────────────────────────────

    def open(self) -> None:
        """Open the database, attempting read-write first, falling back to read-only."""
        try:
            self.conn = sqlite3.connect(str(self.path))
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute("PRAGMA busy_timeout = 3000")
            self.is_readonly = False
        except (sqlite3.Error, sqlite3.OperationalError):
            uri = f"file:{self.path}?mode=ro"
            try:
                self.conn = sqlite3.connect(uri, uri=True)
            except sqlite3.OperationalError:
                self.conn = sqlite3.connect(str(self.path))
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute("PRAGMA busy_timeout = 3000")
            try:
                self.conn.execute("PRAGMA query_only = ON")
            except sqlite3.Error:
                pass
            self.is_readonly = True

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def is_open(self) -> bool:
        return self.conn is not None

    # ── introspection ─────────────────────────────────────────────────────

    def has_table(self, name: str) -> bool:
        row = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name=?",
            (name,),
        ).fetchone()
        return row is not None

    def table_names(self) -> List[str]:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    # ── sessions ──────────────────────────────────────────────────────────

    def get_sessions(self) -> List[Dict[str, Any]]:
        if not self.has_table("sessions"):
            return []
        sql = """
        SELECT
            s.id,
            s.start_time,
            s.end_time,
            s.objective,
            s.domain,
            s.goal_achieved,
            s.confidence_level,
            s.total_thoughts,
            s.revision_count,
            s.branch_count,
            s.effectiveness_score,
            s.lessons_learned,
            s.successful_strategies,
            s.failed_approaches,
            s.tags,
            s.cognitive_roles_used,
            s.metacognitive_interventions,
            s.initial_complexity,
            s.final_complexity,
            s.created_at,
            COUNT(t.id) AS actual_thought_count,
            MIN(t.timestamp) AS first_thought_time,
            MAX(t.timestamp) AS last_thought_time
        FROM sessions s
        LEFT JOIN thoughts t ON t.session_id = s.id
        GROUP BY s.id
        """
        try:
            rows = [row_to_dict(r) for r in self.conn.execute(sql)]
        except sqlite3.Error:
            return []
        # Sort in Python: the timestamp column mixes UTC "…Z" and naive
        # local strings, so SQL string ordering scrambles the list.
        rows.sort(
            key=lambda s: ts_sort_key(
                s.get("start_time") or s.get("first_thought_time") or ""
            ),
            reverse=True,
        )
        return rows

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        sql = "SELECT * FROM sessions WHERE id = ?"
        row = self.conn.execute(sql, (session_id,)).fetchone()
        return row_to_dict(row) if row else None

    def get_orphan_session_ids(self) -> List[str]:
        if not self.has_table("thoughts"):
            return []
        sql = """
        SELECT DISTINCT session_id
        FROM thoughts
        WHERE session_id NOT IN (SELECT id FROM sessions)
        ORDER BY session_id
        """
        try:
            return [r["session_id"] for r in self.conn.execute(sql)]
        except sqlite3.Error:
            return []

    def get_synthetic_session(self, session_id: str) -> Dict[str, Any]:
        """Build a synthetic session entry from thoughts when sessions table
        lacks a row."""
        row = self.conn.execute(
            """
            SELECT
                MIN(timestamp) AS start_time,
                MAX(timestamp) AS end_time,
                COUNT(*) AS actual_thought_count,
                SUM(CASE WHEN is_revision THEN 1 ELSE 0 END) AS revision_count,
                SUM(CASE WHEN branch_id IS NOT NULL THEN 1 ELSE 0 END) AS branch_count,
                AVG(confidence) AS confidence_level
            FROM thoughts WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

        return {
            "id": session_id,
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "objective": "(orphan session — no sessions row)",
            "domain": "",
            "goal_achieved": 0,
            "confidence_level": row["confidence_level"] or 0.5,
            "total_thoughts": row["actual_thought_count"],
            "revision_count": row["revision_count"],
            "branch_count": row["branch_count"],
            "effectiveness_score": None,
            "actual_thought_count": row["actual_thought_count"],
            "first_thought_time": row["start_time"],
            "last_thought_time": row["end_time"],
            "is_orphan": True,
        }

    # ── thoughts ──────────────────────────────────────────────────────────

    def get_thoughts(self, session_id: str) -> List[Dict[str, Any]]:
        if not self.has_table("thoughts"):
            return []
        sql = """
        SELECT *
        FROM thoughts
        WHERE session_id = ?
        ORDER BY thought_number ASC, timestamp ASC
        """
        try:
            rows = self.conn.execute(sql, (session_id,)).fetchall()
        except sqlite3.Error:
            return []
        return [self._decode_thought(row_to_dict(r)) for r in rows]

    def get_thought(self, thought_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM thoughts WHERE id = ?", (thought_id,)
        ).fetchone()
        return self._decode_thought(row_to_dict(row)) if row else None

    def _decode_thought(self, d: Dict[str, Any]) -> Dict[str, Any]:
        for col in JSON_COLUMNS_THOUGHTS:
            key = col + "_parsed"
            fallback = {} if col == "context" else []
            d[key] = safe_json(d.get(col), fallback)
        # coerce booleans
        for bcol in ("is_revision", "next_thought_needed", "needs_more_thoughts", "success"):
            if bcol in d and d[bcol] is not None:
                d[bcol + "_bool"] = bool(d[bcol])
            else:
                d[bcol + "_bool"] = False
        return d

    # ── outcomes ──────────────────────────────────────────────────────────

    def get_outcomes_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        if not self.has_table("outcomes"):
            return []
        sql = """
        SELECT o.*, t.thought_number, t.thought
        FROM outcomes o
        LEFT JOIN thoughts t ON t.id = o.thought_id
        WHERE o.session_id = ?
        ORDER BY o.recorded_at DESC
        """
        try:
            return [row_to_dict(r) for r in self.conn.execute(sql, (session_id,))]
        except sqlite3.Error:
            return []

    def get_outcomes_for_thought(self, thought_id: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT * FROM outcomes
        WHERE thought_id = ?
        ORDER BY recorded_at DESC
        """
        return [row_to_dict(r) for r in self.conn.execute(sql, (thought_id,))]

    # ── calibration ───────────────────────────────────────────────────────

    def get_calibration(self) -> List[Dict[str, Any]]:
        if not self.has_table("confidence_calibration"):
            return []
        sql = """
        SELECT domain, predicted_bucket, actual_success_rate,
               sample_size, calibration_error, last_updated
        FROM confidence_calibration
        ORDER BY domain, predicted_bucket
        """
        return [row_to_dict(r) for r in self.conn.execute(sql)]

    # ── learning patterns ─────────────────────────────────────────────────

    def get_learning_patterns(self) -> List[Dict[str, Any]]:
        if not self.has_table("learning_patterns"):
            return []
        sql = """
        SELECT pattern_type, pattern_signature, success_count,
               failure_count, success_rate, avg_confidence,
               domains, first_seen, last_seen, insights
        FROM learning_patterns
        ORDER BY success_rate DESC, success_count DESC
        """
        return [row_to_dict(r) for r in self.conn.execute(sql)]

    # ── raw MCP events ────────────────────────────────────────────────────

    def has_raw_events(self) -> bool:
        return self.has_table("raw_mcp_events")

    def get_raw_events_for_session(self, planauditmap_session_id: str) -> List[Dict[str, Any]]:
        if not self.has_raw_events():
            return []
        # id (insertion order) — request_timestamp mixes zones/formats.
        sql = """
        SELECT * FROM raw_mcp_events
        WHERE planauditmap_session_id = ?
        ORDER BY id ASC
        """
        try:
            return [row_to_dict(r) for r in self.conn.execute(sql, (planauditmap_session_id,))]
        except sqlite3.Error:
            return []

    def get_recent_raw_events(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Newest wire events across all sessions (viewer fallback view)."""
        if not self.has_raw_events():
            return []
        try:
            rows = [
                row_to_dict(r)
                for r in self.conn.execute(
                    "SELECT * FROM raw_mcp_events ORDER BY id DESC LIMIT ?", (limit,)
                )
            ]
        except sqlite3.Error:
            return []
        rows.reverse()  # oldest -> newest for transcript rendering
        return rows

    def get_raw_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        if not self.has_raw_events():
            return None
        row = self.conn.execute(
            "SELECT * FROM raw_mcp_events WHERE id = ?", (event_id,)
        ).fetchone()
        return row_to_dict(row) if row else None

    # ── bookmarks ─────────────────────────────────────────────────────────

    def has_bookmarks_table(self) -> bool:
        return self.has_table("viewer_bookmarks")

    def ensure_bookmarks_table(self) -> None:
        """Create bookmarks table if it doesn't exist (safe write)."""
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS viewer_bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                thought_id TEXT,
                label TEXT,
                note TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def add_bookmark(
        self, session_id: str, thought_id: Optional[str], label: str, note: str
    ) -> int:
        if self.is_readonly:
            raise sqlite3.OperationalError("Attempt to write to a read-only database connection.")
        self.ensure_bookmarks_table()
        cur = self.conn.execute(
            """
            INSERT INTO viewer_bookmarks (session_id, thought_id, label, note, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, thought_id, label, note, datetime.now().isoformat()),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_bookmarks(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.has_bookmarks_table():
            return []
        if session_id:
            sql = "SELECT * FROM viewer_bookmarks WHERE session_id = ? ORDER BY created_at DESC"
            return [row_to_dict(r) for r in self.conn.execute(sql, (session_id,))]
        else:
            sql = "SELECT * FROM viewer_bookmarks ORDER BY created_at DESC"
            return [row_to_dict(r) for r in self.conn.execute(sql)]

    def delete_bookmark(self, bookmark_id: int) -> None:
        if self.is_readonly:
            raise sqlite3.OperationalError("Attempt to write to a read-only database connection.")
        if not self.has_bookmarks_table():
            return
        self.conn.execute("DELETE FROM viewer_bookmarks WHERE id = ?", (bookmark_id,))
        self.conn.commit()

    # ── search ────────────────────────────────────────────────────────────

    def search_fts(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        if self.has_table("thoughts_fts"):
            cleaned = clean_fts_query(query)
            if cleaned:
                try:
                    sql = """
                    SELECT
                        t.id, t.session_id, t.thought_number, t.total_thoughts,
                        t.timestamp, t.domain, t.objective,
                        snippet(thoughts_fts, 0, '[', ']', '...', 24) AS snippet,
                        bm25(thoughts_fts) AS rank
                    FROM thoughts_fts
                    JOIN thoughts t ON thoughts_fts.rowid = t.rowid
                    WHERE thoughts_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """
                    return [
                        row_to_dict(r)
                        for r in self.conn.execute(sql, (cleaned, limit))
                    ]
                except sqlite3.Error:
                    pass

        # fallback LIKE search
        sql = """
        SELECT
            id, session_id, thought_number, total_thoughts,
            timestamp, domain, objective,
            thought AS snippet
        FROM thoughts
        WHERE thought LIKE ?
        ORDER BY timestamp DESC
        LIMIT ?
        """
        return [
            row_to_dict(r)
            for r in self.conn.execute(sql, (f"%{query}%", limit))
        ]

    # ── stats ─────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}
        try:
            stats["total_sessions"] = self.conn.execute(
                "SELECT COUNT(*) AS c FROM sessions"
            ).fetchone()["c"]
        except sqlite3.Error:
            stats["total_sessions"] = 0
        try:
            stats["total_thoughts"] = self.conn.execute(
                "SELECT COUNT(*) AS c FROM thoughts"
            ).fetchone()["c"]
        except sqlite3.Error:
            stats["total_thoughts"] = 0
        try:
            stats["total_outcomes"] = self.conn.execute(
                "SELECT COUNT(*) AS c FROM outcomes"
            ).fetchone()["c"]
        except sqlite3.Error:
            stats["total_outcomes"] = 0
        try:
            stats["db_size_mb"] = round(
                os.path.getsize(str(self.path)) / (1024 * 1024), 2
            )
        except OSError:
            stats["db_size_mb"] = 0
        return stats


# ──────────────────────────────────────────────────────────────────────────────
# Session Browser (Left Pane)
# ──────────────────────────────────────────────────────────────────────────────

class SessionBrowser(ttk.Frame):
    """Treeview listing all sessions with summary columns."""

    COLUMNS = ("start", "domain", "thoughts", "rev", "br", "conf", "goal")

    def __init__(self, parent, on_select=None, on_double_click=None):
        super().__init__(parent)
        self.on_select_cb = on_select
        self.on_double_click_cb = on_double_click
        self.sessions: List[Dict[str, Any]] = []
        self._build()

    def _build(self):
        # header
        hdr = ttk.Frame(self)
        hdr.pack(fill=X)
        ttk.Label(hdr, text="Sessions", font=("", 12, "bold")).pack(side=LEFT, padx=4)
        self.count_label = ttk.Label(hdr, text="", foreground="gray")
        self.count_label.pack(side=RIGHT, padx=4)

        # tree
        self.tree = ttk.Treeview(
            self,
            columns=self.COLUMNS,
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Session / Objective")
        self.tree.heading("start", text="Started")
        self.tree.heading("domain", text="Domain")
        self.tree.heading("thoughts", text="T")
        self.tree.heading("rev", text="R")
        self.tree.heading("br", text="B")
        self.tree.heading("conf", text="Conf")
        self.tree.heading("goal", text="Goal")

        self.tree.column("#0", width=240, minwidth=120)
        self.tree.column("start", width=130, minwidth=80)
        self.tree.column("domain", width=100, minwidth=60)
        self.tree.column("thoughts", width=35, minwidth=30, anchor="center")
        self.tree.column("rev", width=35, minwidth=30, anchor="center")
        self.tree.column("br", width=35, minwidth=30, anchor="center")
        self.tree.column("conf", width=50, minwidth=40, anchor="center")
        self.tree.column("goal", width=40, minwidth=30, anchor="center")

        self.tree.pack(fill=BOTH, expand=True)

        # scrollbar
        sb = ttk.Scrollbar(self.tree, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double)

    def _on_select(self, _event=None):
        if self.on_select_cb:
            sel = self.tree.selection()
            if sel:
                self.on_select_cb(sel[0])

    def _on_double(self, _event=None):
        if self.on_double_click_cb:
            sel = self.tree.selection()
            if sel:
                self.on_double_click_cb(sel[0])

    def load(self, sessions: List[Dict[str, Any]]):
        self.tree.delete(*self.tree.get_children())
        self.sessions = sessions
        for s in sessions:
            sid = s["id"]
            label = (s.get("objective") or s.get("id") or "?")[:120]
            start = format_timestamp(s.get("start_time") or s.get("first_thought_time"))
            domain = (s.get("domain") or "")[:30]
            tcount = s.get("actual_thought_count") or s.get("total_thoughts") or 0
            rcount = s.get("revision_count") or 0
            bcount = s.get("branch_count") or 0
            conf = s.get("confidence_level")
            conf_s = f"{conf:.2f}" if conf is not None else "—"
            goal = bool_display(s.get("goal_achieved"))

            tags = []
            if s.get("is_orphan"):
                tags.append("orphan")
            if s.get("goal_achieved"):
                tags.append("achieved")

            self.tree.insert(
                "",
                END,
                iid=sid,
                text=label,
                values=(start, domain, tcount, rcount, bcount, conf_s, goal),
                tags=tuple(tags),
            )

        self.tree.tag_configure("orphan", foreground="#b0b0b0")
        self.tree.tag_configure("achieved", foreground="#2a7d2a")
        self.count_label.config(text=f"{len(sessions)} sessions")

    def get_selected_id(self) -> Optional[str]:
        sel = self.tree.selection()
        return sel[0] if sel else None


# ──────────────────────────────────────────────────────────────────────────────
# Thought Timeline (Middle Pane)
# ──────────────────────────────────────────────────────────────────────────────

class ThoughtTimeline(ttk.Frame):
    """Listbox showing the thought timeline for a selected session."""

    def __init__(self, parent, on_select=None):
        super().__init__(parent)
        self.on_select_cb = on_select
        self.thoughts: List[Dict[str, Any]] = []
        # Row r of the listbox shows self.thoughts[self._visible[r]].
        # When the quick filter is active only a subset is visible, so every
        # index coming out of the listbox must be mapped through _visible
        # (the old code indexed self.thoughts directly and showed the wrong
        # thought after any search).
        self._visible: List[int] = []
        self._build()

    def _build(self):
        hdr = ttk.Frame(self)
        hdr.pack(fill=X)
        ttk.Label(hdr, text="Timeline", font=("", 12, "bold")).pack(side=LEFT, padx=4)
        self.count_label = ttk.Label(hdr, text="", foreground="gray")
        self.count_label.pack(side=RIGHT, padx=4)

        # listbox with monospace font
        self.listbox = tk.Listbox(
            self,
            font=("Menlo", 11),
            selectmode="browse",
            activestyle="none",
        )
        self.listbox.pack(fill=BOTH, expand=True)

        sb = ttk.Scrollbar(self.listbox, orient=VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)

        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        # search bar at bottom
        sf = ttk.Frame(self)
        sf.pack(fill=X, pady=(4, 0))
        self.search_var = tk.StringVar()
        ttk.Entry(sf, textvariable=self.search_var).pack(side=LEFT, fill=X, expand=True)
        ttk.Button(sf, text="", width=3, command=self._quick_search).pack(side=RIGHT)

    def _on_select(self, _event=None):
        if self.on_select_cb:
            sel = self.listbox.curselection()
            if sel and sel[0] < len(self._visible):
                self.on_select_cb(self.thoughts[self._visible[sel[0]]])

    def clear_filter(self) -> None:
        self.search_var.set("")
        self._redraw()

    def _quick_search(self):
        q = self.search_var.get().strip().lower()
        if not q:
            self._redraw()
            return
        self.listbox.delete(0, END)
        self._visible = [
            i for i, t in enumerate(self.thoughts)
            if q in (t.get("thought") or "").lower()
            or q in str(t.get("thought_number") or "").lower()
        ]
        for i in self._visible:
            self.listbox.insert(END, self._format_thought(self.thoughts[i], i))
        self.count_label.config(
            text=f"{len(self._visible)}/{len(self.thoughts)} thoughts"
        )

    @staticmethod
    def badge_for(t: Dict[str, Any]) -> str:
        if t.get("is_revision_bool"):
            rev = t.get("revises_thought", "?")
            return f"REV→{rev}"
        bid = t.get("branch_id")
        if bid:
            bfrom = t.get("branch_from_thought", "?")
            # truncate long branch ids
            short_bid = str(bid)[:12]
            return f"BR:{short_bid}←{bfrom}"
        if not t.get("next_thought_needed_bool"):
            return "DONE"
        return "THINK"

    def _format_thought(self, t: Dict[str, Any], idx: int) -> str:
        badge = self.badge_for(t)
        conf = t.get("confidence")
        conf_s = f"{conf:.2f}" if conf is not None else " -- "
        tn = t.get("thought_number", idx + 1)
        tt = t.get("total_thoughts", "?")
        text = (t.get("thought") or "").replace("\n", " ")
        return f"#{tn:>3}/{tt:<3} {badge:<14} c={conf_s}  {text[:130]}"

    def load(self, thoughts: List[Dict[str, Any]]):
        self.thoughts = thoughts
        self._redraw()

    def _redraw(self):
        self.listbox.delete(0, END)
        self._visible = list(range(len(self.thoughts)))
        for i, t in enumerate(self.thoughts):
            self.listbox.insert(END, self._format_thought(t, i))
        self.count_label.config(text=f"{len(self.thoughts)} thoughts")

    def clear(self):
        self.thoughts = []
        self._visible = []
        self.listbox.delete(0, END)
        self.count_label.config(text="")

    def get_selected_index(self) -> int:
        """Thought index (not row) of the current selection, or -1."""
        sel = self.listbox.curselection()
        if sel and sel[0] < len(self._visible):
            return self._visible[sel[0]]
        return -1

    def select_index(self, idx: int):
        """Select thought `idx`; resets the filter if it is hidden by it."""
        if not (0 <= idx < len(self.thoughts)):
            return
        if idx not in self._visible:
            self.clear_filter()
        try:
            row = self._visible.index(idx)
        except ValueError:
            return
        self.listbox.selection_clear(0, END)
        self.listbox.selection_set(row)
        self.listbox.activate(row)
        self.listbox.see(row)


# ──────────────────────────────────────────────────────────────────────────────
# Detail Notebook (Right Pane)
# ──────────────────────────────────────────────────────────────────────────────

class DetailNotebook(ttk.Frame):
    """Multi-tab detail view for a single thought."""

    def __init__(self, parent, db: Optional[MapThinkDoDB] = None):
        super().__init__(parent)
        self.db = db
        self._current_thought: Optional[Dict[str, Any]] = None
        self._build()

    def _build(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=BOTH, expand=True)

        # Tab 1 — Thought text
        self.thought_text = tk.Text(
            self.notebook, wrap=WORD, font=("", 12), padx=10, pady=10
        )
        self.notebook.add(self.thought_text, text="Thought")

        # Tab 2 — Metadata JSON
        self.meta_text = tk.Text(
            self.notebook, wrap="none", font=("Menlo", 10), padx=8, pady=8
        )
        self.notebook.add(self.meta_text, text="Metadata")

        # Tab 3 — Output
        self.output_text = tk.Text(
            self.notebook, wrap="none", font=("Menlo", 10), padx=8, pady=8
        )
        self.notebook.add(self.output_text, text="Output")

        # Tab 4 — Outcomes
        self.outcome_text = tk.Text(
            self.notebook, wrap=WORD, font=("Menlo", 10), padx=8, pady=8
        )
        self.notebook.add(self.outcome_text, text="Outcomes")

        # Tab 5 — Raw row
        self.raw_text = tk.Text(
            self.notebook, wrap="none", font=("Menlo", 10), padx=8, pady=8
        )
        self.notebook.add(self.raw_text, text="Raw Row")

        # Tab 6 — Context trace
        self.trace_text = tk.Text(
            self.notebook, wrap="none", font=("Menlo", 10), padx=8, pady=8
        )
        self.notebook.add(self.trace_text, text="Context Trace")

    def _clear_all(self):
        for w in [
            self.thought_text,
            self.meta_text,
            self.output_text,
            self.outcome_text,
            self.raw_text,
            self.trace_text,
        ]:
            w.delete("1.0", END)

    def show_thought(self, thought: Dict[str, Any]):
        self._current_thought = thought
        self._clear_all()

        # ── Tab 1: Thought ────────────────────────────────────────────────
        badge = ThoughtTimeline.badge_for(thought)
        header_lines = [
            f"Thought {thought.get('thought_number', '?')} / {thought.get('total_thoughts', '?')}",
            f"Session: {thought.get('session_id', '')}",
            f"Timestamp: {thought.get('timestamp', '')}",
            f"Type: {badge}",
            f"ID: {thought.get('id', '')}",
            f"Confidence: {thought.get('confidence', '—')}",
            f"Domain: {thought.get('domain', '—')}",
            f"Objective: {thought.get('objective', '—')}",
            f"Complexity: {thought.get('complexity', '—')}",
            f"Success: {bool_display(thought.get('success'))}",
            f"Effectiveness: {thought.get('effectiveness_score', '—')}",
            "",
            "─" * 60,
            "",
        ]
        self.thought_text.insert("1.0", "\n".join(header_lines))
        self.thought_text.insert(END, thought.get("thought", "(empty)"))

        # ── Tab 2: Metadata ───────────────────────────────────────────────
        meta = {}
        skip = {"thought", "output", "context_trace_parsed"}
        for k, v in thought.items():
            if k in skip:
                continue
            if k.endswith("_parsed"):
                continue
            if k.endswith("_bool"):
                continue
            meta[k] = v
        self.meta_text.insert("1.0", json.dumps(meta, indent=2, default=str))

        # ── Tab 3: Output ─────────────────────────────────────────────────
        output = thought.get("output")
        if output:
            parsed = safe_json(output, None)
            if parsed is not None and parsed != output:
                self.output_text.insert(
                    "1.0", json.dumps(parsed, indent=2, default=str)
                )
            else:
                self.output_text.insert("1.0", str(output))
        else:
            self.output_text.insert(
                "1.0",
                "No persisted output in thoughts.output column.\n\n"
                "For raw MCP response capture (e.g. cognitive_state, hypothesis_ledger),\n"
                "use the raw_mcp_events middleware side table.\n\n"
                "If this Grok session was truncated in the UI, the full response\n"
                "lives in the middleware wire log, not here.",
            )

        # ── Tab 4: Outcomes ───────────────────────────────────────────────
        if self.db:
            outcomes = self.db.get_outcomes_for_thought(thought["id"])
            if outcomes:
                self.outcome_text.insert(
                    "1.0", json.dumps(outcomes, indent=2, default=str)
                )
            else:
                self.outcome_text.insert("1.0", "No outcome feedback recorded.")
        else:
            self.outcome_text.insert("1.0", "(no database connection)")

        # ── Tab 5: Raw Row ────────────────────────────────────────────────
        clean = {}
        for k, v in thought.items():
            if k.endswith("_parsed") or k.endswith("_bool"):
                continue
            clean[k] = v
        self.raw_text.insert("1.0", json.dumps(clean, indent=2, default=str))

        # ── Tab 6: Context Trace ──────────────────────────────────────────
        trace = thought.get("context_trace_parsed")
        if trace:
            self.trace_text.insert("1.0", json.dumps(trace, indent=2, default=str))
        else:
            self.trace_text.insert("1.0", "No context trace recorded.")

    def clear(self):
        self._current_thought = None
        self._clear_all()


# ──────────────────────────────────────────────────────────────────────────────
# Branch / Revision Graph Canvas
# ──────────────────────────────────────────────────────────────────────────────

class GraphCanvas(tk.Canvas):
    """Draw reasoning topology: nodes as thoughts, edges as branches/revisions."""

    NODE_W = 48
    NODE_H = 28
    LANE_H = 72
    X_SPACING = 110
    MARGIN = 50
    COLORS = {
        "linear": "#3b82f6",
        "revision": "#ef4444",
        "branch": "#f59e0b",
        "done": "#22c55e",
        "edge_revision": "#ef4444",
        "edge_branch": "#3b82f6",
        "bg": "#1e1e2e",
        "text": "#e0e0e0",
        "node_text": "#ffffff",
    }

    def __init__(self, parent, on_node_click=None):
        super().__init__(parent, bg=self.COLORS["bg"], highlightthickness=0)
        self.on_node_click = on_node_click
        self.thoughts: List[Dict[str, Any]] = []
        self.node_items: Dict[int, Tuple[int, int, int, int, str]] = {}  # thought_number -> (x1,y1,x2,y2,item)
        self.edge_items: List[int] = []
        self.bind("<Button-1>", self._on_click)
        self.bind("<Configure>", lambda e: self._redraw())

    def load(self, thoughts: List[Dict[str, Any]]):
        self.thoughts = thoughts
        self._redraw()

    def _redraw(self, *_):
        self.delete("all")
        self.node_items.clear()
        self.edge_items.clear()
        if not self.thoughts:
            return

        # assign lanes
        branch_lanes: Dict[str, int] = {}
        next_lane = 1
        lane_assignments: Dict[int, int] = {}  # thought_number -> lane

        for t in self.thoughts:
            tn = t.get("thought_number")
            if not isinstance(tn, int) or tn < 1:
                continue  # malformed row: skip rather than crash on (tn - 1)
            bid = t.get("branch_id")
            if bid:
                bid_str = str(bid)
                if bid_str not in branch_lanes:
                    branch_lanes[bid_str] = next_lane
                    next_lane += 1
                lane_assignments[tn] = branch_lanes[bid_str]
            else:
                lane_assignments[tn] = 0

        max_lane = max(lane_assignments.values()) if lane_assignments else 0
        w = self.winfo_width()
        h = self.winfo_height()

        # draw edges first (under nodes)
        for t in self.thoughts:
            tn = t.get("thought_number", 0)

            # revision edge
            if t.get("is_revision_bool") and t.get("revises_thought"):
                rev = t["revises_thought"]
                if rev in lane_assignments:
                    self._draw_edge(rev, lane_assignments[rev], tn, lane_assignments[tn],
                                    self.COLORS["edge_revision"], dashed=True, label="rev")

            # branch edge
            bid = t.get("branch_id")
            bfrom = t.get("branch_from_thought")
            if bid and bfrom is not None and bfrom in lane_assignments:
                self._draw_edge(bfrom, lane_assignments[bfrom], tn, lane_assignments[tn],
                                self.COLORS["edge_branch"], dashed=False,
                                label=str(bid)[:8])

        # draw nodes
        for t in self.thoughts:
            tn = t.get("thought_number")
            if not isinstance(tn, int) or tn < 1 or tn not in lane_assignments:
                continue
            lane = lane_assignments.get(tn, 0)
            x = self.MARGIN + (tn - 1) * self.X_SPACING
            y = self.MARGIN + lane * self.LANE_H

            # choose color
            if t.get("is_revision_bool"):
                color = self.COLORS["revision"]
            elif t.get("branch_id"):
                color = self.COLORS["branch"]
            elif not t.get("next_thought_needed_bool"):
                color = self.COLORS["done"]
            else:
                color = self.COLORS["linear"]

            # draw node
            x1, y1, x2, y2 = x - self.NODE_W // 2, y - self.NODE_H // 2, x + self.NODE_W // 2, y + self.NODE_H // 2
            item = self.create_rectangle(
                x1, y1, x2, y2,
                fill=color, outline="", tags=("node",),
            )
            # rounded corners approximation
            self.create_text(
                x, y,
                text=f"#{tn}", fill=self.COLORS["node_text"],
                font=("Menlo", 9, "bold"), tags=("node",),
            )
            self.node_items[tn] = (x1, y1, x2, y2, f"#{tn}")

        # adjust scroll region
        needed_w = self.MARGIN + max(t.get("thought_number", 0) for t in self.thoughts) * self.X_SPACING + self.MARGIN
        needed_h = self.MARGIN + (max_lane + 1) * self.LANE_H + self.MARGIN
        self.config(scrollregion=(0, 0, max(needed_w, w), max(needed_h, h)))

    def _draw_edge(self, from_tn: int, from_lane: int, to_tn: int, to_lane: int,
                   color: str, dashed: bool = False, label: str = ""):
        x1 = self.MARGIN + (from_tn - 1) * self.X_SPACING + self.NODE_W // 2
        y1 = self.MARGIN + from_lane * self.LANE_H
        x2 = self.MARGIN + (to_tn - 1) * self.X_SPACING - self.NODE_W // 2
        y2 = self.MARGIN + to_lane * self.LANE_H

        dash = (6, 4) if dashed else None
        self.create_line(x1, y1, x2, y2, fill=color, width=2, dash=dash, tags=("edge",))

        if label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 8
            self.create_text(mx, my, text=label, fill=color, font=("Menlo", 7), tags=("edge",))

    def _on_click(self, event):
        if not self.on_node_click:
            return
        # check node hit
        for tn, (x1, y1, x2, y2, _) in self.node_items.items():
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.on_node_click(tn)
                return

    def clear(self):
        self.thoughts = []
        self.delete("all")
        self.node_items.clear()
        self.edge_items.clear()


# ──────────────────────────────────────────────────────────────────────────────
# Analytics Panel
# ──────────────────────────────────────────────────────────────────────────────

class AnalyticsPanel(ttk.Frame):
    """Confidence calibration + learning patterns view."""

    def __init__(self, parent, db: Optional[MapThinkDoDB] = None):
        super().__init__(parent)
        self.db = db
        self._build()

    def _build(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=BOTH, expand=True)

        # Calibration
        cal_frame = ttk.Frame(self.notebook)
        self.notebook.add(cal_frame, text="Calibration")
        self.cal_tree = ttk.Treeview(
            cal_frame,
            columns=("actual", "samples", "error", "updated"),
            show="tree headings",
        )
        self.cal_tree.heading("#0", text="Domain / Bucket")
        self.cal_tree.heading("actual", text="Actual Rate")
        self.cal_tree.heading("samples", text="N")
        self.cal_tree.heading("error", text="Cal Error")
        self.cal_tree.heading("updated", text="Last Updated")
        self.cal_tree.column("#0", width=240)
        self.cal_tree.column("actual", width=100, anchor="center")
        self.cal_tree.column("samples", width=60, anchor="center")
        self.cal_tree.column("error", width=100, anchor="center")
        self.cal_tree.column("updated", width=140)
        self.cal_tree.pack(fill=BOTH, expand=True)

        # Patterns
        pat_frame = ttk.Frame(self.notebook)
        self.notebook.add(pat_frame, text="Patterns")
        self.pat_tree = ttk.Treeview(
            pat_frame,
            columns=("success", "fail", "rate", "avg_conf", "last_seen"),
            show="tree headings",
        )
        self.pat_tree.heading("#0", text="Pattern Type / Signature")
        self.pat_tree.heading("success", text="")
        self.pat_tree.heading("fail", text="")
        self.pat_tree.heading("rate", text="Rate")
        self.pat_tree.heading("avg_conf", text="Avg Conf")
        self.pat_tree.heading("last_seen", text="Last Seen")
        self.pat_tree.column("#0", width=300)
        self.pat_tree.column("success", width=50, anchor="center")
        self.pat_tree.column("fail", width=50, anchor="center")
        self.pat_tree.column("rate", width=70, anchor="center")
        self.pat_tree.column("avg_conf", width=80, anchor="center")
        self.pat_tree.column("last_seen", width=140)
        self.pat_tree.pack(fill=BOTH, expand=True)

        # Stats
        stat_frame = ttk.Frame(self.notebook)
        self.notebook.add(stat_frame, text="Stats")
        self.stat_text = tk.Text(
            stat_frame, font=("Menlo", 11), wrap="none", padx=10, pady=10, height=8
        )
        self.stat_text.pack(fill=BOTH, expand=True)

    def refresh(self):
        if not self.db:
            return

        # Calibration
        self.cal_tree.delete(*self.cal_tree.get_children())
        for row in self.db.get_calibration():
            domain = row.get("domain", "")
            bucket = row.get("predicted_bucket", "")
            self.cal_tree.insert(
                "",
                END,
                text=f"{domain}  [{bucket}]",
                values=(
                    f"{row.get('actual_success_rate', 0):.3f}",
                    row.get("sample_size", 0),
                    f"{row.get('calibration_error', 0):.4f}",
                    format_timestamp(row.get("last_updated")),
                ),
            )

        # Patterns
        self.pat_tree.delete(*self.pat_tree.get_children())
        for row in self.db.get_learning_patterns():
            ptype = row.get("pattern_type", "")
            sig = row.get("pattern_signature", "")[:80]
            self.pat_tree.insert(
                "",
                END,
                text=f"{ptype}: {sig}",
                values=(
                    row.get("success_count", 0),
                    row.get("failure_count", 0),
                    f"{row.get('success_rate', 0):.3f}",
                    f"{row.get('avg_confidence', 0):.2f}",
                    format_timestamp(row.get("last_seen")),
                ),
            )

        # Stats
        self.stat_text.delete("1.0", END)
        stats = self.db.get_stats()
        tables = self.db.table_names()
        self.stat_text.insert(
            "1.0",
            json.dumps(
                {
                    "database_path": str(self.db.path),
                    "statistics": stats,
                    "tables_found": tables,
                },
                indent=2,
            ),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Search Dialog
# ──────────────────────────────────────────────────────────────────────────────

class SearchDialog(tk.Toplevel):
    """Search across all thought text with results table."""

    def __init__(self, parent, db: MapThinkDoDB):
        super().__init__(parent)
        self.db = db
        self.title("Search Thoughts")
        self.geometry("900x600")
        self._build()

    def _build(self):
        # search bar
        top = ttk.Frame(self)
        top.pack(fill=X, padx=8, pady=8)
        self.query_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.query_var, font=("", 12)).pack(
            side=LEFT, fill=X, expand=True
        )
        ttk.Button(top, text="Search", command=self._search).pack(side=RIGHT, padx=4)
        self.bind("<Return>", lambda e: self._search())

        # results
        cols = ("session", "num", "domain", "obj", "snippet", "rank")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("session", text="Session")
        self.tree.heading("num", text="#")
        self.tree.heading("domain", text="Domain")
        self.tree.heading("obj", text="Objective")
        self.tree.heading("snippet", text="Snippet")
        self.tree.heading("rank", text="Rank")
        self.tree.column("session", width=180)
        self.tree.column("num", width=40, anchor="center")
        self.tree.column("domain", width=100)
        self.tree.column("obj", width=120)
        self.tree.column("snippet", width=350)
        self.tree.column("rank", width=60, anchor="center")
        self.tree.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))

        self.tree.bind("<Double-1>", self._on_double)

        # status
        self.status = ttk.Label(self, text="", foreground="gray")
        self.status.pack(anchor="w", padx=8, pady=(0, 4))

        self.results: List[Dict[str, Any]] = []

    def _search(self):
        q = self.query_var.get().strip()
        if not q:
            return
        self.results = self.db.search_fts(q, limit=200)
        self.tree.delete(*self.tree.get_children())
        for r in self.results:
            sid = (r.get("session_id") or "")[:24]
            self.tree.insert(
                "",
                END,
                values=(
                    sid,
                    r.get("thought_number", ""),
                    r.get("domain", ""),
                    (r.get("objective") or "")[:30],
                    (r.get("snippet") or "")[:200],
                    f"{r.get('rank', 0):.2f}" if r.get("rank") is not None else "—",
                ),
            )
        self.status.config(text=f"{len(self.results)} results for: {q[:80]}")

    def _on_double(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if idx < len(self.results):
            result = self.results[idx]
            # notify parent to jump to this thought
            if hasattr(self.master, "navigate_to_thought"):
                self.master.navigate_to_thought(
                    result["session_id"], result["id"]
                )


# ──────────────────────────────────────────────────────────────────────────────
# Bookmarks Dialog
# ──────────────────────────────────────────────────────────────────────────────

class BookmarksDialog(tk.Toplevel):
    """Manage viewer bookmarks."""

    def __init__(self, parent, db: MapThinkDoDB, on_navigate=None):
        super().__init__(parent)
        self.db = db
        self.on_navigate = on_navigate
        self.title("Bookmarks")
        self.geometry("800x500")
        self._build()
        self._load()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill=X, padx=8, pady=8)
        ttk.Label(top, text="Bookmarks", font=("", 12, "bold")).pack(side=LEFT)
        ttk.Button(top, text="Delete Selected", command=self._delete).pack(side=RIGHT)

        cols = ("session", "thought", "label", "note", "created")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("session", text="Session")
        self.tree.heading("thought", text="Thought #")
        self.tree.heading("label", text="Label")
        self.tree.heading("note", text="Note")
        self.tree.heading("created", text="Created")
        self.tree.column("session", width=200)
        self.tree.column("thought", width=70, anchor="center")
        self.tree.column("label", width=200)
        self.tree.column("note", width=200)
        self.tree.column("created", width=140)
        self.tree.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))

        self.tree.bind("<Double-1>", self._on_double)

    def _load(self):
        self.tree.delete(*self.tree.get_children())
        for bm in self.db.get_bookmarks():
            # find thought number
            tn = "—"
            if bm.get("thought_id"):
                thought = self.db.get_thought(bm["thought_id"])
                if thought:
                    tn = f"#{thought.get('thought_number', '?')}"
            self.tree.insert(
                "",
                END,
                iid=str(bm["id"]),
                values=(
                    (bm.get("session_id") or "")[:30],
                    tn,
                    bm.get("label", ""),
                    bm.get("note", ""),
                    format_timestamp(bm.get("created_at")),
                ),
            )

    def _delete(self):
        sel = self.tree.selection()
        for iid in sel:
            try:
                self.db.delete_bookmark(int(iid))
            except (ValueError, sqlite3.Error):
                pass
        self._load()

    def _on_double(self, _event=None):
        if not self.on_navigate:
            return
        sel = self.tree.selection()
        if not sel:
            return
        bookmarks = self.db.get_bookmarks()
        for bm in bookmarks:
            if str(bm["id"]) == sel[0]:
                self.on_navigate(bm["session_id"], bm.get("thought_id"))
                return


# ──────────────────────────────────────────────────────────────────────────────
# Export Dialog
# ──────────────────────────────────────────────────────────────────────────────

class ExportDialog(tk.Toplevel):
    """Export a session to Markdown or JSON."""

    def __init__(self, parent, db: MapThinkDoDB, session_id: str):
        super().__init__(parent)
        self.db = db
        self.session_id = session_id
        self.title(f"Export {session_id[:30]}...")
        self.geometry("500x300")
        self._build()

    def _build(self):
        ttk.Label(self, text="Export Session", font=("", 14, "bold")).pack(pady=12)

        ttk.Label(self, text=f"Session: {self.session_id}").pack()

        frame = ttk.Frame(self)
        frame.pack(pady=16)

        self.fmt_var = tk.StringVar(value="markdown")
        ttk.Radiobutton(frame, text="Markdown (.md)", variable=self.fmt_var,
                        value="markdown").pack(anchor="w", pady=2)
        ttk.Radiobutton(frame, text="JSON (.json)", variable=self.fmt_var,
                        value="json").pack(anchor="w", pady=2)
        ttk.Radiobutton(frame, text="JSON with raw events (.json)", variable=self.fmt_var,
                        value="json_full").pack(anchor="w", pady=2)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=16)
        ttk.Button(btn_frame, text="Export to File...", command=self._export).pack(
            side=LEFT, padx=4
        )
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=LEFT, padx=4)

    def _export(self):
        fmt = self.fmt_var.get()

        if fmt == "markdown":
            exts = [("Markdown", "*.md"), ("All files", "*.*")]
        else:
            exts = [("JSON", "*.json"), ("All files", "*.*")]

        filename = filedialog.asksaveasfilename(
            defaultextension=".md" if fmt == "markdown" else ".json",
            filetypes=exts,
            initialfile=f"session_{self.session_id[:12]}_{fmt}",
        )
        if not filename:
            return

        try:
            content = self._generate(fmt)
            Path(filename).write_text(content, encoding="utf-8")
            messagebox.showinfo("Export Complete", f"Saved to:\n{filename}")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    def _generate(self, fmt: str) -> str:
        session = self.db.get_session(self.session_id)
        if not session:
            session = self.db.get_synthetic_session(self.session_id)
        thoughts = self.db.get_thoughts(self.session_id)
        outcomes = self.db.get_outcomes_for_session(self.session_id)

        if fmt == "markdown":
            return self._generate_markdown(session, thoughts, outcomes)
        elif fmt == "json":
            return json.dumps(
                {"session": session, "thoughts": thoughts, "outcomes": outcomes},
                indent=2,
                default=str,
            )
        else:
            raw_events = self.db.get_raw_events_for_session(self.session_id)
            return json.dumps(
                {
                    "session": session,
                    "thoughts": thoughts,
                    "outcomes": outcomes,
                    "raw_mcp_events": raw_events,
                },
                indent=2,
                default=str,
            )

    def _generate_markdown(
        self,
        session: Dict[str, Any],
        thoughts: List[Dict[str, Any]],
        outcomes: List[Dict[str, Any]],
    ) -> str:
        lines = []
        lines.append(f"# MapThinkDo Session: {session.get('id', '?')}")
        lines.append("")
        lines.append(f"- **Started**: {format_timestamp(session.get('start_time'))}")
        lines.append(f"- **Ended**: {format_timestamp(session.get('end_time'))}")
        lines.append(f"- **Objective**: {session.get('objective', '—')}")
        lines.append(f"- **Domain**: {session.get('domain', '—')}")
        lines.append(f"- **Confidence**: {session.get('confidence_level', '—')}")
        lines.append(f"- **Goal Achieved**: {bool_display(session.get('goal_achieved'))}")
        lines.append(f"- **Total Thoughts**: {session.get('total_thoughts', 0)}")
        lines.append(f"- **Revisions**: {session.get('revision_count', 0)}")
        lines.append(f"- **Branches**: {session.get('branch_count', 0)}")
        lines.append(f"- **Effectiveness**: {session.get('effectiveness_score', '—')}")
        lines.append("")

        lines.append("## Timeline")
        lines.append("")
        for t in thoughts:
            badge = ThoughtTimeline.badge_for(t)
            lines.append(
                f"### Thought {t.get('thought_number')} / {t.get('total_thoughts')} — {badge}"
            )
            lines.append("")
            lines.append(f"- **Timestamp**: {t.get('timestamp', '—')}")
            lines.append(f"- **Confidence**: {t.get('confidence', '—')}")
            lines.append(f"- **Domain**: {t.get('domain', '—')}")
            lines.append(f"- **Complexity**: {t.get('complexity', '—')}")
            lines.append("")
            lines.append("```")
            lines.append(t.get("thought", "(empty)"))
            lines.append("```")
            lines.append("")

        if outcomes:
            lines.append("## Outcomes")
            lines.append("")
            for o in outcomes:
                lines.append(f"- Thought #{o.get('thought_number', '?')}: "
                             f"**{o.get('actual_outcome', '?')}** "
                             f"(score: {o.get('outcome_score', '?')})")
                if o.get("feedback"):
                    lines.append(f"  > {o['feedback']}")
            lines.append("")

        lines.append("## Raw Session Data")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(session, indent=2, default=str))
        lines.append("```")

        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Main Application
# ──────────────────────────────────────────────────────────────────────────────

class MapThinkDoViewer(tk.Tk):
    """Main application window."""

    def __init__(self, db_path: Optional[Path] = None):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(DEFAULT_WIN_SIZE)
        self.minsize(900, 500)

        self.db: Optional[MapThinkDoDB] = None
        self._current_session_id: Optional[str] = None
        self._sessions: List[Dict[str, Any]] = []
        self._thoughts: List[Dict[str, Any]] = []

        self._build_ui()
        self._apply_theme()

        # open DB
        if db_path:
            self._open_db(db_path)
        else:
            self._auto_open()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        self._create_menu()

        # main container
        self.main_paned = ttk.PanedWindow(self, orient=HORIZONTAL)
        self.main_paned.pack(fill=BOTH, expand=True)

        # left: session browser
        self.session_browser = SessionBrowser(
            self.main_paned,
            on_select=self._on_session_select,
            on_double_click=self._on_session_double_click,
        )
        self.main_paned.add(self.session_browser, weight=1)

        # middle: timeline
        self.thought_timeline = ThoughtTimeline(
            self.main_paned,
            on_select=self._on_thought_select,
        )
        self.main_paned.add(self.thought_timeline, weight=1)

        # right: detail + graph tabs
        right_paned = ttk.PanedWindow(self.main_paned, orient=VERTICAL)
        self.main_paned.add(right_paned, weight=3)

        # detail notebook
        self.detail_notebook = DetailNotebook(right_paned)
        right_paned.add(self.detail_notebook, weight=2)

        # bottom tabs in right pane
        bottom_notebook = ttk.Notebook(right_paned)
        right_paned.add(bottom_notebook, weight=1)

        # graph tab
        graph_frame = ttk.Frame(bottom_notebook)
        bottom_notebook.add(graph_frame, text="Branch/Revision Graph")
        self.graph_canvas = GraphCanvas(graph_frame, on_node_click=self._on_graph_node_click)
        self.graph_canvas.pack(fill=BOTH, expand=True)

        # analytics tab
        self.analytics = AnalyticsPanel(bottom_notebook)
        bottom_notebook.add(self.analytics, text="Analytics")

        # raw events tab — a readable request/response conversation transcript
        raw_frame = ttk.Frame(bottom_notebook)
        bottom_notebook.add(raw_frame, text="Raw Events")
        self.raw_events_text = tk.Text(
            raw_frame, wrap="word", font=("Menlo", 10), padx=8, pady=8
        )
        raw_sb = ttk.Scrollbar(raw_frame, orient=VERTICAL, command=self.raw_events_text.yview)
        self.raw_events_text.configure(yscrollcommand=raw_sb.set)
        self.raw_events_text.pack(side=LEFT, fill=BOTH, expand=True)
        raw_sb.pack(side=RIGHT, fill=Y)
        for tag, color in (
            ("req", "#2563eb"), ("res", "#16a34a"), ("err", "#dc2626"),
            ("dim", "#6b7280"), ("hdr", "#111827"),
        ):
            self.raw_events_text.tag_configure(tag, foreground=color)

        # status bar
        self.status_bar = ttk.Frame(self)
        self.status_bar.pack(fill=X, side="bottom")
        self.status_label = ttk.Label(self.status_bar, text="Ready", foreground="gray")
        self.status_label.pack(side=LEFT, padx=6, pady=2)
        self.db_path_label = ttk.Label(self.status_bar, text="", foreground="gray")
        self.db_path_label.pack(side=RIGHT, padx=6, pady=2)

    def _create_menu(self):
        menubar = tk.Menu(self)

        # File
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Open memory.db...", command=self._open_db_dialog)
        file_menu.add_command(label="Refresh (F5)", command=self._refresh_all)
        file_menu.add_separator()
        file_menu.add_command(label="Export Session as Markdown...",
                              command=self._export_markdown)
        file_menu.add_command(label="Export Session as JSON...",
                              command=self._export_json)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        # Edit
        edit_menu = tk.Menu(menubar, tearoff=False)
        edit_menu.add_command(label="Add Bookmark...", command=self._add_bookmark)
        edit_menu.add_command(label="View Bookmarks...", command=self._view_bookmarks)
        menubar.add_cascade(label="Edit", menu=edit_menu)

        # Navigate
        nav_menu = tk.Menu(menubar, tearoff=False)
        nav_menu.add_command(label="Search Thoughts...", command=self._open_search)
        nav_menu.add_command(label="Next Thought", command=self._next_thought,
                             accelerator="Ctrl+Down")
        nav_menu.add_command(label="Previous Thought", command=self._prev_thought,
                             accelerator="Ctrl+Up")
        menubar.add_cascade(label="Navigate", menu=nav_menu)

        # View
        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="Zoom In Graph", command=lambda: self._zoom_graph(1.2))
        view_menu.add_command(label="Zoom Out Graph", command=lambda: self._zoom_graph(0.8))
        view_menu.add_command(label="Reset Graph Zoom", command=lambda: self._zoom_graph(0))
        menubar.add_cascade(label="View", menu=view_menu)

        # Help
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About", command=self._about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

        # keyboard shortcuts
        self.bind("<F5>", lambda e: self._refresh_all())
        self.bind("<Control-Down>", lambda e: self._next_thought())
        self.bind("<Control-Up>", lambda e: self._prev_thought())
        self.bind("<Control-f>", lambda e: self._open_search())

    def _apply_theme(self):
        style = ttk.Style()
        available = style.theme_names()
        # prefer modern dark-ish themes if available
        for t in ("clam", "alt", "default"):
            if t in available:
                try:
                    style.theme_use(t)
                except tk.TclError:
                    pass
                break

        # tweak fonts
        default_font = ("Segoe UI", 10) if sys.platform == "win32" else ("Helvetica", 11)
        self.option_add("*Font", default_font)

    # ── DB operations ─────────────────────────────────────────────────────

    def _auto_open(self):
        for p in default_db_candidates():
            if p.exists():
                self._open_db(p)
                return
        self._set_status("No default DB found. Use File → Open memory.db...")

    def _open_db_dialog(self):
        filename = filedialog.askopenfilename(
            title="Open MapThinkDo memory.db",
            filetypes=[("SQLite DB", "*.db *.sqlite *.sqlite3"), ("All files", "*.*")],
        )
        if filename:
            self._open_db(Path(filename))

    def _open_db(self, path: Path):
        try:
            if self.db:
                self.db.close()
            self.db = MapThinkDoDB(path)
            self.db.open()
            self.db_path_label.config(text=str(path))
            self._set_status(f"Opened: {path}")
            self.title(f"{APP_TITLE} — {path}")
            self._refresh_all()
        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Could not open database:\n{e}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _refresh_all(self):
        if not self.db or not self.db.is_open():
            return
        self._load_sessions()
        self.analytics.refresh()

    def _load_sessions(self):
        self._sessions = self.db.get_sessions()

        # add orphan sessions
        seen = {s["id"] for s in self._sessions}
        for sid in self.db.get_orphan_session_ids():
            if sid not in seen:
                self._sessions.append(self.db.get_synthetic_session(sid))

        self.session_browser.load(self._sessions)

    # ── Navigation ────────────────────────────────────────────────────────

    def _on_session_select(self, session_id: str):
        if not self.db:
            return
        self._current_session_id = session_id
        self._thoughts = self.db.get_thoughts(session_id)
        self.thought_timeline.load(self._thoughts)   # load() resets any filter
        self.graph_canvas.load(self._thoughts)
        self._load_raw_events(session_id)
        self.detail_notebook.clear()

    def _on_session_double_click(self, session_id: str):
        # open export dialog
        if self.db:
            ExportDialog(self, self.db, session_id)

    def _on_thought_select(self, thought: Dict[str, Any]):
        self.detail_notebook.db = self.db
        self.detail_notebook.show_thought(thought)

    def _on_graph_node_click(self, thought_number: int):
        # find thought by number and select it
        for i, t in enumerate(self._thoughts):
            if t.get("thought_number") == thought_number:
                self.thought_timeline.select_index(i)
                self._on_thought_select(t)
                break

    def navigate_to_thought(self, session_id: str, thought_id: str):
        """Jump to a specific thought (from search/bookmarks)."""
        # select session
        if self._current_session_id != session_id:
            self._current_session_id = session_id
            self._thoughts = self.db.get_thoughts(session_id)
            self.thought_timeline.load(self._thoughts)
            self.graph_canvas.load(self._thoughts)
            self._load_raw_events(session_id)
            # highlight in session tree
            for item in self.session_browser.tree.get_children():
                if item == session_id:
                    self.session_browser.tree.selection_set(item)
                    self.session_browser.tree.see(item)
                    break

        # find and select thought
        for i, t in enumerate(self._thoughts):
            if t.get("id") == thought_id:
                self.thought_timeline.select_index(i)
                self._on_thought_select(t)
                break

    def _next_thought(self):
        idx = self.thought_timeline.get_selected_index()
        if idx >= 0 and idx + 1 < len(self._thoughts):
            self.thought_timeline.select_index(idx + 1)
            self._on_thought_select(self._thoughts[idx + 1])

    def _prev_thought(self):
        idx = self.thought_timeline.get_selected_index()
        if idx > 0:
            self.thought_timeline.select_index(idx - 1)
            self._on_thought_select(self._thoughts[idx - 1])

    # ── Raw events ────────────────────────────────────────────────────────

    def _load_raw_events(self, session_id: str):
        self.raw_events_text.delete("1.0", END)
        if not self.db or not self.db.has_raw_events():
            self.raw_events_text.insert(
                "1.0",
                "(no raw_mcp_events table found)\n\n"
                "This table is created by planauditmap_launcher.py — the stdio "
                "wire-tap that sits between your MCP client and the "
                "plan-audit-map server.\nIf you connect through "
                "planauditmap_launcher.py, every request/response pair is "
                "recorded here and mirrored to "
                "~/.plan-audit-map/raw-mcp-events.jsonl.",
            )
            return

        events = self.db.get_raw_events_for_session(session_id)
        if not events:
            # Not every wire event carries a plan-audit-map session id (e.g.
            # initialize, prompts/list, or a client that never sent one).
            # Show the newest events across all sessions instead of an empty
            # tab, clearly labelled as such.
            recent = self.db.get_recent_raw_events(120)
            self._render_raw_events(
                recent,
                header=f"(no raw events linked to session {session_id[:24]}… — "
                       f"showing the {len(recent)} most recent wire events "
                       f"across all sessions)",
            )
            return

        self._render_raw_events(events, header=None)

    def _render_raw_events(self, events: List[Dict[str, Any]], header: Optional[str]):
        """Render wire events as a readable conversation transcript.

        Each stored row is one request/response pair: the request JSON lives
        in request_json (with the tool call arguments — including the user's
        `thought` text), the response in response_json.  The old renderer
        printed only a fixed list of response fields, which hid half of the
        conversation; this walks both sides.
        """
        w = self.raw_events_text
        w.delete("1.0", END)
        if header:
            w.insert(END, header + "\n\n", ("dim",))

        for ev in events:
            when = format_timestamp(ev.get("request_timestamp") or ev.get("created_at"))
            tool = ev.get("tool_name") or ev.get("method") or "?"
            dur = ev.get("duration_ms")
            ok = ev.get("ok")
            err = ev.get("error")
            w.insert(END, f"── #{ev.get('id')} {when} ", ("hdr",))
            w.insert(END, f"{tool}", ("hdr",))
            if dur is not None:
                w.insert(END, f"  ({dur:.0f} ms)" if isinstance(dur, (int, float)) else f"  ({dur} ms)", ("dim",))
            w.insert(END, "\n")
            w.insert(
                END,
                f"   client={ev.get('client') or '—'} provider={ev.get('provider') or '—'}"
                f" transport={ev.get('transport') or '—'}\n",
                ("dim",),
            )

            # request side: tool + arguments (thought text etc.)
            req = safe_json(ev.get("request_json"), {})
            if isinstance(req, dict) and req:
                args = (req.get("params") or {}).get("arguments") or {}
                if isinstance(args, dict) and args:
                    thought = args.get("thought")
                    if thought:
                        w.insert(END, "  → ", ("req",))
                        w.insert(END, str(thought).replace("\n", " ")[:400] + "\n")
                    rest = {k: v for k, v in args.items() if k != "thought"}
                    if rest:
                        w.insert(END, "  → args ", ("req",))
                        w.insert(END, json.dumps(rest, default=str)[:300] + "\n")

            # response side: unwrap MCP content[0].text, then interesting fields
            resp = safe_json(ev.get("response_json"), {})
            if isinstance(resp, dict) and resp:
                if resp.get("error"):
                    w.insert(END, "  ← error ", ("err",))
                    w.insert(END, json.dumps(resp["error"], default=str)[:400] + "\n")
                    continue
                result = resp.get("result") or {}
                content = result.get("content") if isinstance(result, dict) else None
                payload = None
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            payload = safe_json(item.get("text"), None)
                            break
                if isinstance(payload, dict):
                    shown = 0
                    for k in (
                        "status", "session_id", "thought_number", "total_thoughts",
                        "next_thought_needed", "branches_detected",
                        "metacognitive_awareness", "breakthrough_likelihood",
                        "creative_pressure", "cognitive_flexibility",
                        "insight_potential", "reasoning_mode",
                        "detected_biases", "hypothesis_ledger",
                        "action_ranking", "ai_recommendations",
                        "cognitive_interventions", "memory_insights",
                    ):
                        if k in payload and payload[k] is not None:
                            v = payload[k]
                            if isinstance(v, (list, dict)):
                                v = json.dumps(v, ensure_ascii=False, default=str)
                                if len(v) > 200:
                                    v = v[:200] + "…"
                            w.insert(END, "  ← ", ("res",))
                            w.insert(END, f"{k}: {v}\n")
                            shown += 1
                    if not shown:
                        w.insert(END, "  ← ", ("res",))
                        w.insert(END, json.dumps(payload, default=str)[:300] + "\n")
                else:
                    snippet = json.dumps(resp, default=str)[:300]
                    w.insert(END, "  ← ", ("res",))
                    w.insert(END, snippet + "\n")
            elif err:
                w.insert(END, "  ← error ", ("err",))
                w.insert(END, str(err)[:400] + "\n")
            elif ok == 0:
                w.insert(END, "  ← failed\n", ("err",))
            w.insert(END, "\n")

        w.configure(state="normal")
        w.yview_moveto(0.0)

    # ── Search ────────────────────────────────────────────────────────────

    def _open_search(self):
        if not self.db:
            messagebox.showwarning("No Database", "Open a database first.")
            return
        SearchDialog(self, self.db)

    # ── Bookmarks ─────────────────────────────────────────────────────────

    def _add_bookmark(self):
        if not self.db or not self._current_session_id:
            messagebox.showwarning("No Session", "Select a session first.")
            return

        label = simpledialog.askstring("Bookmark Label", "Label for this bookmark:")
        if label is None:
            return
        note = simpledialog.askstring("Bookmark Note", "Optional note:")
        if note is None:
            note = ""

        thought_id = None
        idx = self.thought_timeline.get_selected_index()
        if idx >= 0 and idx < len(self._thoughts):
            thought_id = self._thoughts[idx].get("id")

        try:
            self.db.add_bookmark(self._current_session_id, thought_id, label, note)
            self._set_status(f"Bookmark added: {label}")
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Could not save bookmark:\n{e}")

    def _view_bookmarks(self):
        if not self.db:
            messagebox.showwarning("No Database", "Open a database first.")
            return
        BookmarksDialog(self, self.db, on_navigate=self.navigate_to_thought)

    # ── Export ────────────────────────────────────────────────────────────

    def _export_markdown(self):
        if not self.db or not self._current_session_id:
            messagebox.showwarning("No Session", "Select a session first.")
            return
        dlg = ExportDialog(self, self.db, self._current_session_id)
        dlg.fmt_var.set("markdown")

    def _export_json(self):
        if not self.db or not self._current_session_id:
            messagebox.showwarning("No Session", "Select a session first.")
            return
        dlg = ExportDialog(self, self.db, self._current_session_id)
        dlg.fmt_var.set("json")

    # ── Graph zoom ────────────────────────────────────────────────────────

    def _zoom_graph(self, factor: float):
        if factor == 0:
            self.graph_canvas.X_SPACING = 110
            self.graph_canvas.NODE_W = 48
            self.graph_canvas.NODE_H = 28
            self.graph_canvas.LANE_H = 72
            self.graph_canvas.MARGIN = 50
        else:
            self.graph_canvas.X_SPACING = int(self.graph_canvas.X_SPACING * factor)
            self.graph_canvas.NODE_W = max(20, int(self.graph_canvas.NODE_W * factor))
            self.graph_canvas.NODE_H = max(14, int(self.graph_canvas.NODE_H * factor))
            self.graph_canvas.LANE_H = max(30, int(self.graph_canvas.LANE_H * factor))
            self.graph_canvas.MARGIN = max(20, int(self.graph_canvas.MARGIN * factor))
        self.graph_canvas._redraw()

    # ── About ─────────────────────────────────────────────────────────────

    def _about(self):
        messagebox.showinfo(
            "About MapThinkDo Viewer",
            textwrap.dedent("""\
            MapThinkDo Viewer v1.0

            A Tkinter desktop app for inspecting MapThinkDo reasoning sessions.

            Reads the SQLite memory database created by the MapThinkDo MCP server
            (geeknik/plan-audit-map) and provides session browsing, thought timeline,
            detail inspection, FTS search, branch/revision graph visualization,
            analytics, bookmarks, and Markdown/JSON export.

            Built for the Grok + Maestra + BatonPass ecosystem.
            """),
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self.status_label.config(text=msg[:200])


# ──────────────────────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    db_path = None
    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1])
        if candidate.exists():
            db_path = candidate
        else:
            print(f"Warning: '{sys.argv[1]}' not found, trying defaults.", file=sys.stderr)

    app = MapThinkDoViewer(db_path)
    app.mainloop()


if __name__ == "__main__":
    main()
