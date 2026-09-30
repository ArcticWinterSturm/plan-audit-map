# Skill: Wiring plan-audit-map into MCP clients (Claude, Qwen, SSE)

## Which client, which file
| Client | Where config lives | Notes |
|---|---|---|
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json` (win), `~/Library/Application Support/Claude/...` (mac) | standard |
| Claude Code | project `.mcp.json` | standard |
| Qwen Code (CLI) | `~/.qwen/settings.json` (user) / `.qwen/settings.json` (project); or `qwen mcp add` | standard |
| Qwen Desktop (official app) | the app's own settings UI (stored under key `mcp_config` by the Electron shell) | NON-standard |
| qwen-studio (Linux port) | `~/.config/qwen-studio/settings.json` under `mcpServers` | non-standard bridge |
| Any SSE client | run the server first, point at the URL | see below |

## The launcher wrapper (recommended)
Point the client at `planauditmap_launcher.py` instead of the server directly.
It is a byte-transparent stdio proxy that also (a) starts the taskbar desk
bar on Windows, (b) records every request/response pair into the
`raw_mcp_events` table (the viewer's conversation view depends on it),
(c) mirrors events to `~/.plan-audit-map/raw-mcp-events.jsonl`.

```json
{"mcpServers": {"plan-audit-map": {
  "command": "/absolute/python",
  "args": ["/absolute/planauditmap_launcher.py", "--client", "claude-desktop",
           "--", "/absolute/node", "/absolute/plan-audit-map/dist/index.js"]
}}}
```

## Qwen-specific traps (verified against the official 1.0.3.44 app)
- chat.qwen.ai has **no API for custom MCP servers** — the web UI gets tools
  from the desktop shell via injected `window.electronAPI` IPC. Configure in
  the app UI only.
- The official app **rewrites runners**: `npx` → its bundled `bun x -y`,
  `uvx` → bundled uvx, and **replaces PATH** with its resources dir. So:
  always use ABSOLUTE paths for `command` (`C:/.../node.exe`), never `npx`,
  never bare `node`.
- qwen-studio spawns servers via `node mcp-bridge.mjs` (official SDK stdio
  transport) — the python launcher works fine there.
- Set `"env": {"PLAN_AUDIT_MAP_PROVIDER": "qwen-desktop"}` so wire events are
  tagged with the right provider.

## SSE / remote
1. `node dist/index.js --sse --host 127.0.0.1 --port 8002` → connect to
   `http://127.0.0.1:8002/sse`.
2. LAN: add `--local` (binds the LAN IP). Token: add `--token <secret>`
   (connect with `?token=` or `Authorization: Bearer`).
3. Public tunnel for browser clients (e.g. Grok): `--remote --tunnel
   localhostrun` (or ngrok/pinggy/serveo); the public URL prints at startup.
4. Windows one-click launchers ship in `windows/*.bat`.

## Verification is a DB query, not a log line
After connecting, the ground truth that the pipeline works is row counts in
`~/.plan-audit-map/memory.db` (`raw_mcp_events`, `thoughts`, `sessions` all
gain rows after one tool call). Silent tap failure with a "working" client
is the classic false positive.
