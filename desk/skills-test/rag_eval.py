#!/usr/bin/env python3
"""rag_eval.py — ground-truth retrieval evaluation for the test corpus.

Fires synthetic "circling agent" traces at the REAL intervention engine
(desk/mtd_intervention.py) over skills-test/corpus and checks that the
expected skill file is retrieved in the top-k. Uses the deterministic
offline embedder so the run is reproducible and CI-safe (no server needed).

Pass criteria:
  * top-1 hit rate >= 70%
  * top-3 hit rate >= 90%
  * corpus size within 100-120 KB (excluding this harness and README)
  * every corpus file has a "# " title and at least 3 "## " sections
  * no chunk exceeds the chunker window (1400) by more than the overlap
    slack (windowing is expected only for oversized sections)

Usage:  python3 rag_eval.py [-v]
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DESK = HERE.parent / "desk"
CORPUS = HERE / "corpus"

sys.path.insert(0, str(DESK))

# Each case: (label, primary expected file, acceptable alternates, trace)
CASES = [
    ("tap-missing-table", "wire-tap-internals.skill.md", ["memory-db-schema.skill.md"],
     "The SQL viewer shows (no raw_mcp_events table found) for every session. "
     "I connected Claude Desktop straight to node dist/index.js and the tool "
     "calls work, thoughts appear, sessions appear, but the Raw Events tab is "
     "empty and there is no conversation. Let me re-check the server source "
     "for where it creates raw_mcp_events... I can't find the CREATE TABLE "
     "anywhere. Let me try again, maybe the table is created lazily. "
     "Hmm, still nothing. Let me re-read the viewer code again."),

    ("silent-segfault", "node-sqlite3-abi-matrix.skill.md", ["server-overlay-build.skill.md"],
     "The plan-audit-map server exits instantly when any MCP client calls it. "
     "No output at all, no stack trace, the launcher reports server exited "
     "with -11 and the direct run gives exit code 139 segmentation fault. "
     "I added console.log everywhere, nothing prints. Let me try rebuilding "
     "node_modules. Same segfault. Let me check the node version, it's v20. "
     "Maybe npm cache clean helps. Let me try again with a clean install. "
     "Still segfaults silently with exit -11."),

    ("node26-compile", "node-sqlite3-abi-matrix.skill.md", ["npm-native-modules-troubleshooting.skill.md"],
     "npm install fails on my new machine with Node 26. The error says "
     "EBADENGINE Unsupported engine better-sqlite3 required node >=22 wait "
     "no, it says something about PropertyCallbackInfo This has been removed "
     "or info.This() compile errors from node-gyp building better_sqlite3. "
     "Let me reinstall. Same compile error. Let me try removing package-lock "
     "and reinstalling. Still fails to compile the native module."),

    ("viewer-empty-db-crash", "memory-db-schema.skill.md", ["wire-tap-internals.skill.md"],
     "The viewer crashes on startup with sqlite3.OperationalError no such "
     "table: sessions when I point it at a fresh memory.db that only has "
     "raw_mcp_events rows. The database was created by the launcher wire "
     "tap before the node server ever wrote a session. Let me check if the "
     "schema init failed... the thoughts table is also missing. Let me "
     "delete the db and try again. Same crash."),

    ("qwen-runner-rewrite", "qwen-desktop-mcp-nonstandard.skill.md", [],
     "I added plan-audit-map to the Qwen desktop app using command npx and "
     "args -y but the tools never show up, zero tools listed. Works fine in "
     "Claude Desktop with the same npx entry. Let me try bun x instead. "
     "Still zero tools in Qwen. Maybe the chat.qwen.ai API needs the server "
     "registered? Let me POST to /api/v2/mcp/config — it returns 404. "
     "Let me try /api/v2/mcp/servers — also 404. One more attempt with a "
     "different npx version."),

    ("qwen-studio-bridge", "qwen-desktop-mcp-nonstandard.skill.md", [],
     "Setting up MCP servers in qwen-studio on Linux. Where does it even "
     "store the config? I tried ~/.qwen/settings.json but the Tauri app "
     "doesn't read that. The settings UI mentions mcp-bridge.mjs and I see "
     "node mcp-bridge.mjs in the process list with TAURI_ENV_PLATFORM env "
     "vars. Let me check how it spawns servers, maybe stdin isn't working "
     "through the bridge. Let me restart the app. Same result."),

    ("camelcase-args", "plan-audit-map-tool-schema.skill.md", [],
     "Every tools/call to plan-audit-map returns isError with Validation "
     "errors found: Unrecognized key(s) in object: thoughtNumber. I am "
     "sending thoughtNumber, totalThoughts, nextThoughtNeeded like every "
     "other MCP tool. Let me try renaming to thought_number only. It wants "
     "all of them snake_case? Let me try camelCase again to be sure. Same "
     "validation error. Let me check the zod schema in the source."),

    ("flailing-generic", "circular-cot-signatures.skill.md", ["plan-audit-map-tool-schema.skill.md"],
     "I used the plan-audit-map tool for the first few thoughts of this task "
     "but then stopped. Now I keep going in circles, let me try again, "
     "hmm that didn't work, one more attempt, wait actually let me check "
     "something else, I already tried this fix twice, let me re-read my "
     "earlier reasoning to see if I verified it... I think I did? Let me "
     "just try the same approach again from the top."),

    ("bar-overlaps-taskbar", "desk-bar-appbar-windows.skill.md", [],
     "The desk bar renders on top of the Windows taskbar and covers the "
     "Start button instead of sitting above it. My taskbar is docked at "
     "the top of the screen, not the bottom. Let me change dock_edge to "
     "top in desk-bar.json. Now the bar overlaps the taskbar at the top "
     "instead. Let me try sit_above_taskbar false. Now Windows moves my "
     "whole desktop layout around when the bar registers. Let me try "
     "another combination."),

    ("second-bar-instance", "desk-bar-appbar-windows.skill.md", ["desk-stack-files-map.skill.md"],
     "I clicked the launcher again and now I think there are two desk bars "
     "running, or maybe the first one is a zombie — nothing responds to "
     "clicks. The bar binds 127.0.0.1:38457 and the second instance should "
     "exit when the port is taken. Let me kill everything and restart. "
     "The port still seems busy. Let me check with netstat."),

    ("proxy-hang", "wire-tap-internals.skill.md", [],
     "The MCP client hangs forever at startup when connected through "
     "planauditmap_launcher.py, but connects instantly to the server "
     "directly. The launcher forwards stdin to the server. I pasted one "
     "initialize message, nothing comes back. Let me add logging to the "
     "proxy. The bytes reach the launcher but seem to never reach the "
     "server until I paste 8KB more. Let me try a bigger message. Still "
     "hangs with small messages."),

    ("zombie-server", "server-overlay-build.skill.md", ["wire-tap-internals.skill.md"],
     "After my MCP client disconnects, node.exe processes keep running, "
     "one per client session. Task manager shows dozens of orphaned node "
     "processes all running dist/index.js. The server never notices the "
     "client closed stdin. Let me add a SIGTERM handler. That only works "
     "for signals, the process just idles. Let me try killing them "
     "manually. They come back with every new session."),

    ("db-locked", "sqlite-multi-process-wal.skill.md", ["wire-tap-internals.skill.md"],
     "sqlite3.OperationalError database is locked appears in the launcher "
     "stderr while the node server is writing a thought at the same time. "
     "The wire tap inserts into raw_mcp_events and the server inserts "
     "into thoughts concurrently. Let me add a retry loop. Still locked "
     "sometimes. Let me close the connection between every insert. "
     "Slower but still occasional 'database is locked' errors."),

    ("tkinter-thread-crash", "tkinter-pitfalls.skill.md", [],
     "RuntimeError main thread is not in main loop sometimes when the "
     "desk bar updates the ticker from the IPC socket thread. I call "
     "self.ticker.configure from the thread that received the message. "
     "It works for a while then crashes in Tcl. Let me add a lock around "
     "the configure call. Still crashes. Let me try calling update() "
     "from the thread. Worse."),

    ("pyw-stdin-none", "tkinter-pitfalls.skill.md", ["wire-tap-internals.skill.md"],
     "AttributeError NoneType has no attribute buffer or the launcher "
     "crashes with an AttributeError on sys.stdin.buffer when started "
     "with pythonw.exe. The .pyw extension means no console so stdin is "
     "None. Let me guard with getattr. Now stdout is also None in places. "
     "Let me try running the .pyw with python.exe instead — a console "
     "window flashes."),

    ("npm-prepare-chmod", "npm-native-modules-troubleshooting.skill.md", ["server-overlay-build.skill.md"],
     "npm install fails on Windows during the prepare step: 'chmod' is "
     "not recognized as an internal or external command. The package.json "
     "build script runs tsc && chmod +x dist/*.js which is a Unix command. "
     "Let me install Git Bash so chmod exists on PATH. npm still can't "
     "find it in the script context. Let me try running tsc manually — "
     "that works, but npm install keeps failing at prepare."),

    ("intervention-estimate", "intervention-paste-bar.skill.md", [],
     "Where does the ~14% improvement estimate in the intervention block "
     "come from? I need to explain the number to my team. Is it from a "
     "benchmark? Let me look at the code, there is repetition, "
     "calibration gap, recall, transfer 0.6, clamp 5 to 45. Which of "
     "these are measured vs invented? Let me re-read the message. The "
     "work string shows arithmetic but I need the formula."),

    ("ollama-not-detected", "intervention-paste-bar.skill.md", [],
     "The paste bar says 'offline fallback (no server found)' even though "
     "Ollama is running with nomic-embed-text pulled. ollama list shows "
     "the model. The bar auto-detects 127.0.0.1:11434. Let me set "
     "embedding_endpoint explicitly. Still falls back to offline. Let me "
     "check if the model name must be nomic-embed-text exactly. Maybe "
     "the port is different."),

    ("relocate-paths", "desk-stack-files-map.skill.md", ["plan-audit-map-desk-install.skill.md"],
     "I moved the whole workspace folder to a new drive and now the desk "
     "bar opens nothing when I click SQL Viewer and the server_command "
     "in desk-bar.json points at the old path. The connect/*.local.json "
     "files also have stale absolute paths baked in. Let me edit "
     "desk-bar.json viewer_script. The MCP client config still points at "
     "the old location too. Let me find every file that embeds absolute "
     "paths."),

    ("handshake-hang", "mcp-stdio-protocol.skill.md", ["wire-tap-internals.skill.md"],
     "My custom MCP client sends an initialize request and gets the "
     "response, then sends tools/list and nothing comes back. Do I need "
     "to send a notification after initialize? The spec says something "
     "about notifications/initialized. Let me try sending initialized "
     "before tools/list. That works. Now my client hangs on close — do I "
     "need to send a shutdown request like LSP? Let me try JSON-RPC "
     "shutdown with an id."),

    ("clipboard-empty", "tkinter-pitfalls.skill.md", [],
     "The intervention block was copied to the clipboard but when I quit "
     "the desk bar and paste, the clipboard is empty. On Windows it "
     "works, on Linux the paste after quitting gives nothing. Let me "
     "re-run and paste immediately. Works while the bar is running, "
     "empty after the bar exits."),
]

STRUCT_MIN_BYTES = 100_000
STRUCT_MAX_BYTES = 120_000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    import mtd_intervention as mi

    with tempfile.TemporaryDirectory() as td:
        os.environ["PLAN_AUDIT_MAP_HOME"] = td
        ivp = mi.intervention_config({"skills_dir": str(CORPUS),
                                      "embedding_provider": "local"})
        sdir = mi.skills_dir_for(ivp)
        if sdir is None or not CORPUS.is_dir():
            print(f"FAIL: corpus directory missing: {CORPUS}")
            return 2
        index = mi.SkillsIndex(sdir, mi.HashedEmbedder(),
                               int(ivp["max_chunk_chars"]))
        n_chunks = index.build()

        top1 = top3 = 0
        failures = []
        for label, primary, alts, trace in CASES:
            qv = index.embedder.embed_batch([trace])[0]
            hits = index.search(qv, mi.tokenize(trace), top_k=3,
                                min_score=float(ivp["min_score"]))
            files = [h.get("file") for _, h in hits]
            ok1 = bool(files) and files[0] in ([primary] + alts)
            ok3 = primary in files or any(a in files for a in alts)
            top1 += ok1
            top3 += ok3
            if not ok3:
                failures.append((label, primary, files))
            if args.verbose:
                print(f"  {label:24s} top1={ok1} top3={ok3} -> {files}")

        rate1 = 100.0 * top1 / len(CASES)
        rate3 = 100.0 * top3 / len(CASES)

        # ---- structural checks ----------------------------------------------
        files = sorted(p for p in CORPUS.glob("*.md")
                       if not p.name.upper().startswith("README"))
        total = sum(p.stat().st_size for p in files)
        bad_titles = [p.name for p in files
                      if not p.read_text(encoding="utf-8").lstrip().startswith("# ")]
        bad_sections = []
        oversized = 0
        for p in files:
            text = p.read_text(encoding="utf-8")
            if text.count("\n## ") + text.startswith("## ") < 3:
                bad_sections.append(p.name)
            for ch in mi.chunk_markdown(text, int(ivp["max_chunk_chars"])):
                if len(ch["text"]) > int(ivp["max_chunk_chars"]) + 260:
                    oversized += 1

        print()
        print("=" * 64)
        print(f"cases: {len(CASES)}   top-1: {top1}/{len(CASES)} ({rate1:.0f}%)"
              f"   top-3: {top3}/{len(CASES)} ({rate3:.0f}%)")
        print(f"corpus: {len(files)} files, {total/1024:.1f} KB, "
              f"{n_chunks} chunks (target {STRUCT_MIN_BYTES//1024}-"
              f"{STRUCT_MAX_BYTES//1024} KB)")
        if failures:
            print("misses:")
            for label, primary, files in failures:
                print(f"  - {label}: wanted {primary}, got {files}")
        ok = True
        if rate1 < 70: ok = False; print("FAIL: top-1 below 70%")
        if rate3 < 90: ok = False; print("FAIL: top-3 below 90%")
        if not (STRUCT_MIN_BYTES <= total <= STRUCT_MAX_BYTES):
            ok = False
            print(f"FAIL: corpus size {total} outside 100-120 KB")
        if bad_titles: ok = False; print("FAIL: missing '# ' title:", bad_titles)
        if bad_sections: ok = False; print("FAIL: <3 '## ' sections:", bad_sections)
        if oversized: ok = False; print(f"FAIL: {oversized} chunks exceed window")
        print("RESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
