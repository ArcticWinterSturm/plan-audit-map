# Hermes Agent Integration Prompt

Use this prompt when asking Hermes Agent to integrate the desk bar into an existing MapThinkDo or MCP workspace.

---

You are integrating a cross-platform desk bar for MapThinkDo.

## Goal

Integrate a Python desk bar that:

1. Runs on Windows and Ubuntu from one codebase.
2. Stays available as a normal taskbar/dock window.
3. Pops open the first time any supported AI launches.
4. Tracks Codex, Claude Code, Hermes, OpenCode, and ChatGPT-style local launchers from any virtual environment.
5. Uses SQLite as the single local source of truth for launch history and live instance state.
6. Double-clicking the desk bar header minimizes it to the taskbar.
7. Closing the desk bar exits it.
8. New launch events re-open the desk bar if it is minimized.

## Hard constraints

- Do not rebuild LVS Tasker.
- Use the popup/sidebar patterns only as a UI reference.
- Keep the desk bar independent from the MCP server process.
- Keep the UI code separate from the tracking and SQLite code.
- Use the same user config base directory logic as MapThinkDo: prefer `~/.plan-audit-map`, fall back to `~/.code-reasoning` only if needed.
- Do not use hidden tool-window behavior that removes the window from the taskbar.
- Ensure one code path works for Windows and Ubuntu.
- Prefer a real top-level Qt window with a sidebar layout and bottom-right popup positioning.

## Required implementation steps

1. Inspect the existing repo and identify where launchers, shell wrappers, or startup hooks live.
2. Add or merge the following components:
   - desk-bar config file
   - SQLite launch tracking layer
   - wrapped agent runner with heartbeat and finish events
   - Qt desk bar window
   - autostart installer for Windows and Linux
3. Make the window show in the taskbar/dock.
4. Make the first unseen launch event auto-open the desk bar.
5. Make double-click on the desk bar header minimize it.
6. Make the bar restore when the user clicks the taskbar item or tray icon.
7. Preserve config and last seen state in SQLite or config.
8. Keep code comments brief and useful.

## Testing requirements

Perform thorough testing and report only concise results, not raw hidden reasoning.

### Test matrix

- Windows launch flow
- Ubuntu launch flow
- first run config creation
- autostart install/uninstall
- single-instance protection
- launch event insert
- heartbeat updates
- finish updates
- active instance timeout behavior
- popup re-open on new launch
- double-click minimize behavior
- close exits process
- agent alias normalization for Codex, Claude Code, Hermes, OpenCode, ChatGPT

### Verification style

Use internal step-by-step reasoning privately.
Do not print chain-of-thought.
Instead, output:

- plan
- files changed
- commands run
- test results
- remaining risks
- next suggested improvements

## Required deliverables

- final code
- sample `desk-bar.json`
- short run instructions
- exact commands for tracking Codex, Claude Code, Hermes, and OpenCode launches
- explicit note about why a normal top-level window is used instead of a hidden override-redirect popup

Now inspect the repo, integrate the feature fully, run the tests you can run locally, and summarize the result cleanly.
