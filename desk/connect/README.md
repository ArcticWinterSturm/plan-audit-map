# Connecting MCP clients to plan-audit-map

After running `install.bat` (Windows) or `install.sh` (Linux/macOS), every
`*.json` template in this folder gets a resolved twin `*.local.json` with the
absolute `node` / `python` / `dist/index.js` paths of **this machine** filled
in. Paste or merge a `.local.json` into your client — nothing else to edit.

| File | Transport | Use when |
|---|---|---|
| `plan-audit-map.stdio+desk.local.json` | stdio via launcher | **Recommended (Windows)** — taskbar desk bar + conversation recording |
| `plan-audit-map.stdio.local.json` | stdio direct | Headless / no Python / no bar wanted |
| `plan-audit-map.sse.json` | HTTP SSE | Client supports URLs; run the server first (`windows/planauditmap_localhost.bat` or `node dist/index.js --sse --port 8002`) |
| `claude-desktop.local.json` | stdio via launcher | Claude Desktop (`%APPDATA%\Claude\claude_desktop_config.json`) |
| `qwen-desktop.local.json` | stdio | Qwen Desktop app / qwen-studio — **see the notes below, Qwen is non-standard** |
| `qwen-code-settings.local.json` | stdio | Qwen Code CLI (`~/.qwen/settings.json` or `.qwen/settings.json`) |

## What the launcher wrapper buys you

`planauditmap_launcher.py` is a byte-transparent stdio proxy that:

1. **starts the taskbar desk bar** on Windows (click the bar → recent-activity
   overview → the single "SQL Viewer" button),
2. **records every JSON-RPC request/response pair** into the `raw_mcp_events`
   table of `~/.plan-audit-map/memory.db` — this is the table that powers the
   viewer's *Raw Events* conversation transcript; the bare server never
   creates it,
3. mirrors everything to `~/.plan-audit-map/raw-mcp-events.jsonl` as a
   crash-safe fallback.

Without the launcher you still get the server + memory DB, but no bar and no
wire capture.

## Qwen Desktop — the non-standard bits (short version)

Full write-up in [`../RESEARCH-qwen-desktop.md`](../RESEARCH-qwen-desktop.md).

- **Qwen Code (CLI)** is *standard*: `mcpServers` in `~/.qwen/settings.json`,
  or `qwen mcp add plan-audit-map --transport stdio -- node <abs>/dist/index.js`.
- **Qwen Desktop (official Electron app)** is *not standard*: chat.qwen.ai
  has **no API to register custom MCP servers** — the web UI asks the desktop
  shell for config via injected `window.electronAPI` IPC. Add servers in the
  app's own settings UI.
- The official app **rewrites runners**: `npx` → bundled `bun x -y`, `uvx` →
  bundled uvx, and it **replaces PATH** with its resources dir. Always use
  **absolute paths** (`C:/.../node.exe`, not `node`) in Qwen configs — that's
  what the resolved `.local.json` files contain.
- **qwen-studio** (the Linux desktop port, Tauri) stores its MCP config in
  `~/.config/qwen-studio/settings.json` under `mcpServers` and spawns each
  server via `node mcp-bridge.mjs` (official SDK `StdioClientTransport`).
- The launcher auto-tags Qwen traffic as `provider: qwen-desktop` via
  `PLAN_AUDIT_MAP_PROVIDER` (set in the JSON) or Tauri env markers, so you can
  filter by client in the viewer.
