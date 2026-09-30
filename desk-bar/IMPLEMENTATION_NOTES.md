# Implementation Notes

## Cross-platform behavior choice

The desk bar is implemented as a real Qt top-level window, not an override-redirect popup.

That matters because:

- Windows taskbar presence is reliable for top-level app windows.
- Linux dock/taskbar presence is more reliable for top-level app windows than for utility or tool windows.
- The app can still look like a popup sidebar by using a narrow fixed-width layout and bottom-right positioning.

## First-launch popup model

The desk bar polls the shared SQLite database for new launch rows.

- If `latest_launch_id > last_seen_launch_id`, it refreshes the UI.
- If `show_on_new_launch` is true, it re-opens itself.
- The window remains a normal taskbar/dock item, so minimizing does not remove it from the taskbar.

## Any venv / any AI model

The shared contract is the tracker layer, not the agent runtime.

Any agent or launcher that can run one of these commands can participate:

```bash
python -m planauditmap_desk track launch --agent codex
python -m planauditmap_desk track run-agent --agent codex -- codex
python -m planauditmap_desk track heartbeat --instance-key ...
python -m planauditmap_desk track finish --instance-key ... --exit-code 0
```

This makes the desk bar independent of:

- the active virtual environment
- the shell used to launch the agent
- the MCP server process
- which local AI CLI is used

## SQLite notes

The implementation enables:

- `PRAGMA journal_mode=WAL`
- `PRAGMA synchronous=NORMAL`
- `PRAGMA busy_timeout=5000`

This is the practical desktop setup for multiple local readers plus short writes from wrappers.

## Linux notes

Ubuntu support assumes a normal graphical desktop session.

- The taskbar/dock restore path is the main path.
- The tray icon is optional and only used if the desktop environment exposes a supported tray implementation.
- XDG autostart is installed via `~/.config/autostart/planauditmap-desk.desktop`.

## Windows notes

- The desk bar can be launched with `pythonw.exe` through the generated launcher.
- Login autostart is installed under the current user's Run key.
- The window remains a taskbar window when minimized.

## Suggested next integration step

If you already have MapThinkDo launchers or MCP bootstrap scripts, the cleanest upgrade is:

1. start the desk bar once per login
2. wrap each AI CLI with `track run-agent`
3. optionally write richer metadata into `metadata_json`
4. if desired, replace the sample SQLite file with your shared production DB path in `desk-bar.json`
