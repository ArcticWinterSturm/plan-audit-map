# Skill: better-sqlite3 × Node version matrix (field-tested)

## The matrix

`better-sqlite3` is a native module: its compiled `.node` binary is built
against a specific V8/Node ABI. Version pins that this stack verified by
actually installing:

| better-sqlite3 | Node 20 | Node 22 | Node 24 | Node 26+ |
|---|---|---|---|---|
| `^13.0.3` | **SEGFAULT** | OK | OK | OK |
| `^12.5.0` | OK | OK | OK | **COMPILE FAIL** |
| `^12.11.1` | OK | OK | OK | OK |

- `^13.0.3` declares `engines: node >=22`. npm only WARNS
  (`EBADENGINE Unsupported engine`) — it does not stop the install — and
  the module then segfaults at require time on Node 20.
- `^12.5.0` compiles fine through Node 24 but fails to build on Node 26:
  V8 removed `PropertyCallbackInfo::This()`, so node-gyp dies inside the
  addon source with `info.This()` errors. No prebuilt exists for that
  combination.
- `^12.11.1` is the pin that spans Node 20 through 26+ and is what the
  overlay `server/package.json` ships.

## The silent-segfault signature (memorise this one)

Server exits instantly when any MCP client connects. No stdout, no
stderr, no stack trace. Exit code `-11` through the launcher, `139`
(SIGSEGV) in a shell. Direct run: nothing at all. THIS PATTERN — instant,
output-free, signal death — is a native-module ABI mismatch until proven
otherwise. Diagnosis, in order:
1. `node --version` — get the exact major.
2. `npm ls better-sqlite3` — which version actually installed.
3. Cross-check the matrix above; the fix is a pin bump, not a rebuild.

Do not waste time adding logging: the process dies inside the native
require before any application code runs. `npm cache clean`, deleting
`node_modules`, or "trying again" change nothing.

## Where to patch: the overlay, not the repo

In plan-audit-map-desk, `install.sh`/`install.bat` step 2 copies
`server/package.json` OVER the repo's `package.json`. Any version edit
made to the repo copy before install is silently undone. Patch
`plan-audit-map-desk/server/package.json` (the overlay), then run the
installer — or patch after the overlay step and build manually with
`npx tsc`.

## EBADENGINE vs compile errors — different problems

`npm warn EBADENGINE Unsupported engine … required node >=22, current
node v20.x` = the engines advisory. It is a WARNING; on Node 20 with
better-sqlite3@13 it precedes the segfault. An actual node-gyp COMPILE
error mentioning removed V8 C++ APIs (`PropertyCallbackInfo::This()`,
`info.This()`, `Nan::…`) = the module is too OLD for your Node — Node 26
with 12.5.x. The first fixes by downgrading the package, the second by
upgrading it. Check which direction you need before touching anything.

## When a compile is actually required

Prebuilt binaries ship for common platform/ABI pairs and download during
`npm install` (via the package's install script). A build from source
kicks in when no prebuilt matches. Toolchain needed:
- Windows: Visual Studio Build Tools (C++ workload) + Python — the
  classic `gyp ERR! find VS` failure means they are missing.
- macOS: Xcode Command Line Tools (`xcode-select --install`).
- Linux: `build-essential` + `python3` (`apt install -y build-essential
  python3`).

Escape hatch when install scripts fail or are blocked:
`npm install --ignore-scripts` then `npm rebuild better-sqlite3` — this
fetches/builds the native part alone. If a repo's `prepare` hook runs a
Unix-only command (`chmod +x dist/*.js`) and fails under cmd.exe, the
whole `npm install` fails at prepare; either fix the script (upstream
`build` becomes plain `tsc`) or install with `--ignore-scripts` and run
`tsc` manually.

## engines is advisory — verify, don't trust green installs

`npm install` exits 0 with only a warning when engines do not match, and
the failure mode at runtime is the silent segfault above. After any
install involving native modules, smoke-test before declaring victory:
`node dist/index.js --help` must print usage. If the server is launched
by an MCP client, also confirm rows appear in `memory.db` — a client that
"works" can still be masking an instantly-restarting server.

## Decision tree: server will not start

1. ANY output at all? → not the silent segfault; read it.
2. Exit -11 / 139 with zero output → native ABI. `node --version` +
   `npm ls better-sqlite3`, apply the matrix.
3. Exit 1 with a JS stack → application-level; check the DB path env
   vars and file permissions.
4. Exit 0 but client says nothing → the client's problem: did it send
   `notifications/initialized` before `tools/list`? See the protocol
   skill.

## Prebuilt download internals

better-sqlite3's install script computes `{platform}-{arch}-{abi}`
(e.g. `linux-x64-127`) and fetches a matching prebuilt from its release
host; `napi_versions`/`node_abi` in the package decide compatibility.
When the fetch fails (offline, proxy, unknown Node), it falls back to
node-gyp compile — which then needs the full C++ toolchain. That is why
the SAME install can succeed on one machine and require Visual Studio
Build Tools on another: the only difference may be which path it took.

## Version pins in this stack

The overlay `server/package.json` pins `better-sqlite3 ^12.11.1`,
`@modelcontextprotocol/sdk ^1.26.0`, `mathjs ^15.2.0`,
`@typescript-eslint/* ^8.69.0`, `@types/node ^22`. The repo's own
dependabot branch `npm_and_yarn-a8e7958c52` is exactly the
sdk/mathjs/eslint group bump (no better-sqlite3 change) — carrying it is
safe on Node 20 with the 12.11.1 pin.

## Worked diagnosis transcript (the shape a correct one takes)

"The server exits instantly, no output, -11 through the launcher.
node --version → v20.20.2. npm ls better-sqlite3 → 13.0.3@. Matrix:
13.x needs ≥22 → pin 12.x. Edited plan-audit-map-desk/server/package.json
(the overlay — a repo-side edit would be overwritten at install) to
^12.11.1, re-ran install.sh, node dist/index.js --help prints usage.
Done: 4 commands, ~2 minutes, no cache clearing, no node_modules
deletion, no reinstalling Node."

Contrast the flailing version — "let me npm cache clean, let me delete
node_modules, let me reinstall node, let me try again" — which never
asks which ABI is loaded and therefore cannot terminate.
