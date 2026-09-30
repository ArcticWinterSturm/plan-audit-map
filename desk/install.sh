#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# plan-audit-map-desk — one-shot installer (Linux / macOS)
#
# What it does, in order:
#   1. finds the plan-audit-map repo (this folder dropped into a GitHub zip,
#      an existing checkout, or it clones/downloads a fresh copy)
#   2. overlays the enhanced server (SSE/tunnels/dashboard) + env-aware DB
#      paths on top of the repo sources
#   3. installs node dependencies and builds dist/ (TypeScript)
#   4. writes ~/.plan-audit-map/desk-bar.json so the taskbar bar / launcher /
#      SQL viewer know where everything lives
#   5. resolves connect/*.json templates into connect/*.local.json with
#      absolute paths, ready to paste into any MCP client
#   6. smoke-tests the built server
#
# Usage:
#   ./install.sh                 # everything, auto
#   ./install.sh --repo /path    # use an existing repo checkout
#   ./install.sh --no-install    # skip npm install (deps already present)
#   ./install.sh --with-bar      # also start the desk bar (needs a display)
# ---------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESK="$HERE/desk"
SERVER_SRC="$HERE/server"
CONNECT="$HERE/connect"
REPO=""
SKIP_INSTALL=0
WITH_BAR=0
CLONE_URL="https://github.com/geeknik/plan-audit-map.git"

c_ok()   { printf '\033[32m%s\033[0m\n' "$*"; }
c_info() { printf '\033[36m%s\033[0m\n' "$*"; }
c_warn() { printf '\033[33m%s\033[0m\n' "$*"; }
c_err()  { printf '\033[31m%s\033[0m\n' "$*"; }
step()   { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

for arg in "$@"; do
  case "$arg" in
    --repo) ;;
    --repo=*) REPO="${arg#--repo=}" ;;
    --no-install) SKIP_INSTALL=1 ;;
    --with-bar) WITH_BAR=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) if [ -n "${REPO:-}" ] || [ ! -d "$arg" ]; then c_warn "unknown arg: $arg (continuing)"; fi ;;
  esac
done
# --repo DIR (two-token form)
if [ "${1:-}" = "--repo" ] && [ -n "${2:-}" ]; then REPO="$2"; fi

# --- 1. locate the repo ----------------------------------------------------
step "1/6  Locating the plan-audit-map repository"
is_repo() { [ -f "$1/package.json" ] && grep -q '"@geeknik/plan-audit-map"\|"name": "plan-audit-map"' "$1/package.json" 2>/dev/null; }

if [ -z "$REPO" ]; then
  for cand in "$HERE" "$HERE/.." "$HERE/plan-audit-map" "$HERE/../plan-audit-map"; do
    if is_repo "$cand"; then REPO="$(cd "$cand" && pwd)"; break; fi
  done
fi

if [ -z "$REPO" ]; then
  c_warn "No repo found next to this folder — cloning a fresh copy."
  command -v git >/dev/null 2>&1 || { c_err "git not found. Install git, or unpack a repo zip next to this folder and re-run."; exit 1; }
  REPO="$HERE/plan-audit-map"
  git clone --depth 1 "$CLONE_URL" "$REPO"
fi
REPO="$(cd "$REPO" && pwd)"
c_ok "Repo: $REPO"

# --- 2. overlay the enhanced server ---------------------------------------
step "2/6  Overlaying enhanced server sources"
[ -f "$SERVER_SRC/index.ts" ]  && cp "$SERVER_SRC/index.ts"  "$REPO/index.ts"
[ -f "$SERVER_SRC/server.ts" ] && cp "$SERVER_SRC/server.ts" "$REPO/src/server.ts"
mkdir -p "$REPO/src/utils"
[ -f "$SERVER_SRC/config.ts" ] && cp "$SERVER_SRC/config.ts" "$REPO/src/utils/config.ts"
[ -f "$SERVER_SRC/package.json" ] && cp "$SERVER_SRC/package.json" "$REPO/package.json"
c_ok "server/server.ts -> src/server.ts, server/config.ts -> src/utils/config.ts (env-aware DB path, EOF fix, sqlite pinned to ^12.5.0 for Node 20)"

