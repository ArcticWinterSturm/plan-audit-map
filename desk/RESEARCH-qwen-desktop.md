# RESEARCH — How "QWEN desktop" connects to MCP servers (and why it's non-standard)

*Compiled 2026-09-07 from: the `qwen-studio` checkout included in the
workspace (v2.2.3, `youssefvdel/qwen-studio`, incl. its own analysis docs
`docs/MCP_DOMAIN_ANALYSIS.md` + `docs/OFFICIAL_APP_ANALYSIS.md` extracted
from the official `Qwen-1.0.3.44-release-win-x64.exe`), the
`mcp-bridge.mjs` / `mcp-proxy-server.js` source in that repo, and the public
Qwen Code MCP documentation.*

There are **three different "Qwen" things**, and each connects differently:

| Thing | What it is | MCP config | Standard? |
|---|---|---|---|
| **Qwen Code** | CLI (fork of Gemini CLI) | `mcpServers` in `~/.qwen/settings.json` (user) / `.qwen/settings.json` (project); `qwen mcp add …` | ✅ standard |
| **Qwen Desktop (official)** | Electron app wrapping chat.qwen.ai (internal repo `gitlab.alibaba-inc.com:qwenx/qwen-electron`) | stored under key `mcp_config` via `electron-settings`, edited in the app UI | ❌ non-standard |
| **qwen-studio (community Linux port)** | Tauri v2 app wrapping chat.qwen.ai | `mcpServers` in `~/.config/qwen-studio/settings.json`, edited in app UI | ❌ non-standard bridge |

## 1. Qwen Code (CLI) — the standard one

`~/.qwen/settings.json`:

```json
{
  "mcpServers": {
    "plan-audit-map": {
      "command": "/absolute/path/to/node",
      "args": ["/absolute/path/to/plan-audit-map/dist/index.js"],
      "env": { "PLAN_AUDIT_MAP_PROVIDER": "qwen-code" },
      "timeout": 30000
    }
  }
}
```

or `qwen mcp add plan-audit-map --transport stdio -- node /abs/dist/index.js`.
stdio / SSE / streamable-HTTP all supported; that's what
`connect/qwen-code-settings.local.json` is.

## 2. Qwen Desktop (official app) — how it actually works

Findings from the extracted official Windows app (v1.0.3.44):

1. The app is an **Electron shell around `https://chat.qwen.ai`**
   (custom UA suffix `AliDesktop(QWENCHAT/<version>)`, `webSecurity: false`,
   `nodeIntegrationInSubFrames: true`).
2. **chat.qwen.ai itself has no custom-MCP API.** Probed endpoints:
   `GET /api/v2/mcp/list` works (returns only the 4 built-ins:
   `code-interpreter` local, `fire-crawl` mcpo, `amap` sse,
   `image-generation` local) but `POST /api/v2/mcp/config`,
   `/api/v2/mcp/servers`, `/api/v2/mcp/custom` all 404. Custom servers must
   be configured **locally in the desktop shell**, not on the domain.
3. The web page gets tools through an **injected IPC bridge**: a preload
   script exposes `window.electronAPI`, and the page calls
   `mcp_client_get_config` / `mcp_client_update_config` /
   `mcp_client_tool_list` / `mcp_client_tool_call`. The web UI is literally
   rendered by what the desktop app feeds it — that's the non-standard part:
   your "MCP settings" live in the Electron main process, not in the web app
   and not in any spec-defined place.
4. Config storage: key `"mcp_config"` in the `electron-settings` store
   (OS-specific settings file). Format is the usual
   `{ "name": { "command", "args", "env" } }` map.
5. **Runner rewriting (important!):** before spawning a configured server the
   app rewrites commands — `npx`/`bun` → the **bundled `bun` binary** (with
   `args.unshift("-y", "x")` for npx), `uvx` → bundled uvx — and **replaces
   `PATH`** with `resources/bin:/usr/local/bin:/usr/bin:/bin:…`. Consequence:
   * `npx`-style entries run under Bun, not Node;
   * bare `node`/`python` only resolve if they live on one of those system
     paths.
   → **Use absolute paths in Qwen configs** (what the resolved
   `connect/qwen-desktop.local.json` provides).
