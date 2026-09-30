# Skill: Troubleshooting the wire tap, memory.db and the SQL viewer

## Ground rules
- The desk stack (bar, launcher, viewer) is stdlib-only Python. If pip is
  involved, something is wrong.
- One database: `~/.plan-audit-map/memory.db` (override with
  `PLAN_AUDIT_MAP_HOME` or `PLAN_AUDIT_MAP_DB` — the server overlay honours the
  same vars; the Python side always has). Split-brain symptoms (sessions in
  the viewer but no conversations) almost always mean two different DB
  files are in play. Check with: `SELECT COUNT(*) FROM raw_mcp_events;`
  against the exact path shown in the viewer status bar.
- The server only ever writes: thoughts, sessions, outcomes,
  confidence_calibration, learning_patterns (+ thoughts_fts). The
  `raw_mcp_events` table — the entire conversation view — exists ONLY
  because the launcher tap creates it. No launcher in the chain = no
  conversations, by design.

## Symptom → cause → fix
| Symptom | Cause | Fix |
|---|---|---|
| Viewer: "(no raw_mcp_events table found)" | client connects to the server directly, not through the launcher | re-point the client at `planauditmap_launcher.py -- node .../dist/index.js` |
| Tap rows exist but `planauditmap_session_id` is NULL | older mtd_shared (looked for `content` at message top level) | upgrade desk/; verify with `SELECT COUNT(*) FROM raw_mcp_events WHERE planauditmap_session_id IS NOT NULL` |
| "SQLite objects created in a thread…" in launcher stderr | ancient mtd_shared (check_same_thread) | upgrade desk/ |
| Client hangs at startup through the launcher | ancient launcher blocked on buffered read | upgrade desk/ (proxy now uses raw os.read) |
| Server never exits after client closes | ancient server ignored stdin EOF | rebuild dist (overlay ships the EOF fix) |
| Server exits -11/139 instantly | better-sqlite3@13 on Node 20 (needs 22+) | keep `^12.11.1` in the overlay package.json |
| npm EBADENGINE + `info.This()` compile error | better-sqlite3@12.5.x on Node >= 26 | bump overlay pin to `^12.11.1` |
| tsc compiles the desk folder and fails | repo tsconfig `**/*.ts` include | installer excludes the desk dir; keep that exclude line |
| Viewer order looks scrambled | mixed UTC 'Z' and naive local timestamps sorted as strings | current viewer sorts via a tz-aware parser + rowid; rebuild desk/ |
| Bar exists but no ticker updates | bar watching a different DB than the server writes | set `PLAN_AUDIT_MAP_HOME` for both, or check desk-bar.json |

## Quick health check (one paste)
```
python3 - <<'EOF'
import sqlite3, os
p = os.path.expanduser("~/.plan-audit-map/memory.db")
c = sqlite3.connect(p)
for t in ("sessions","thoughts","outcomes","raw_mcp_events"):
    try: print(t, c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    except sqlite3.Error: print(t, "MISSING")
EOF
```
All four > 0 after one launcher-mediated session = pipeline healthy.

## Viewer cheatsheet
`python3 desk/planauditmap_viewer.py [db]` — F5 refresh, Ctrl+F search
(FTS with LIKE fallback), double-click a session = export dialog, Raw
Events tab = conversation transcript (falls back to the newest events
across all sessions when the selected session has none), Analytics tab =
calibration + learning patterns. The desk bar's overview popup has exactly
one button — SQL Viewer — by design.
