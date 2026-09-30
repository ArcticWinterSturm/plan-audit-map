# Skill: memory.db schema — tables, writers, and the timestamp trap

## Three writers, one file, know which is which

`~/.plan-audit-map/memory.db` (SQLite, WAL mode) is written by three
processes. Every "missing data" mystery resolves to "which writer":

| Table | Writer | When |
|---|---|---|
| `thoughts`, `sessions`, `outcomes`, `confidence_calibration`, `learning_patterns`, `thoughts_fts*` | Node server (`dist/index.js`) | on every tool call / feedback |
| `raw_mcp_events` | Python wire tap (`planauditmap_launcher.py`) | on every JSON-RPC pair through the launcher |
| `viewer_bookmarks` | SQL viewer (Tkinter) | user bookmarks only |

If `thoughts` is populated but `raw_mcp_events` is missing/empty, the
client is bypassing the launcher — the bare server NEVER creates that
table. If `raw_mcp_events` exists but `thoughts` is empty, the server is
failing (check its stderr / the ABI skill for silent segfaults).

## thoughts columns (id TEXT PRIMARY KEY)

`id`, `session_id` (NOT NULL), `thought`, `thought_number`,
`total_thoughts`, `timestamp`, `confidence` (REAL), `domain`,
`objective`, `is_revision` (INTEGER bool), `revises_thought`,
`branch_id` (TEXT), `branch_from_thought`, `next_thought_needed`,
`complexity`, `success`, `effectiveness_score`, `output`, `context`,
`tags`, `patterns_detected`, `similar_thoughts`, `context_trace` — the
JSON-ish columns (`context`, `tags`, `patterns_detected`,
`similar_thoughts`, `context_trace`) hold JSON strings; parse before use.

## sessions columns (id TEXT PRIMARY KEY)

`id`, `start_time`, `end_time`, `objective`, `domain`, `goal_achieved`
(INTEGER bool), `confidence_level` (REAL), `total_thoughts`,
`revision_count`, `branch_count`, `effectiveness_score`,
`lessons_learned`, `successful_strategies`, `failed_approaches`, `tags`,
`cognitive_roles_used`, `metacognitive_interventions`,
`initial_complexity`, `final_complexity`, `created_at`.

## raw_mcp_events columns (id INTEGER PRIMARY KEY AUTOINCREMENT)

`id`, `planauditmap_session_id`, `client`, `provider`, `transport`,
`direction` (request|response|notification|server-request), `method`,
`tool_name`, `jsonrpc_id`, `request_json`, `response_json`,
`request_timestamp`, `response_timestamp`, `duration_ms` (REAL), `ok`
(INTEGER), `error`, `process_id`, `created_at`. One row per
request/response pair once pairing completes; `request_json` holds the
tool arguments including the user's `thought` text, `response_json` holds
the MCP envelope whose `result.content[0].text` is the server's JSON
payload (status, session_id, cognitive metrics).

## The timestamp trap: order by rowid, never by timestamp

The Node server writes `new Date().toISOString()` — UTC with `Z`. SQLite
defaults and some paths write `YYYY-MM-DD HH:MM:SS` — naive LOCAL time.
Sorting the column as strings mixes zones: a 23:30Z row sorts BEFORE a
22:00 naive-local row even when it is later in real time. Symptom:
"recent activity" shows an hour-old item above a fresh one; sessions list
scrambled. Rule: `ORDER BY rowid DESC` for thoughts/sessions (insertion
order) and `ORDER BY id DESC` for `raw_mcp_events`. For Python-side
display sorting, parse to aware datetimes first (naive = assume local).

## Query recipes

Newest activity across everything:
`SELECT session_id, timestamp FROM thoughts ORDER BY rowid DESC LIMIT 20`
then take max by a timezone-aware parse of the 20.

A session's full conversation:
`SELECT * FROM raw_mcp_events WHERE planauditmap_session_id = ? ORDER BY id ASC`
— `id`, not `request_timestamp` (mixed zones again).

Orphan sessions (thoughts whose session row never landed, e.g. server
killed mid-call):
`SELECT DISTINCT session_id FROM thoughts WHERE session_id NOT IN
 (SELECT id FROM sessions)` — the viewer synthesises session entries for
these and tags them "orphan".

## Opening the DB safely from Python

Read-only readers (bar, viewer, intervention engine) should use the URI
mode: `sqlite3.connect("file:<path>?mode=ro", uri=True, timeout=5)` plus
`PRAGMA busy_timeout`. Row factory `sqlite3.Row`. Writers (tap) need WAL +
autocommit + busy_timeout 8000 — see the multi-process WAL skill. The
`-wal` and `-shm` files are part of the database; copying only `memory.db`
while a writer is live can lose recent commits — use `sqlite3` `.backup`
or copy all three files.

## Empty-database guard (the viewer crash)

A DB created by the tap alone contains ONLY `raw_mcp_events` (+
`sqlite_sequence`). Any tool that assumes `sessions`/`thoughts` exist —
`SELECT COUNT(*) FROM sessions` on open — dies with `sqlite3.OperationalError:
no such table: sessions`. Correct pattern: check
`SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name=?`
before every per-table query, and treat a missing table as "0 rows", not
an error. The viewer does this for sessions, thoughts, outcomes,
calibration, patterns and events.

## outcomes / confidence_calibration / learning_patterns columns

`outcomes`: `id` TEXT PK, `thought_id` (NOT NULL), `session_id`
(NOT NULL), `recorded_at`, `actual_outcome` (success|partial|failure),
`outcome_score`, `feedback` — written by the plan-audit-map-feedback tool.
`confidence_calibration`: `id` INTEGER PK, `domain`,
`predicted_bucket` REAL, `actual_success_rate` REAL, `sample_size`,
`calibration_error`, `last_updated` — the server's self-calibration of
confidence vs reality; the intervention estimate reads the
sample-weighted mean |bucket − actual| as its "calibration gap".
`learning_patterns`: `id` TEXT PK, `pattern_type`,
`pattern_signature`, `success_count`, `failure_count`, `success_rate`,
`avg_confidence`, `domains` (JSON), `insights` (JSON), `first_seen`,
`last_seen`.

## FTS notes

`thoughts_fts*` (config/data/docsize/idx tables) is the server's FTS5
index over thoughts. Viewer search tries `MATCH` with a sanitized
OR-joined term query and falls back to `LIKE '%q%'` when FTS is missing
or the query has no word characters. `snippet(thoughts_fts, 0, …)`
provides highlighted excerpts. Deleting rows directly from `thoughts`
without touching FTS leaves the index stale — prefer the server's own
deletion paths.

## Worked queries

Health: count all four tables (see the wire-tap skill).
Recent conversation across everything (oldest→newest):
`SELECT * FROM raw_mcp_events ORDER BY id DESC LIMIT 120` then reverse.
Thoughts of a session in order:
`SELECT * FROM thoughts WHERE session_id=? ORDER BY thought_number ASC,
timestamp ASC` — thought_number first: revisions can share timestamps.
Session effectiveness over time:
`SELECT start_time, effectiveness_score, goal_achieved FROM sessions
ORDER BY rowid DESC LIMIT 50`.
