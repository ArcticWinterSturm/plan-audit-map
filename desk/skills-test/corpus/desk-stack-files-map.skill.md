# Skill: plan-audit-map-desk files, config, ports and relocation map

## What lives where (authoritative layout)

The drop-in folder `plan-audit-map-desk/` contains four layers that install
into a repo checkout of geeknik/plan-audit-map:

| Path | Role |
|---|---|
| `desk/mtd_shared.py` | paths, config load/save, `raw_mcp_events` store, activity feed — imported by every other desk script |
| `desk/planauditmap_bar.pyw` | the taskbar bar (Win32 appbar or strip mode) |
| `desk/planauditmap_launcher.py` | stdio proxy + wire tap + bar starter; sits between MCP client and `node dist/index.js` |
| `desk/planauditmap_viewer.py` | Tkinter SQL viewer for `memory.db` |
| `desk/mtd_intervention.py` | intervention paste-bar engine (embeddings, retrieval, estimate) |
| `skills/*.md` | the ONE folder the paste bar indexes (README* skipped) |
| `server/index.ts` | overlay → repo `index.ts` (CLI flags for SSE/tunnels) |
| `server/server.ts` | overlay → repo `src/server.ts` (enhanced server + fixes) |
| `server/config.ts` | overlay → repo `src/utils/config.ts` (env-aware paths) |
| `server/package.json` | overlay → repo `package.json` (pinned deps) |
| `connect/*.json` | client templates; installer resolves `__NODE__`, `__PYTHON__`, `__DIST_INDEX__`, `__DESK_DIR__` into `*.local.json` |
| `windows/*.bat` | SSE/LAN/token/remote/stdio launchers + `start_desk_bar.bat` helper |
| `tools/install_helpers.py` | writes `desk-bar.json` + resolves connect templates |
| `install.sh` / `install.bat` | one-shot installers |

## Every config key in ~/.plan-audit-map/desk-bar.json

Defaults (user file is merged over these; the `intervention` section merges
one level deep so editing only `top_k` keeps the rest):

| Key | Default | Meaning |
|---|---|---|
| `enabled` | true | bar runs at all |
| `bar_height` | 30 | pixels |
| `dock_edge` | bottom | bottom or top |
| `sit_above_taskbar` | true | strip mode: float above the taskbar instead of registering a Win32 appbar |
| `opacity` | 0.96 | bar alpha |
| `bar_port` | 38457 | localhost IPC port (single instance + live feed) |
| `poll_seconds` | 3 | DB re-read interval |
| `activity_limit` | 60 | rows in the overview feed |
| `autostart_with_server` | true | launcher starts the bar |
| `viewer_script` | planauditmap_viewer.py | resolved by installer to absolute path |
| `python_exe` / `pythonw_exe` | "" | empty = auto-detect |
| `server_command` | "" | e.g. `["node", "/abs/plan-audit-map/dist/index.js"]` |
| `log_raw_events` | true | tap writes `raw_mcp_events` |
| `mirror_jsonl` | true | tap also writes `raw-mcp-events.jsonl` |
| `max_payload_bytes` | 262144 | truncate stored payloads |
| `intervention.skills_dir` | "" | "" = `<desk>/skills`, then `<desk>/../skills`, then `~/.plan-audit-map/skills` |

## Intervention config keys (desk-bar.json, `intervention` section)

| `intervention.skills_dir` | "" | "" = `<desk>/skills`, then `<desk>/../skills`, then `~/.plan-audit-map/skills` |
| `intervention.embedding_provider` | auto | auto, ollama, lmstudio, nomic, local |
| `intervention.embedding_endpoint` | "" | e.g. http://127.0.0.1:11434 |
| `intervention.embedding_model` | nomic-embed-text | |
| `intervention.top_k` / `min_score` | 3 / 0.04 | retrieval count / floor |
| `intervention.max_chunk_chars` | 1400 | chunker window |
| `intervention.max_message_chars` | 3000 | intervention block budget |
| `intervention.min_paste_chars` | 40 | below this: "paste more" |
| `intervention.max_paste_chars` | 12000 | analyse at most this much |

## Environment variables (checked in this order)

| Variable | Effect |
|---|---|
| `PLAN_AUDIT_MAP_HOME` | data dir (default `~/.plan-audit-map`) — honoured by BOTH the Python stack and the patched Node server |
| `PLAN_AUDIT_MAP_CONFIG_DIR` | alias of HOME, checked second |
| `PLAN_AUDIT_MAP_DB` / `PLAN_AUDIT_MAP_MEMORY_DB` | explicit DB file, overrides HOME join |
| `PLAN_AUDIT_MAP_PROVIDER` / `MAPTHINKDO_PROVIDER` / `MTD_PROVIDER` | provider tag written to wire events (beats env sniffing) |
| `NOMIC_API_KEY` | enables the nomic cloud embedder (paid) |

Files inside the data dir: `memory.db` (+ `-wal`/`-shm`), `desk-bar.json`,
`raw-mcp-events.jsonl`, `skills-index.json`, `prompt_values.json`,
`prompts/`, `plugins/`, `mcp-servers.json`.