# The repo tsconfig includes ./**/*.ts — which would also compile the .ts
# overlay copies inside THIS folder (they only work from their real location
# in the repo).  Exclude ourselves from the build, idempotently.
DESKNAME="$(basename "$HERE")"
node -e '
const fs = require("fs");
const p = process.argv[1], self = process.argv[2];
let j;
try { j = JSON.parse(fs.readFileSync(p, "utf8")); }
catch (e) { console.error("tsconfig.json not plain JSON — leaving untouched"); process.exit(0); }
j.exclude = Array.from(new Set([...(j.exclude || []), "node_modules", "dist", self]));
fs.writeFileSync(p, JSON.stringify(j, null, 2) + "\n");
console.log("tsconfig excludes:", j.exclude.join(", "));
' "$REPO/tsconfig.json" "$DESKNAME" || true

# --- 3. toolchain checks ---------------------------------------------------
step "3/6  Checking the toolchain"
command -v node >/dev/null 2>&1 || { c_err "node not found (need >= 20). https://nodejs.org"; exit 1; }
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$NODE_MAJOR" -lt 20 ]; then c_err "Node >= 20 required (found $(node --version))."; exit 1; fi
if [ "$NODE_MAJOR" -lt 22 ]; then c_warn "Node $(node --version): OK for the pinned better-sqlite3 ^12.5.0."; else c_ok "Node $(node --version)"; fi
NODE_BIN="$(command -v node)"
PY_BIN="${PYTHON:-}"
if [ -z "$PY_BIN" ]; then for p in python3 python; do command -v "$p" >/dev/null 2>&1 && PY_BIN="$(command -v "$p")" && break; done; fi
[ -z "$PY_BIN" ] && c_warn "python3 not found — the desk bar / SQL viewer need it: apt install python3 python3-tk (or dnf install python3-tkinter)"
c_ok "node: $NODE_BIN"

# --- 4. npm install + build ------------------------------------------------
step "4/6  Installing dependencies and building"
cd "$REPO"
if [ "$SKIP_INSTALL" -eq 1 ]; then
  c_warn "skipping npm install (--no-install)"
else
  # npm's "prepare" hook runs `tsc && chmod ...`; fine on Linux, but tsc is
  # run explicitly again below so a failed chmod can never fail the install.
  npm install --no-audit --no-fund || { c_err "npm install failed. On Debian/Ubuntu native builds need: sudo apt install -y build-essential python3"; exit 1; }
fi
npx tsc || { c_err "build failed (tsc)."; exit 1; }
[ -f dist/index.js ] || { c_err "dist/index.js missing after build."; exit 1; }
node dist/index.js --help >/dev/null 2>&1 && c_ok "dist/index.js built and responds to --help" || { c_err "built server failed --help smoke test"; exit 1; }
DIST_INDEX="$REPO/dist/index.js"

# --- 5. desk-bar config + resolved connection JSONs ------------------------
step "5/6  Writing config and resolving connection JSONs"
CONF_DIR="${PLAN_AUDIT_MAP_HOME:-$HOME/.plan-audit-map}"
mkdir -p "$CONF_DIR"
BAR_CFG="$CONF_DIR/desk-bar.json"
PY_RESOLVE="${PYTHON:-python3}"
if [ -n "$PY_BIN" ]; then PY_RESOLVE="$PY_BIN"; fi
"$PY_RESOLVE" "$HERE/tools/install_helpers.py" "$DESK" "$DIST_INDEX" "$PY_BIN" "$BAR_CFG" "$NODE_BIN" "$CONNECT" \
  || c_warn "config/JSON resolution failed (python3 missing?)"

# --- 6. optional bar start + summary ---------------------------------------
step "6/6  Done"
if [ "$WITH_BAR" -eq 1 ] && [ -n "$PY_BIN" ]; then
  "$PY_BIN" "$DESK/planauditmap_launcher.py" --start-bar && c_ok "desk bar started" || c_warn "desk bar did not start (no display? Windows-only feature)"
else
  c_info "Desk bar: on Windows the launcher starts it automatically with the server."
fi

cat <<SUMMARY

$(c_ok "INSTALL COMPLETE")

  server        $DIST_INDEX
  desk stack    $DESK   (bar, launcher/wire-tap, SQL viewer)
  config        $BAR_CFG
  connections   $CONNECT/*.local.json  <- paste-ready MCP client JSON

  Try it now:
    python3 "$DESK/planauditmap_viewer.py"            # SQL viewer
    node "$DIST_INDEX" --sse --port 8002             # SSE server -> http://127.0.0.1:8002/sse
    python3 "$DESK/planauditmap_launcher.py" --print-mcp-config

SUMMARY
