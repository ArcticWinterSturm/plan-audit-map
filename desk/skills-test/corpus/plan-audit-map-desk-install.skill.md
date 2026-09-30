# Skill: Install & Verify plan-audit-map-desk (Hermes agent)

> Source: attached verbatim from the field skill that was distilled from a
> successful agent-driven install of this build. Two of its findings are
> already folded into the build (better-sqlite3 ^12.11.1 for Node >= 26;
> the overlay-vs-repo patch ordering). Kept as the canonical install skill.

## Purpose
Install the plan-audit-map MCP server + desk stack from a workspace zip, prove the
reasoning pipeline logs into SQLite, open the viewer, then relocate the tree and
re-point every config that embeds absolute paths.

## Assumptions
- Workspace zip (`workspace-*.zip`) on the Desktop; extract it and work inside.
- Node >= 20 and Python 3.9+ (with tkinter for the viewer) are on PATH.
- Data home defaults to `~/.plan-audit-map/` (DB: `~/.plan-audit-map/memory.db`).
- A long-lived GUI/SSE process must be launched via the harness `background=true`
  flag — never `&` foreground backgrounding.

## Procedure

1. **Locate and extract** the zip from the Desktop into a working directory.

2. **Identify the real repo.** The export contains several `mtd` copies:
   - `work/mtd/` is a STUB (only `index.ts`, `server.ts`, `package.json`) —
     running the installer against it fails with
     `cannot create regular file '.../src/server.ts': No such file or directory`.
   - The full buildable repo is `work/incomplete/work/mtd/` (has `src/`,
     `tsconfig.json`, `package-lock.json`). Verify with `test -d <repo>/src`.

3. **Patch the OVERLAY first — not the repo.** In
   `plan-audit-map-desk/server/package.json` set `better-sqlite3` to `^12.11.1`.
   Rationale: `install.sh` step 2 copies `server/package.json` OVER the repo's
   `package.json`, so any edit made to the repo copy before install is silently
   undone. Pinned `^12.5.0` fails to compile on Node >= 26 (V8 removed
   `PropertyCallbackInfo::This()`; no prebuilt binaries for Node 26).

4. **Run the installer:**
   `bash plan-audit-map-desk/install.sh --repo <full-repo-path>`
   It overlays the enhanced server, runs `npm install` + `tsc`, writes
   `~/.plan-audit-map/desk-bar.json`, and resolves `connect/*.local.json`.

5. **Verify the build:** `node <repo>/dist/index.js --help` exits 0 and prints
   usage (flags: --sse, --port, --token, --local, --remote, --tunnel ...).

6. **Smoke-test the wire tap** by piping three JSON-RPC lines into the launcher:
   `initialize` -> `notifications/initialized` -> `tools/call`, run under
   `timeout`:
   ```
   printf '%s\n' '<initialize>' '<initialized>' '<tools/call>' | timeout 15 \
     python3 desk/planauditmap_launcher.py --no-bar -- node <repo>/dist/index.js
   ```
   - tool arguments are **snake_case**: `thought`, `thought_number`,
     `total_thoughts`, `next_thought_needed`. camelCase is rejected with
     "Unrecognized key(s) in object".
   - Expected reply: `status: "processed"`, a `session_id`, and `cognitive_state`.

7. **Verify by effect, not by logs.** Query `~/.plan-audit-map/memory.db`:
   `raw_mcp_events`, `sessions`, `thoughts` must all gain rows. Tables present:
   `raw_mcp_events, thoughts, sessions, outcomes, confidence_calibration,
   learning_patterns, thoughts_fts*`. The wire tap failing silently is the
   classic failure — the DB row counts are the ground truth.

8. **Open viewers:**
   - Tkinter SQL viewer: launch `desk/planauditmap_viewer.py [db-path]` as a
     long-lived background process with `DISPLAY` set (it needs an X server;
     a quick `timeout 5` run exiting 124 = it stayed open = healthy).
   - SSE dashboard: `node <repo>/dist/index.js --sse --port 8002` as a
     long-lived background process; UI at `http://localhost:8002/`.

9. **Relocate and re-point.** Move the workspace to its final location, then
   rewrite absolute paths in BOTH:
   - `~/.plan-audit-map/desk-bar.json` (`viewer_script`, `server_command[1]`)
   - `plan-audit-map-desk/connect/*.local.json`
   Then re-run steps 6-7 from the new path to prove nothing broke.

## Failure-mode table
| Symptom | Cause | Fix |
|---|---|---|
| `cannot create regular file .../src/server.ts` | installer pointed at stub `work/mtd/` | point `--repo` at `work/incomplete/work/mtd/` |
| npm EBADENGINE + `info.This()` compile errors | `better-sqlite3@12.5.0` on Node >= 26 | bump to `^12.11.1` in `server/package.json` (the overlay) |
| "Unrecognized key(s): thoughtNumber..." | camelCase tool args | use snake_case field names |
| Viewer exits instantly / no window | no X display | `DISPLAY=:0.0` + background process |
| `Foreground command uses '&'` error | harness rule | relaunch with `background=true` |
| Patching repo `package.json` had no effect | install.sh overlay overwrites it | patch the overlay source, or patch after overlay step and build manually |

## Pointers (authoritative source lives in the repo — do not duplicate)
- `plan-audit-map-desk/README.md` — full feature list and the 18-item bug sweep.
- `plan-audit-map-desk/install.sh` — installer source of truth.
- `plan-audit-map-desk/desk/` — viewer/launcher/bar source (stdlib-only Python).
- `plan-audit-map-desk/connect/*.local.json` — paste-ready MCP client configs.
- Response payload schema (`cognitive_state`, `action_ranking`, metrics) —
  inspect live rows in `memory.db` or the dashboard; not restated here.
