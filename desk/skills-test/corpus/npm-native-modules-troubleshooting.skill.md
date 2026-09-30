# Skill: npm + native modules — scripts, prepare hooks, builds

## How a native module install actually proceeds

`npm install` for a package like better-sqlite3 runs its lifecycle
scripts: typically `preinstall` → download a PREBUILT `.node` binary for
your platform/ABI → `install` → if no prebuilt matched, invoke
node-gyp to COMPILE against your local Node headers. Two very different
failure classes with opposite fixes:
- No output, process dies at require, exit -11/139 → prebuilt for the
  WRONG ABI (module too new/old for your Node major). Fix = version
  pin, not a rebuild. See the ABI matrix skill.
- node-gyp COMPILE errors naming V8 C++ APIs (`PropertyCallbackInfo`,
  `info.This()`, `Nan::…`) → no prebuilt exists for your Node major and
  the module's C++ is too old for it. Fix = newer module or older Node.

`npm ls better-sqlite3` + `node --version` answer "which class am I in"
in ten seconds. Do this BEFORE deleting node_modules or clearing caches.

## prepare hooks can fail the whole install

`prepare` runs on `npm install` (and on pack/git installs) AFTER
dependencies are placed — commonly `npm run build` → `tsc`. If prepare
fails, THE INSTALL FAILS, even though the package itself is fine. The
plan-audit-map overlay hit this twice:
- Upstream `build` was `tsc && chmod +x dist/*.js` — `chmod` does not
  exist under cmd.exe → `'chmod' is not recognized` → install dies at
  prepare on Windows. Fix: `build: tsc`.
- A repo tsconfig with `include ./**/*.ts` compiles a dropped-in folder
  of overlay sources whose relative imports only resolve from their
  intended locations → tsc errors → install dies. Fix: exclude the
  folder in tsconfig before install.

Escape hatch: `npm install --ignore-scripts` skips lifecycle scripts
entirely (also skips native prebuilds!) then `npm rebuild <pkg>` runs
just that package's build step. Manual alternative: install
ignore-scripts, `npx tsc` yourself, smoke-test the entrypoint.

## engines is a warning, not a gate

`"engines": {"node": ">=22"}` produces
`npm warn EBADENGINE Unsupported engine … current: {node v20.x}` and
npm exits 0. The landmine detonates later, at runtime (see the silent
segfault). Treat every green install of a native module as unverified
until `node <entrypoint> --help` (or equivalent) runs. If you want npm
to actually enforce engines: `engine-strict=true` in `.npmrc` — useful
in CI, hostile on mixed-fleet dev machines.

## Toolchain prerequisites for compiling

Windows: Visual Studio Build Tools with the C++ workload + Python
(failure looks like `gyp ERR! find VS`). macOS: Xcode Command Line
Tools (`xcode-select --install`). Debian/Ubuntu: `sudo apt install -y
build-essential python3`. node-gyp needs a Python that matches its
expectations (3.x); `npm config set python /path/python3` when multiple
Pythons confuse it.

## Lockfiles and the overlay-overwrite trap

`package-lock.json` pins the exact resolved tree; `^` ranges in
`package.json` float. Two structural traps in this repo family:
1. Editing the repo's `package.json` and running an installer that
   later copies ITS OWN `server/package.json` over it silently undoes
   your edit — patch the overlay source (or patch after the overlay
   step, then build manually).
2. Deleting the lockfile to "fix" a resolve error trades a known tree
   for whatever floats today — including an ABI-incompatible native
   version. Prefer explicit pins over lock deletion for native deps.

## Post-install verification ritual (30 seconds)

1. `node --version` and `npm ls <native-module>` — matrix check.
2. `node <entrypoint> --help` — catches require-time segfaults.
3. One end-to-end call through the real path (here: the launcher), then
   assert side effects (DB rows) — a working entrypoint behind a broken
   wrapper still fails here.

## .npmrc flags that matter here

`engine-strict=true` (fail instead of warn on engines), `ignore-scripts
true` (global escape hatch; remember to `npm rebuild` natives), `build
-from-source=true` (force compile even when a prebuilt exists — useful
to reproduce a toolchain problem), `python=/path/python3` for gyp.
Scripts also read `npm_config_*` env vars, which is how CI pins these
without touching files.

## CI recipe for this repo family

1. `node --version` (assert expected major — CI is where the ABI
   matrix bites silently otherwise)
2. `npm ci` (uses the lockfile exactly; fails on drift instead of
   resolving fresh — prefer over `npm install` in CI)
3. `npx tsc` (bypass prepare-hook quirks entirely)
4. `node dist/index.js --help` (require-time segfault detector)
5. One scripted MCP session through the launcher + assert DB row counts
   (end-to-end; catches EOF/proxy regressions)
6. Optional: `npm rebuild better-sqlite3` once, cache `node_modules`
   between runs keyed on Node version.
