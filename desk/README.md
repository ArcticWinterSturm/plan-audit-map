# plan-audit-map-desk — desk bar + wire tap + SQL viewer + auto-install

A drop-in companion for the **[geeknik/plan-audit-map](https://github.com/geeknik/plan-audit-map)**
MCP server (fork of **[mettamatt/code-reasoning](https://github.com/mettamatt/code-reasoning)**).

Drop this folder into a repo zip of `plan-audit-map` (or any empty folder — the
installer will clone the repo), run **`install.bat`** on Windows or
**`install.sh`** on Linux/macOS, and you get:

- a built, patched **plan-audit-map server** (`dist/index.js`, stdio + SSE +
  tunnels + web dashboard),
- a **taskbar desk bar** (Windows): click it → recent-activity overview →
  exactly one button, **SQL Viewer**,
- the **🛟 Intervention paste bar** (v1.1): paste a circling agent's last
  messages, get back a copy-paste rescue built from the skills folder +
  the memory DB + a measured improvement estimate — see below,
- the **launcher / wire tap**: a transparent stdio proxy that records every
  MCP request/response pair so conversations are actually visible in the
  viewer,
- the **SQL viewer** (Tkinter, stdlib-only): sessions, thought timeline,
  branch/revision graph, analytics, search, bookmarks, export, and a
  conversation transcript built from the wire capture,
- **paste-ready MCP connection JSONs** for Claude Desktop, Qwen (all three
  flavours — see `RESEARCH-qwen-desktop.md`), SSE clients, and plain stdio.

```
plan-audit-map-desk/
├── install.bat / install.sh     one-shot installers (see below)
├── desk/                        python desk stack (stdlib only)
│   ├── mtd_shared.py              paths, config, raw-event store, activity feed
│   ├── mtd_intervention.py        🛟 intervention engine (embeddings, retrieval, estimate)
│   ├── planauditmap_bar.pyw         the taskbar bar (Win32 appbar, Windows)
│   ├── planauditmap_launcher.py     stdio proxy / wire tap / bar starter
│   └── planauditmap_viewer.py       the SQL viewer
├── skills/                      🛟 the ONE folder the paste bar indexes (*.md)
├── server/                      enhanced server overlay (copied into the repo)
│   ├── index.ts                   CLI (SSE/tunnel/token flags)
│   ├── server.ts                  server + dashboard + EOF/DB-path fixes
│   ├── config.ts                  → src/utils/config.ts (env-aware paths)
│   └── package.json               deps pinned (better-sqlite3 ^12.11.1, Node 20–26+)
├── connect/                     MCP client JSON templates (+ *.local.json after install)
├── windows/                     double-click launchers (SSE/LAN/token/remote/stdio, bar helper)
├── tools/install_helpers.py     post-build config + JSON resolver
├── RESEARCH-qwen-desktop.md     how Qwen desktop connects (non-standard) — research
└── README.md                    this file
```

## Install

**Windows** (in the folder after unzipping the repo + this folder):
```bat
install.bat            :: everything; or: install.bat --with-bar
```

**Linux / macOS:**
```bash
./install.sh           # everything; or: ./install.sh --with-bar
```

The installer finds the repo (same folder, parent, `plan-audit-map/` subdir — or
clones it), overlays `server/` onto the repo sources, `npm install`s, builds
`dist/`, writes `~/.plan-audit-map/desk-bar.json`, and resolves
`connect/*.json` → `*.local.json` with absolute paths. Requirements:
Node ≥ 20 and Python 3.9+ (bar/viewer only). No pip packages — the desk
stack is 100 % stdlib.

Then connect a client with `connect/plan-audit-map.stdio+desk.local.json`
(recommended — bar + conversation recording) or `plan-audit-map.stdio.local.json`
(bare server). Details: [`connect/README.md`](connect/README.md).

## What the dependabot `npm_and_yarn-a8e7958c52` branch offers over main

That branch (`9e57542`, one commit over `main` @ `1d6735d`) is a Dependabot
**dependency-group bump** — no features, no code changes. Direct deps:

| Package | main | branch |
|---|---|---|
| `@modelcontextprotocol/sdk` | ^1.11.2 | **^1.26.0** |
| `mathjs` | ^14.5.3 | **^15.2.0** |
| `@typescript-eslint/eslint-plugin` | ^8.32.1 | **^8.69.0** |
| `@typescript-eslint/parser` | ^8.32.1 | **^8.69.0** |

…plus ~6 transitive bumps in the lockfile (brace-expansion, mime-db,
ajv-formats, hono/node-server bits, etc. — 10 updates total, 557 insertions /
507 deletions, all in `package.json` + `package-lock.json`).
The SDK 1.11→1.26 jump is the meaningful one (newer transports, bug fixes,
completions capability). This package **already carries those bumps** (see
`server/package.json`) while keeping `better-sqlite3` at **^12.5.0** — see the
bug sweep below for why.

For context, geeknik's fork itself over the original `mettamatt/code-reasoning`:
adds the whole `src/cognitive/*` orchestrator (multi-persona reasoning, bias
detection, insight detection, plugin system, MCP client integration, self-
modifying architecture), `src/memory/*` (SQLite store replacing in-memory),
`src/state/*`, prompt templates + plugins, evaluations, and renames the tool
`code-reasoning` → `plan-audit-map` (legacy alias accepted).

## Bug sweep — what was broken and what's fixed here

Verified by building and running the full stack (Node 20, Linux CI-style
harness; Windows-specific paths compiled + code-reviewed):

### Critical (the "something is broken" set)

1. **Wire tap never wrote to the DB** — `RawEventStore` created its SQLite
   connection on the main thread and used it from the pipe threads;
   CPython forbids that (`check_same_thread`) and every insert failed
   silently (only the JSONL mirror survived). → connection now opens with
   `check_same_thread=False` (all access already lock-serialised).
2. **Launcher deadlocked the client→server direction** — `sys.stdin.buffer`
   is a `BufferedReader`; `read(8192)` blocks until **all** 8192 bytes
   arrive. MCP frames are ~100 bytes, so nothing reached the server until
   8 KiB piled up. → raw `os.read()` returns whatever is available.
3. **Launcher never exited / leaked the server** — after client EOF it kept
   the child's stdin open, so the pair hung forever (the loop waited for a
   server that never saw EOF). → EOF is now forwarded (half-close), total
   lifecycle for a session: ~3 s, exit 0.
4. **Server ignored stdin EOF** — the custom `FilteredStdioServerTransport`
   overrode `start()` without registering the base class's `end`/`close`
   handling: any direct stdio use leaked one zombie `node.exe` per client
   disconnect. → EOF handler + force-exit watchdog.
5. **Server segfaulted on Node 20** — the modified `package.json` pinned
   `better-sqlite3@^13.0.3`, which requires Node ≥ 22; on Node 20 it
   segfaults *silently* (zero output, exit -11/139). → pinned back to
   `^12.5.0` (Node 20+, matches repo main and the dependabot branch).
6. **Split-brain database** — the Python side honours
   `PLAN_AUDIT_MAP_HOME`/`PLAN_AUDIT_MAP_DB` but the Node server hardcoded
   `~/.plan-audit-map/memory.db`; with an env override set, bar/viewer/tap
   watched one DB while the server wrote another (conversations "missing").
   → server now honours the same env vars (`server.ts` + `config.ts`).
7. **Sessions never linked to their wire events** — `extract_session_id()`
   looked for `content` at the message top level; real MCP tool responses
   nest it under `result`. → both locations checked; verified linking.
8. **Viewer refused to open launcher-created DBs** — any DB without a
   `sessions` table (e.g. created by the tap before the server writes) threw
   "no such table: sessions" and the open failed. → all reads guarded.

### Also fixed

9. **Scrambled "recent" ordering** — the server writes UTC `…Z` timestamps,
   SQLite writes naive local ones; SQL string ordering mixes zones. → all
   recent/activity queries order by `rowid`/`id` (insertion order) or sort
   via a timezone-aware parser (viewer).
10. **Viewer quick-search showed the wrong thought** — filtered listbox rows
    were indexed straight into the unfiltered thoughts list. → visible-index
    mapping everywhere (select, next/prev, bookmark).
11. **Raw Events tab showed half the conversation** — only a fixed list of
    response fields. → renders a proper request→response transcript
    (thought text, args, errors, durations) and falls back to the newest
    events across all sessions when the selected session has none.
12. **Overview popup didn't close on outside click** — `focus_displayof()`
    stays populated after focus loss. → `focus_get()`-based check.
13. **`open_viewer` crashed on Linux/macOS** — `creationflags=`/`startupinfo=`
    are Windows-only `Popen` kwargs (ValueError elsewhere). → kwargs only on
    Windows.
14. **Ticker stuck on the last tool call forever** — live IPC events never
    expired. → 45 s expiry, falls back to the DB activity feed.
15. **Strip mode overlapped a top-docked taskbar** → sits under it now; the
    bar also re-asserts its docked position every ~20 s (resolution changes,
    taskbar moves).
16. **Provider mis-detection for Qwen** — sniffing own argv never matches;
    detection now: `PLAN_AUDIT_MAP_PROVIDER` env → Tauri env markers → argv.
17. **Request/response pairing race** — the response thread can commit
    before the request thread (duplicate/orphan rows); unmatched responses
    are now folded into their late-arriving request rows.
18. **stdin-None crash under `pythonw`**, **pending-map wipe at 512 entries**
    (now trims oldest), **inbound notifications miscategorised as requests**,
    **graph crash on malformed thought numbers**, **search filter not
    cleared on session switch**, **`npm run build` breaks on Windows**
    (`chmod` in the script → `install.bat` uses `npx tsc`; overlay
    `package.json` uses `build: tsc`), **installer's tsc compiling the
    dropped-in overlay folder** (repo `tsconfig.json` now excludes it),
    and the **hardcoded `C:\Users\User\...` paths in the .bat launchers**
    (now relative, with a dist-exists check).

## The Intervention Paste Bar (v1.1)

**The failure it targets.** Weak/preview models do plan-audit-map for the
first stretch of a solution, then silently drop back to native
chain-of-thought that is uninformed by prior errors — and start flailing in
circles. The desk bar's overview now has a second tab, **🛟 Intervene**
(also: the "🛟 Intervene" segment on the bar strip, the right-click menu, or
`planauditmap_launcher.py --open-intervention`).

**The flow — two copy-paste round trips, no pre-loaded ground truth:**

1. You copy the agent's last few messages (the circling part) and paste
   them into the bar. `Analyze` (or Ctrl+Enter).
2. The bar runs entirely local, in a background thread:
   - **retrieval** — every `*.md` in the skills folder is chunked,
     embedded and cached; the paste is embedded with the same model and the
     top chunks are pulled (hybrid score: 0.65 embedding cosine + 0.35
     lexical overlap, so it works even on the offline fallback embedder),
   - **prior work** — the memory DB is mined for thoughts/outcomes that
     overlap the paste's terms, the best prior session, the agent's last
     recorded cognitive state (the MCP's own metrics), the calibration
     table, and wire-log evidence that tool usage stopped,
   - **diagnostics** — repeated-5-gram ratio, longest repeated block,
     retry/hedge marker count of the paste itself,
   - **the number** — an estimated improvement from re-engaging the MCP
     (e.g. "~14%"), derived ONLY from the measurements above:
     `rep_ratio×25 + calibration_gap×30 + recall×20 + 4·(mcp-dropped)`,
     ×0.6 transfer, clamped 5–45. Every input and the arithmetic are
     printed in the message so the estimate can be argued with, never a
     placeholder.
3. The intervention block is **already on the clipboard** — paste it into
   the agent. It contains, in priority order under a hard token budget:
   the diagnosis with real numbers, retrieved skill chunks, a seeded
   `plan-audit-map` first call (continuing the best prior session when
   possible), and the instruction to record outcomes with
   `plan-audit-map-feedback` so the *next* intervention retrieves the
   agent's own fix.

If the agent can re-derive a better solution from the injected framing —
good. If not, the retrieved chunk points at the documented fix anyway.

**Embedding providers** (auto-detected, config under `intervention` in
`desk-bar.json`): Ollama at `127.0.0.1:11434` with `nomic-embed-text`
(recommended: `ollama pull nomic-embed-text`) → LM Studio at
`127.0.0.1:1234` (OpenAI-compatible) → deterministic offline hashed
n-gram fallback (no server needed; keyword-grade, honest about it).
Explicit choice via `embedding_provider`
(`auto|ollama|lmstudio|nomic|local`), custom `embedding_endpoint`, and
`embedding_model`. The chunk index is cached at
`~/.plan-audit-map/skills-index.json` and rebuilt incrementally when skill
files change (mtime+size; only changed files re-embed). Cache is keyed to
the provider, so switching providers rebuilds cleanly.

**Skills folder** — drop `*.md` files into `skills/` (READMEs are skipped).
Format tips are in `skills/README.md`. Four ship with this build, including
the field-tested install skill distilled from a successful agent install.

- **Bar** (Windows): started automatically with the server by the launcher,
  or `windows/start_desk_bar.bat`. Left-click → overview; the one button
  opens the SQL viewer; right-click → menu (hide/refresh/quit).
- **Viewer**: `python desk/planauditmap_viewer.py` (auto-finds
  `~/.plan-audit-map/memory.db`). F5 refresh, Ctrl+F search, double-click a
  session to export.
- **No-bar mode**: `planauditmap_launcher.py --no-bar -- node dist/index.js`
  still records conversations.
- **SSE**: `windows/planauditmap_localhost.bat` / `--local` / `--remote`
  (tunnel) / `--token`; connect `connect/plan-audit-map.sse.json`.

Env overrides (all optional): `PLAN_AUDIT_MAP_HOME` (data dir, default
`~/.plan-audit-map`), `PLAN_AUDIT_MAP_DB` (explicit DB file),
`PLAN_AUDIT_MAP_PROVIDER` (provider tag for wire events).

## Changelog

**v1.1.1 — the test RAG (`skills-test/`)**

- `skills-test/corpus/` — 18 skill documents, ~102 KB, written from
  field-tested knowledge of this stack (verbatim failure signatures,
  the better-sqlite3 ABI matrix, Qwen desktop internals, cross-file
  invariants) — knowledge a spec dump cannot contain.
- `skills-test/rag_eval.py` — offline, deterministic eval harness: 21
  labelled synthetic circling traces fired at the real intervention
  engine (`desk/mtd_intervention.py` with the offline hashed embedder)
  plus structural corpus checks. Run `python3 rag_eval.py` from
  `skills-test/`; exit 0 = pass.
- Current score: **top-1 86 % (18/21), top-3 100 % (21/21)**, every
  corpus file titled and sectioned per the chunker's own rules.
- This corpus doubles as a reference for *how* to write a skill
  document the retrieval engine actually likes: `## `-sectioned chunks
  under the 1400-char window, symptom vocabulary up front, tables for
  exact-value knowledge.

**v1.1.0 — the Intervention Paste Bar**
- New `desk/mtd_intervention.py`: skills-folder chunker, embedding
  providers (Ollama/LM Studio/Nomic cloud/offline hashed), cached
  incremental index, hybrid retrieval, circularity diagnostics, memory-DB
  mining (prior work, calibration, cognitive state, MCP-drop evidence) and
  the measured improvement estimate with shown work.
- Bar: overview is now tabbed (Recent activity / 🛟 Intervene); strip
  segment + right-click menu + IPC message + `--open-intervention`
  launcher flag; analysis runs off the Tk thread; result auto-copied to
  the clipboard (keeps the whole rescue at two C+V round trips).
- `skills/` folder with four skill documents (incl. the field install
  skill); installer points `intervention.skills_dir` at it.
- Field fixes adopted from the agent-driven install: `better-sqlite3`
  pinned `^12.11.1` (12.5.x fails to compile on Node ≥ 26), documented
  overlay-vs-repo patch ordering.
- Fixes found while testing the new UI: `ABE_BOTTOM/ABE_TOP` NameError
  crashed `_dock()` on non-Windows; intervention message now budgets by
  priority (the instruction can no longer be truncated away by chunk
  text); `diagnose()` UnboundLocalError on <5-token pastes;
  `intervention_config()` accepts both flat and nested config shapes;
  `--open-intervention` argparse flag was missing.
- Verified: full UI flow under Xvfb (popup, tab, analysis thread,
  clipboard, IPC, guards), Ollama path against a mock server, offline
  fallback, index cache reuse (5 ms second run), and the estimator output
  end-to-end.

