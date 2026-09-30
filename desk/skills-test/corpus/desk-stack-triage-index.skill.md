# Skill: master triage — route any plan-audit-map-desk symptom to its fix

## How to use this file

This is the index, not the encyclopedia. Match your symptom, apply the
one-liner, then read the named skill for the full procedure. Skills
live in the same folder: wire-tap-internals, memory-db-schema,
node-sqlite3-abi-matrix, server-overlay-build, desk-bar-appbar-windows,
desk-bar-activity-feed, intervention-paste-bar, viewer-features-cookbook,
plan-audit-map-tool-schema, mcp-stdio-protocol, sqlite-multi-process-wal,
tkinter-pitfalls, npm-native-modules-troubleshooting,
qwen-desktop-mcp-nonstandard, circular-cot-signatures,
desk-stack-files-map, plan-audit-map-desk-install.

## Server will not start / dies instantly

| Signal | Route |
|---|---|
| exit -11 / 139, ZERO output, any client | better-sqlite3 ABI → node-sqlite3-abi-matrix |
| node-gyp compile error mentioning V8 C++ APIs | Node too new for module pin → node-sqlite3-abi-matrix |
| `'chmod' is not recognized` during npm install | prepare hook on Windows → npm-native-modules-troubleshooting |
| tsc errors about `./src/server.js` from the desk folder | tsconfig include → server-overlay-build |
| JS stack, mentions a path | env/path resolution → desk-stack-files-map |

## Client cannot talk to the server

| Signal | Route |
|---|---|
| hangs at startup THROUGH the launcher, fine direct | buffered-read proxy deadlock → wire-tap-internals |
| initialize answered, tools/list hangs | missing notifications/initialized → mcp-stdio-protocol |
| tools/call returns "Unrecognized key(s) in object" | camelCase args → plan-audit-map-tool-schema |
| works in Claude, zero tools in Qwen | runner rewriting → qwen-desktop-mcp-nonstandard |
| orphaned node.exe accumulating | stdin EOF not handled → server-overlay-build |

## Data looks wrong or missing

| Signal | Route |
|---|---|
| "(no raw_mcp_events table found)" in viewer | client bypasses launcher → wire-tap-internals |
| conversations rows exist but session ids NULL | extraction bug → wire-tap-internals |
| viewer crash "no such table: sessions" | tap-created empty DB → memory-db-schema |
| "recent" list order scrambled | Z vs naive timestamps → memory-db-schema |
| sessions in one place, conversations in another | split-brain DB paths → desk-stack-files-map |
| "database is locked" in tap stderr | WAL discipline → sqlite-multi-process-wal |
| bar all-zeros while client "works" | pipeline bypassed → desk-bar-activity-feed |

## The bar itself

| Signal | Route |
|---|---|
| bar covers the Start button / taskbar | edge + strip geometry → desk-bar-appbar-windows |
| bar ignores clicks, port 38457 busy | half-dead instance → desk-bar-appbar-windows |
| "main thread is not in main loop" crash | widget access from thread → tkinter-pitfalls |
| popup will not close on outside click | focus check → tkinter-pitfalls |
| clipboard empty after quitting (Linux) | X11 ownership → tkinter-pitfalls |
| AttributeError NoneType .buffer under pythonw | no-console stdio → tkinter-pitfalls |
| screen 30px shorter after a crash | ABM_REMOVE missing → desk-bar-appbar-windows |

## The intervention paste bar

| Signal | Route |
|---|---|
| "offline fallback" despite Ollama running | alive check/model name → intervention-paste-bar |
| "No skills folder found" | skills_dir resolution → intervention-paste-bar |
| wrong skill retrieved | vocabulary discipline → intervention-paste-bar |
| where does "~14%" come from | measured estimate formula → intervention-paste-bar |
| agent circles after first half done | signatures + response protocol → circular-cot-signatures |

## Install / relocate

| Signal | Route |
|---|---|
| `cannot create regular file …/src/server.ts` | stub repo, use --repo → plan-audit-map-desk-install |
| patching package.json "didn't stick" | overlay overwrites repo → npm-native-modules-troubleshooting |
| paths stale after moving the folder | rewrite desk-bar.json + *.local.json → desk-stack-files-map |
| verify an install without reading logs | DB row counts as ground truth → plan-audit-map-desk-install |

## The 60-second full-stack health check

1. `node <repo>/dist/index.js --help` — server startable (ABI).
2. Pipe initialize/initialized/tools/call through the launcher — proxy
   + server + EOF chain (mcp-stdio-protocol, wire-tap-internals).
3. Count the four tables in memory.db — every writer alive
   (memory-db-schema).
4. Bar up + counts non-zero — feed healthy (desk-bar-activity-feed).
5. One paste-bar analysis — retrieval + estimate path
   (intervention-paste-bar).
Each step isolates one layer; the first failing step is your bug, and
the skill named beside it holds the procedure.

## Golden rules (the five invariants behind every table above)

1. **Row counts are ground truth; log lines are gossip.** A client that
   "works" can mask a dead server; the DB tells the truth.
2. **One database.** Every process must resolve the same path via
   PLAN_AUDIT_MAP_HOME/PLAN_AUDIT_MAP_DB — split-brain is the #1 "missing
   data" cause.
3. **stdout is protocol.** Anything else a process wants to say goes to
   stderr, a socket, or a file — never the client-facing pipe.
4. **EOF is a message.** Both directions: forward it, handle it, exit
   on it. Zombie processes are unhandled EOFs.
5. **Absolute paths in third-party client configs.** Qwen rewrites
   runners and replaces PATH; bare `node`/`npx` entries are how tools
   silently never appear.