## IPC protocol on 127.0.0.1:38457

Line-delimited JSON. The bar is the server; launcher and any script are
clients. Message types: `ping` (bar answers `pong`), `wake` (un-hide bar),
`show` (show bar + toggle overview), `intervene` (open the Intervene tab),
`quit` (bar exits), `server` (`{"state":"up|down","pid":…,"exit_code":…}`),
`mcp` (live tool-call event for the ticker). If the port is busy the bar
assumes another instance runs, sends `wake`, exits 0/1.

## Relocation procedure (after moving the folder)

Absolute paths are baked into exactly two places after install:
`~/.plan-audit-map/desk-bar.json` (`viewer_script`, `server_command[1]`) and
`plan-audit-map-desk/connect/*.local.json` (every `__TOKEN__` already
resolved). Rewrite both to the new location, then re-run the smoke test:
pipe `initialize` + `notifications/initialized` + one `tools/call` through
`planauditmap_launcher.py --no-bar -- node <new>/dist/index.js` and confirm
`raw_mcp_events`, `sessions`, `thoughts` all gain rows in `memory.db`.
Row counts are the ground truth; log lines are not.

## Installer step order (and why the order matters)

`install.sh`/`install.bat`: (1) find repo — same dir, parent,
`plan-audit-map/` child, else `--repo PATH`, else clone; (2) copy the four
`server/` overlays over the repo sources — a later overlay copy silently
undoes any edit made to the repo copy first, so patch the OVERLAY when
patching deps; (3) exclude the desk folder name from the repo
`tsconfig.json` (its `include ./**/*.ts` would otherwise compile the
overlay copies in place and fail on their broken relative imports); (4)
`npm install` + `npx tsc` + `node dist/index.js --help` smoke test; (5)
`tools/install_helpers.py` writes `desk-bar.json` and resolves the six
connect templates; (6) optional `--with-bar` starts the bar. On Windows
the overlay `package.json` intentionally uses `build: tsc` — the upstream
`tsc && chmod +x …` script cannot run under cmd.exe.

## Data-dir file inventory (~/.plan-audit-map/)

| File | Writer | Purpose |
|---|---|---|
| `memory.db` (+`-wal`, `-shm`) | server + tap + viewer | the one database; see the schema skill |
| `desk-bar.json` | installer/user | bar + launcher + intervention config |
| `raw-mcp-events.jsonl` | tap | crash-safe mirror of every wire event (one JSON per line: ts, direction, provider, transport, session_id, message) — if the DB is locked/missing, the tap keeps writing here and the conversation survives |
| `skills-index.json` | intervention engine | chunk+vector cache, provider-keyed, mtime+size incremental |
| `prompt_values.json` | server | prompt template values |
| `prompts/` | user | custom prompt .md files loaded at server start |
| `plugins/` | server | cognitive plugin drop dir |
| `mcp-servers.json` | server | MCP client/plugin integration config |

## IPC payloads, exactly

`server`: `{"type":"server","state":"up|down","pid":123,"command":[…]}`
on launch, `{"state":"down","exit_code":0}` on exit. `mcp`:
`{"type":"mcp","direction":"request|response|notification|server-request",
"stream":"in|out","tool":"plan-audit-map","method":"tools/call","text":"…",
"thought_number":n,"total_thoughts":m,"session_id":"session_…",
"error":"…" (only on errors)}` — the bar's ticker renders `→ tool` on
requests, `← tool` on results, `✗ tool` on errors. Any client can send
`{"type":"intervene"}` to pop the paste bar — `start_desk_bar.bat`
option 5 does exactly this via the launcher.

## Install troubleshooting quick table

| Symptom | Fix |
|---|---|
| `cannot create regular file '…/src/server.ts'` | installer pointed at a stub copy — use `--repo` with the full repo (`test -d <repo>/src`) |
| tsc compiles the desk folder | keep the tsconfig exclude line the installer added |
| connect/*.local.json missing | re-run `tools/install_helpers.py` (needs python) |
| desk-bar.json points at old paths after a move | edit `viewer_script` + `server_command[1]`, re-run smoke test |
| bar does not start on Linux | it is Windows-first; on Linux use the viewer directly |

## Config precedence and common misconfigurations

desk-bar.json wins over defaults key-by-key; unknown keys are ignored
(not an error). Precedence for the launcher's server command: CLI
arguments after `--` > `server_command` in desk-bar.json > error with a
usage hint. Provider tagging: `--client NAME` sets the client column;
`PLAN_AUDIT_MAP_PROVIDER` sets the provider column; they are different
fields and both land in `raw_mcp_events`. Misconfigurations seen in the
wild: pointing `viewer_script` at the old location after a move
(symptom: SQL Viewer button does nothing, bar flashes "viewer script
not found"); setting `bar_port` to something in use by another app
(symptom: bar never starts, "port busy" in stderr — the bar INTENTIONALLY
treats busy as "another instance"); `server_command` with a relative
node path (breaks when the client's cwd differs — use absolute or bare
`node` which resolves on PATH).
