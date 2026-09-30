# Skill: the enhanced server overlay — flags, endpoints, EOF, build

## What the overlay is

Four files in `plan-audit-map-desk/server/` copied over a stock
geeknik/plan-audit-map checkout at install: `index.ts` (CLI), `server.ts`
(→ `src/server.ts`), `config.ts` (→ `src/utils/config.ts`), and
`package.json` (pinned deps). Beyond upstream it adds: HTTP/SSE mode,
public tunnels, token auth, TLS, a web dashboard, the stdin-EOF fix, the
env-aware DB path, and the Node 20-26+ sqlite pin. The repo's tsconfig
`include ./**/*.ts` must EXCLUDE the dropped-in desk folder or tsc tries
to compile the overlay copies in place and dies on broken relative
imports (`Cannot find module './src/server.js'`) — the installers add
that exclude automatically.

## CLI flags (node dist/index.js …)

`--sse` (HTTP/SSE instead of stdio), `--host` (default 127.0.0.1),
`--port` (8002), `--token <secret>` / `--token-file <path>`,
`--local` (bind the LAN IP), `--remote` (public tunnel via `--tunnel
ngrok|pinggy|localtunnel|localhostrun|serveo`), `--cors-origin`,
`--no-dashboard`, `--max-connections` (50), `--quiet`, `--tls-cert` /
`--tls-key` (HTTPS), `--debug`, `--help`. Token is accepted as
`?token=` on GET /sse or `Authorization: Bearer` — constant-time
compared. Rate limits: 30 requests/min per IP, 10 new SSE
connections/min; security headers set on every response (nosniff, DENY
framing, HSTS when TLS). Endpoints: `GET /sse` (MCP over SSE, prints an
`endpoint` event with the session id), `POST /messages?sessionId=…`,
`GET /` dashboard, `GET /health` (200).

## The stdin-EOF fix (FilteredStdioServerTransport)

The overlay's transport wraps `StdioServerTransport` with a 1 MB input
buffer cap, stdout error filtering (EPIPE marks the transport closed
instead of crashing), and — the fix — stdin `end`/`close` handlers.
The original overrode `start()` without registering them, so when the
client closed stdin the server never noticed and idled forever: one
zombie `node.exe` per client disconnect. Now EOF sets closed, fires
`onclose`, and a 1.5 s watchdog forces `process.exit(0)` even if another
handle keeps the event loop alive. Symptom of the old bug: orphaned
node processes accumulating in Task Manager, all running
`dist/index.js`. Related proxy-side rule: a launcher must forward EOF by
half-closing the child's stdin, or the fix never triggers.

## Env-aware database path

DB resolution order: `PLAN_AUDIT_MAP_DB`/`PLAN_AUDIT_MAP_MEMORY_DB` (exact
file) → `PLAN_AUDIT_MAP_HOME`/`PLAN_AUDIT_MAP_CONFIG_DIR` +
`/memory.db` → default `~/.plan-audit-map/memory.db`. The Python desk
stack resolves the same way. If the two sides ever disagree you get a
SPLIT-BRAIN DB (sessions in one file, conversations in another —
"viewer shows nothing but the client works"). Check the exact path in
the viewer status bar against the env of the process launching the
server. `config.ts` applies the same env precedence to
`prompt_values.json` and the `prompts/` directory.

## Build behaviour and failure table

`build` is plain `tsc` (upstream's `tsc && chmod +x …` cannot run under
cmd.exe and fails the Windows install at the `prepare` hook). Typical
build failures:

| Symptom | Cause | Fix |
|---|---|---|
| instant exit, code -11/139, no output | better-sqlite3 ABI vs Node (13.x on Node 20) | pin per the ABI skill |
| node-gyp compile error `info.This()` / `PropertyCallbackInfo::This()` | better-sqlite3 12.5.x on Node ≥ 26 | bump pin to `^12.11.1` in the OVERLAY package.json |
| tsc errors `Cannot find module './src/server.js'` from the desk folder | repo tsconfig compiling the dropped-in overlay | installer's tsconfig exclude; keep it |
| npm install fails at prepare: `'chmod' is not recognized` | Unix-only command in build script under cmd.exe | overlay package.json uses `build: tsc`; or `--ignore-scripts` + manual tsc |
| server never exits after client closes | pre-fix dist without the EOF handlers | rebuild from the current overlay |
| `EBADENGINE` warning then segfault | engines advisory ignored | see ABI skill — verify with `node dist/index.js --help` |

## Smoke tests that mean something

1. `node dist/index.js --help` prints usage (catches the silent segfault
   class instantly).
2. SSE: `node dist/index.js --sse --port 8002` then
   `curl -N http://127.0.0.1:8002/sse` must emit an
   `event: endpoint` line; `/` returns 200; `/health` returns 200.
3. Full pipeline: pipe `initialize` → `notifications/initialized` →
   `tools/call` through `planauditmap_launcher.py` and assert row counts
   in `memory.db` grew. Exit code 0 within a few seconds of closing
   stdin proves the EOF chain end-to-end.

## Tunnel provider matrix (--remote --tunnel …)

| Provider | Mechanism | Notes |
|---|---|---|
| ngrok | ngrok agent API (`--ngrok-authtoken`, `--ngrok-api` default http://127.0.0.1:4040, `--ngrok-domain`) | needs an account/token; stable domains on paid plans |
| localhostrun | ssh to localhost.run with the bundled key | default for the Grok launcher .bat; no account |
| pinggy | ssh tunnel | temporary URLs |
| localtunnel | npx localtunnel client | node-based |
| serveo | ssh serveo.net | availability varies |

All follow the same startup: bind local SSE (port 8002), open the
tunnel, print the PUBLIC URL to paste into the remote client. The
Windows `planauditmap_remote.bat` first clears port 8002 (netstat/PID
kill loop) because a stale listener is the usual "tunnel starts but
the URL 502s" cause.

## Dashboard and limits

`GET /` serves an inline dashboard (status, recent activity, connection
info); `--no-dashboard` disables it. Rate limiting is per-IP token
bucket: 30 req/min general, 10 new SSE connections/min,
`--max-connections` 50 concurrent sessions; excess gets 429/503. CORS
defaults open (`*`); restrict with `--cors-origin` when the dashboard
is exposed beyond localhost.