6. The MCP client itself is an internal Alibaba package, **`@ali/spark-mcp`
   (v1.0.5-beta.12)** — an Express-based HTTP proxy with
   `/setConfig`, `/getConfig`, `/connect`, `/close`, `/listTools`,
   `/callTool` endpoints — *not* part of the MCP spec. (The official Qwen
   desktop app ships it as a local sidecar.)
7. Auth/login flows over the `qwen://` deep link (`qwen://open?token=…`).

## 3. qwen-studio (the Linux desktop client in the workspace)

The community port replaces `@ali/spark-mcp` with its own bridge, and this is
what the desk stack's provider-detection was written against:

- **`mcp-bridge.mjs`** — a Node sidecar spawned by the Tauri plugin
  (`tauri_plugin_mcp_bridge`). Protocol: **NDJSON over its stdin/stdout**
  (`{"id":N,"method":"connect|disconnect|listTools|callTool|getConfig|updateConfig"}`).
  Internally it uses the **official SDK**
  (`@modelcontextprotocol/sdk` `Client` + `StdioClientTransport`) to spawn
  each configured server as a normal stdio child process, with
  `env = {...process.env, ...config.env}`.
  → Because it's the *official SDK stdio transport*, pointing Qwen-studio at
  the python launcher (`planauditmap_launcher.py`) works, which is how the
  desk bar + conversation capture can run *inside* Qwen.
- **Config lives in `~/.config/qwen-studio/settings.json`** under
  `mcpServers`; the Rust side (`src/mcp.rs`) auto-adds its own `qwen-core`
  server on first launch.
- Tauri exports `TAURI_ENV_PLATFORM` / `TAURI_ENV_ARCH` / `TAURI_ENV_FAMILY`
  into every child process — the wire tap uses these as a reliable
  `provider: qwen-desktop` marker (in addition to `PLAN_AUDIT_MAP_PROVIDER`).

### Why conversations showed up "provider: unknown"

The original `_detect_provider()` sniffed its **own argv** for
`"qwen"`/`"mcp-bridge"` — but the launcher's argv never contains those
strings (they belong to the *parent* bridge process). Detection now happens
in this order: `PLAN_AUDIT_MAP_PROVIDER` env (set by the generated Qwen JSONs)
→ Tauri env markers → argv sniff.

## Practical connection recipes

**Qwen Code:**
```bash
qwen mcp add plan-audit-map --transport stdio --scope user \
  -- /abs/node /abs/plan-audit-map/dist/index.js
```

**qwen-studio (Linux):** open Settings → MCP, add server with
command = absolute `python3`, args =
`["/abs/plan-audit-map-desk/desk/planauditmap_launcher.py", "--client",
"qwen-desktop", "--", "/abs/node", "/abs/plan-audit-map/dist/index.js"]`
(or paste the whole `qwen-desktop.local.json` map into
`~/.config/qwen-studio/settings.json`).

**Official Qwen Desktop (Windows/macOS):** Settings → MCP/Tools → add
server; command = **absolute** `node.exe` path, args =
`["C:/.../plan-audit-map/dist/index.js"]`. Avoid `npx` entries — they silently
run under the app's bundled Bun.

## Sources

- workspace checkout `work/qstudio` (`mcp-bridge.mjs`, `mcp-proxy-server.js`,
  `src/mcp.rs`, `docs/MCP_DOMAIN_ANALYSIS.md`, `docs/OFFICIAL_APP_ANALYSIS.md`)
- Qwen Code MCP docs (settings schema, `qwen mcp add`, scopes):
  https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/mcp.md
  https://qwenlm.github.io/qwen-code-docs/en/developers/tools/mcp-server/
