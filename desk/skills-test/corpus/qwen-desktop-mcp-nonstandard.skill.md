# Skill: Qwen MCP wiring — three different Qwens, two of them non-standard

## First: which Qwen are you holding?

| Product | Config location | Standard? |
|---|---|---|
| Qwen Code (CLI, Gemini-CLI fork) | `~/.qwen/settings.json` (user) / `.qwen/settings.json` (project); `qwen mcp add …` | standard MCP |
| Qwen Desktop (official Electron app, win/mac) | app settings UI; stored under key `mcp_config` via electron-settings | NOT standard |
| qwen-studio (community Linux port, Tauri v2) | `~/.config/qwen-studio/settings.json` under `mcpServers` | NOT standard bridge |

Diagnose from the symptom: "works in Claude Desktop, zero tools in Qwen"
with the SAME `npx` entry is the official desktop app rewriting your
command — see the runner-rewriting section.

## Official Qwen Desktop: how it actually works (v1.0.3.44, extracted)

The app is an Electron shell loading `https://chat.qwen.ai` (custom
User-Agent suffix `AliDesktop(QWENCHAT/<version>)`). The web page has NO
custom-MCP API of its own — probed and confirmed 404: `POST
/api/v2/mcp/config`, `GET /api/v2/mcp/servers`, `GET /api/v2/mcp/custom`.
Only `GET /api/v2/mcp/list` works and it returns the four built-ins
(`code-interpreter` local, `fire-crawl` mcpo, `amap` sse,
`image-generation` local). Custom servers MUST be configured locally in
the desktop shell: a preload script injects `window.electronAPI` and the
page calls `mcp_client_get_config` / `mcp_client_update_config` /
`mcp_client_tool_list` / `mcp_client_tool_call` over IPC. Your "MCP
settings" live in the Electron main process, not on the domain and not in
any spec-defined file.

## Runner rewriting: the trap that eats npx entries

Before spawning a configured server, the official app rewrites commands:
- `npx` (and `bun`) → the app's BUNDLED bun binary, with
  `args.unshift("-y", "x")` so `npx pkg` becomes `bun x -y pkg`
- `uvx` → the bundled uvx binary
- and it REPLACES `PATH` with
  `resources/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`

Consequences: an `npx`-style entry silently runs under Bun (different
runtime, different native-module support); bare `node`/`python` in `PATH`
terms only resolve if they live on those system paths. RULE: in any Qwen
config, always use ABSOLUTE paths for `command`
(`C:/dev/node/node.exe`, `/usr/bin/python3`) and never rely on `npx`.
This is why generated connect JSONs for Qwen carry absolute paths.

## The MCP client inside the official app

Not the reference SDK — it is Alibaba's internal `@ali/spark-mcp`
(v1.0.5-beta.12): an Express HTTP sidecar exposing `/setConfig`,
`/getConfig`, `/connect`, `/close`, `/listTools`, `/callTool`. If you are
debugging Qwen traffic and see requests to those paths on localhost,
that is this proxy, not your server misbehaving. Login flows use the
`qwen://` deep link (`qwen://open?token=…`).

## qwen-studio (Linux port): mcp-bridge.mjs

The Tauri port replaces spark-mcp with its own sidecar, `mcp-bridge.mjs`:
a Node process speaking NDJSON on ITS stdin/stdout
(`{"id":N,"method":"connect|disconnect|listTools|callTool|getConfig|
updateConfig"}`) and, internally, the official MCP SDK
`Client` + `StdioClientTransport` to spawn each configured server with
`env = {...process.env, ...config.env}`. Because that inner transport is
the standard SDK, wrapping plan-audit-map in the python launcher works
here — the bridge cannot tell the difference. Config auto-adds its own
`qwen-core` server on first launch. The Tauri shell exports
`TAURI_ENV_PLATFORM` / `TAURI_ENV_ARCH` / `TAURI_ENV_FAMILY` into every
child process — the wire tap uses these as a reliable
`provider: qwen-desktop` marker (plus `PLAN_AUDIT_MAP_PROVIDER`).

## Working recipes

Qwen Code: `qwen mcp add plan-audit-map --transport stdio --scope user --
/abs/node /abs/plan-audit-map/dist/index.js` or the `mcpServers` block in
`~/.qwen/settings.json` (supports command/args/env/cwd/timeout/trust,
plus httpUrl/url entries for remote servers).

qwen-studio: paste the `mcpServers` map into
`~/.config/qwen-studio/settings.json` or use the in-app settings; give
absolute `python3` + launcher args for the full desk-bar experience, and
set `"env": {"PLAN_AUDIT_MAP_PROVIDER": "qwen-desktop"}` so wire events
are tagged.

Official desktop: settings UI only; absolute paths; no `npx`. If tools
still do not appear, verify the app can execute your command at all
(its PATH is replaced) before blaming the server.

## Auth and deep links

Official app login flows over `qwen://open?token=…`; the renderer
receives `set_cookie` events over the `event_from_main` IPC channel.
Window behavior: macOS close = hide (app keeps running); Windows/Linux
close = quit. Auto-update provider `https://download.qwen.ai/` with
autoInstallOnQuit. None of this affects MCP, but it explains ghost
"still running" states after closing the window on macOS.

## Provider detection internals (the tap side)

Order: `PLAN_AUDIT_MAP_PROVIDER`/`MAPTHINKDO_PROVIDER`/`MTD_PROVIDER` env
(explicit wins) → Claude markers (`CLAUDE_DESKTOP`, `CLAUDECODE`,
`ANTHROPIC_API_KEY`) → Tauri markers (`TAURI_ENV_PLATFORM`,
`TAURI_ENV_ARCH`, `TAURI_ENV_FAMILY` — inherited by everything qwen-studio
spawns, including `node mcp-bridge.mjs` and its children) → argv sniff
(last resort, mostly useless because the tap's own argv never contains
the parent's markers — this was the original "provider: unknown" bug).

## Trace matrix: symptom → which Qwen → fix

| Symptom | Likely | Fix |
|---|---|---|
| npx entry, zero tools, other clients fine | official desktop (bun rewrite) | absolute node.exe path |
| settings.json edits ignored (CLI reads them?) | you edited ~/.qwen but run the desktop app | edit the app's settings UI / qwen-studio file |
| `qwen mcp add` works but app shows nothing | CLI vs desktop are different products | configure the app separately |
| tools appear but calls time out | bridge spawn timeout (60 s connect in qwen-studio) | check server startup time; prebuild dist |
