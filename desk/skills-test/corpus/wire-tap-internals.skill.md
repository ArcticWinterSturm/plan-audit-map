# Skill: wire-tap internals — the stdio proxy that records conversations

## What it is and the one rule it never breaks

`planauditmap_launcher.py` sits between an MCP client and
`node dist/index.js`. It is a byte-transparent stdio proxy: every byte the
client writes goes to the server verbatim, every byte the server writes
goes back verbatim. Nothing is ever written to stdout that did not come
from the server — stdout belongs to the JSON-RPC stream, all launcher
diagnostics go to stderr. Break that rule and the client's parser dies.

Side effects: it taps the stream into the `raw_mcp_events` table, mirrors
each event to `~/.plan-audit-map/raw-mcp-events.jsonl`, starts the desk bar
(Windows, unless `--no-bar`), and streams live tool calls to the bar on
port 38457. Run it with `python.exe`, never `pythonw.exe` — it needs real
stdio.

## Why the proxy uses os.read, not read(8192) — the classic deadlock

The naive proxy does `sys.stdin.buffer.read(8192)`. That is a
`BufferedReader`: `read(n)` blocks until ALL n bytes arrive or EOF. MCP
stdio frames are ~100-200 bytes. Result: the client sends `initialize`,
the proxy waits for 8192 bytes, the server waits for the proxy, the client
waits for the server — total deadlock until 8 KiB of messages accumulate.
Symptom: client hangs at startup through the launcher but connects fine
directly to the server. Fix: `os.read(fd, 8192)` returns whatever is
available the moment it is available. Any stdio proxy must do this.

## EOF must be forwarded (half-close), or nothing ever exits

When the client closes stdin, the proxy's read loop gets `b""`. If the
proxy just exits its loop, the child server's stdin pipe stays open (the
OS keeps the write end alive because the proxy holds it) and the server
never sees EOF — both processes idle forever. Correct behavior: when the
client→server pump ends, explicitly `close()` the child's stdin so EOF
propagates, then wait for the child. Lifecycle for a full session
(init → tools/list → 2 tool calls → close) is ~3 s ending in exit 0.

## Message classification: request / response / notification / server-request

Line-delimited JSON, one object per line. Direction rules, where stream is
`in` (client→server) or `out` (server→client):
- `in` + has `id` → `request`; method without id → `notification`
- `out` + `id` without `method` → `response`
- `out` + `id` AND `method` → `server-request` (server-initiated:
  `sampling/createMessage`, `roots/list` pings) — these are NOT responses
  and must never be paired with client requests
Pairing happens on the JSON-RPC `id` string. A response updates the row
its request created (computing `duration_ms`); notifications are stored
standalone.

## The raw_mcp_events store — cross-thread SQLite that actually works

Two properties that break naive implementations:
1. **Threads.** The connection is created on the main thread; inserts come
   from the pipe threads. CPython raises `SQLite objects created in a
   thread can only be used in that same thread` and — worse — the original
   build swallowed the error, so the tap wrote NOTHING to the DB while
   appearing healthy (only the JSONL mirror survived). Fix:
   `sqlite3.connect(..., check_same_thread=False)` is safe because every
   access is serialised by one RLock.
2. **Two writers.** The Node server holds the same DB open in WAL mode.
   Coexistence recipe: WAL + `PRAGMA busy_timeout = 8000` + autocommit
   (`isolation_level=None`) + never hold a transaction open. Every write
   is one INSERT or UPDATE.

Storage details: payloads truncated at `max_payload_bytes` (262144) before
storing; the pending map of unanswered requests is trimmed oldest-first at
512 entries; a response that arrives before its own request row commits
(the pipe threads race) is remembered and folded into the late request
instead of duplicating.

## Session linking — where planauditmap_session_id comes from

The server generates `session_<uuid>` ids; the tool schema does NOT accept
a client-supplied `session_id` (sending one returns `Unrecognized key(s)
in object: 'session_id'`). The tap extracts the real id from response
payloads: `message.result.content[*]` where `type == "text"`, parse the
text as JSON, read `session_id`/`sessionId`. Looking for `content` at the
message top level is the classic bug — it matches sampling-style messages
but never real tool responses, leaving every row NULL and the viewer's
per-session conversation empty. Requests link via `params.arguments` when
an id is already known.

## Symptom → cause → fix

| Symptom | Cause | Fix |
|---|---|---|
| viewer: "(no raw_mcp_events table found)" | client connects directly to the server, bypassing the launcher | point the client at `planauditmap_launcher.py -- node …/dist/index.js` |
| tap rows exist but `planauditmap_session_id` all NULL | extraction looked at message top level instead of `result.content` | upgrade `desk/` |
| "SQLite objects created in a thread…" on stderr | `check_same_thread` default | upgrade `desk/` (store opens with it disabled) |
| client hangs through launcher, fine direct | buffered `read(8192)` blocking | upgrade `desk/` (raw `os.read`) |
| launcher+server never exit after client closes | EOF not forwarded / server EOF handler missing | upgrade both `desk/` and rebuild `dist/` |
| "database is locked" in tap stderr | long transactions or missing busy_timeout | keep autocommit + busy_timeout; see the WAL skill |
| AttributeError on `sys.stdin.buffer` under pythonw | stdin is None without a console | launcher guards with `getattr(sys.stdin, "buffer", None)`; run the launcher with python.exe |

## Quick health check (one paste)

```
python3 - <<'EOF'
import sqlite3, os
c = sqlite3.connect(os.path.expanduser("~/.plan-audit-map/memory.db"))
for t in ("sessions","thoughts","outcomes","raw_mcp_events"):
    try: print(t, c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    except sqlite3.Error: print(t, "MISSING")
EOF
```
All four counts > 0 after one launcher-mediated session means the whole
pipeline (client → tap → DB ← server) is healthy. Any zero means the
corresponding writer is bypassed or broken — investigate that writer, not
the reader.

## Launcher CLI reference

`planauditmap_launcher.py [--config PATH] [--no-bar] [--no-log]
[--client NAME] [--start-bar] [--stop-bar] [--open-intervention]
[--print-mcp-config] -- <server command>…`
- `--no-log`: skip the DB tap entirely (pure proxy)
- `--client`: tag wire rows with the client name (provider comes from
  `PLAN_AUDIT_MAP_PROVIDER` or auto-detection: TAURI_ENV_* → qwen-desktop,
  CLAUDE_* → claude, else unknown)
- `--print-mcp-config`: emits a paste-ready `mcpServers` entry using the
  current interpreter and `server_command` from desk-bar.json
- `--open-intervention`: opens the bar's Intervene tab (starting the bar
  if needed) and exits — binds nothing, safe from scripts

## Worked example: one tool call, both directions

Client writes:
`{"jsonrpc":"2.0","id":11,"method":"tools/call","params":{"name":
"plan-audit-map","arguments":{"thought":"check the ABI first","thought_number":1,
"total_thoughts":3,"next_thought_needed":true}}}`
Tap: direction=request (id 11, has method) → INSERT with request_json,
pending[11] = {row_id, timestamp, tool_name}.
Server writes back id 11 with `result.content[0].text` containing the
server payload JSON (`session_id`, metrics…). Tap: direction=response,
pairs with pending[11] → UPDATE that row: response_json, duration_ms =
response_ts − request_ts, ok=1, `planauditmap_session_id` extracted from
`result.content[0].text` (NOT message top level). Viewer later renders
this row as one conversation turn: request args (the thought text) +
unwrapped response fields.
