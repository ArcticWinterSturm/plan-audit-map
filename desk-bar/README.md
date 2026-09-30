# MapThinkDo Desk Bar

A cross-platform Windows and Ubuntu desk bar for MapThinkDo-style agent activity.

## Why this design

This implementation follows the storage direction used by GeekNik's `plan-audit-map` project:

- default base directory: `~/.plan-audit-map`
- legacy fallback: `~/.code-reasoning`
- local SQLite persistence for cross-session state

Instead of using a tool window that disappears from the taskbar, this app uses a real top-level window so it stays in the Windows taskbar and Linux dock/task list. The visual layout is still a narrow popup/sidebar.

## What it does

- Opens as a taskbar-visible desk bar window.
- Pops open on first run and on new unseen launch events.
- Tracks agent launches across different virtual environments.
- Shows live instances and historical launch counts from one SQLite database.
- Double-click the header to minimize to the taskbar.
- Optional system tray icon when the desktop environment supports it.
- Optional login autostart for Windows and Linux.

## Project layout

- `planauditmap_desk/app.py` - Qt desk bar UI
- `planauditmap_desk/storage.py` - SQLite schema and queries
- `planauditmap_desk/tracker.py` - launch tracking and agent wrapper runner
- `planauditmap_desk/autostart.py` - Windows and Linux autostart installers
- `desk-bar.json` - sample config
- `HERMES_INTEGRATION_PROMPT.md` - integration and test prompt for Hermes Agent

## Install

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Create config

```bash
python -m planauditmap_desk config
python -m planauditmap_desk config --print
```

This creates `desk-bar.json` under `~/.plan-audit-map/desk-bar.json` unless the legacy `~/.code-reasoning` directory already exists and `~/.plan-audit-map` does not.

## Run the desk bar

```bash
python -m planauditmap_desk desk
```

Or with an explicit config:

```bash
python -m planauditmap_desk desk --config ./desk-bar.json
```

## Track an agent launch

One-shot launch event:

```bash
python -m planauditmap_desk track launch --agent codex
```

Wrapped live process with heartbeat tracking:

```bash
python -m planauditmap_desk track run-agent --agent codex -- codex
python -m planauditmap_desk track run-agent --agent claude-code -- claude
python -m planauditmap_desk track run-agent --agent hermes -- hermes
python -m planauditmap_desk track run-agent --agent opencode -- opencode
```

## Suggested integration pattern

Make each agent command go through the wrapper so the desk bar gets real live state:

### Bash aliases

```bash
alias codex='python -m planauditmap_desk track run-agent --agent codex -- codex'
alias claude='python -m planauditmap_desk track run-agent --agent claude-code -- claude'
alias hermes='python -m planauditmap_desk track run-agent --agent hermes -- hermes'
alias opencode='python -m planauditmap_desk track run-agent --agent opencode -- opencode'
```

### PowerShell functions

```powershell
function codex { python -m planauditmap_desk track run-agent --agent codex -- codex @Args }
function claude { python -m planauditmap_desk track run-agent --agent claude-code -- claude @Args }
function hermes { python -m planauditmap_desk track run-agent --agent hermes -- hermes @Args }
function opencode { python -m planauditmap_desk track run-agent --agent opencode -- opencode @Args }
```

## Autostart

Install login autostart:

```bash
python -m planauditmap_desk autostart install
python -m planauditmap_desk autostart status
```

Remove it:

```bash
python -m planauditmap_desk autostart remove
```

## UI behavior

- The window opens in the bottom-right usable screen area.
- It remains a normal taskbar/dock window.
- Double-click the header to minimize it.
- Close exits the program.
- When a new agent launch is written to SQLite, the bar refreshes and pops back open.

## Test

```bash
python -m unittest discover -s tests -v
python -m py_compile planauditmap_desk/*.py
```

## Notes for integrating into an existing MapThinkDo repo

1. Keep the desk bar as a separate Python module or utility package.
2. Do not make the MCP server depend on the GUI.
3. Call the tracker wrapper from agent launch scripts, launchers, or shell aliases.
4. If you already have a shared SQLite DB, adapt `DeskDatabase` to write into the existing schema or add a small sync job.
5. Leave the bar as a top-level app window, not an override-redirect popup, if you need reliable taskbar presence on both Windows and Linux.
