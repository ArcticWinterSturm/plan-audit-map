# Skill: the desk bar on Windows — appbar docking, strip mode, IPC

## Two docking modes

`sit_above_taskbar` in desk-bar.json picks the mode:
- **true (default) — strip mode**: no Win32 registration. The bar is a
  topmost borderless window pinned directly above (or below) the
  taskbar rect, found via `SHAppBarMessage(ABM_GETTASKBARPOS)`. The real
  taskbar stays fully visible; Windows does not reserve screen space.
- **false — appbar mode**: registers a real application desktop toolbar
  (`ABM_NEW` with a callback message, then `ABM_QUERYPOS`/`ABM_SETPOS`
  to negotiate the rectangle). Windows reserves the space and shifts the
  taskbar/work area. This is a genuine taskbar band — and it will move
  your maximized windows and desktop layout to make room, which some
  setups hate.

DPI awareness must be set BEFORE any window exists:
`SetProcessDpiAwareness(2)` (per-monitor) with fallback
`SetProcessDPIAware()`, or every coordinate is in scaled lies.

## Edge handling and the top-taskbar case

`dock_edge` is bottom or top. With the taskbar at the BOTTOM (the
default assumption), strip mode sits the bar just above `taskbar.top`.
With the taskbar at the TOP, the bar must sit just BELOW
`taskbar.bottom` — pinning above `taskbar.top - height` would put it
OVER the taskbar and cover the window controls. Symptom "bar covers the
Start button" = strip geometry computed for the wrong edge or
`sit_above_taskbar` interacting badly with a non-bottom taskbar — set
`dock_edge` to match the physical taskbar and let the 20-second re-dock
loop settle it. The bar re-asserts its position every ~20 s and after
`<Configure>` events, which recovers from resolution changes, taskbar
moves, and auto-hide toggles without a restart.

## Single instance, IPC, and the zombie-port case

The bar binds `127.0.0.1:38457` (config `bar_port`). Second start:
bind fails → assume an instance is running → send `{"type":"wake"}` →
exit. The same socket carries: `ping`→`pong`, `show`, `intervene`
(opens the Intervene tab), `quit`, `server` up/down, and live `mcp`
tool-call events for the ticker. A bar that ignores clicks but holds the
port is a half-dead instance — kill it
(`planauditmap_launcher.py --stop-bar`, then process kill if needed) and
start fresh. The launcher starts the bar detached
(`DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP`, `STARTF_USESHOWWINDOW`,
stdio → DEVNULL) with `pythonw.exe`, so no console flashes and it
survives the client closing.

## Popup behaviour (overview + Intervene tabs)

Left-click the bar → overview popup (an `overrideredirect` topmost
Toplevel): tabs "Recent activity" and "🛟 Intervene"; the activity tab's
only button remains SQL Viewer, by design. Esc hides; clicking outside
hides — implemented via `focus_get()` and walking `.master` up from the
focused widget, because `focus_displayof()` stays populated after focus
moves to another app and never auto-hides the popup. `overrideredirect`
windows are not focusable by the OS on show — call `focus_force()`.
Right-click the bar: menu (overview, intervention bar, SQL viewer,
refresh, hide, quit).

## Ticker and LED semantics

The ticker prefers live IPC events for ~45 s after the last one, then
falls back to the newest DB activity so it never freezes on a stale
"last tool call". Live items expire by epoch time, not by count. LED:
green when a session exists in the DB (any real activity), dim when the
DB is empty, green while the server is up per the `server` IPC message.
Counts label shows `NS TT EE` (sessions / thoughts / raw events) —
zeros there while the client "works" means the pipeline is bypassed or
dead, check the wire-tap skill.

## Running without a console / on other platforms

The bar file is `.pyw` (no console). Under `pythonw`, `sys.stdin` /
`sys.stdout` can be `None` — anything touching `.buffer` must guard with
`getattr(sys.stdin, "buffer", None)`. On non-Windows the Win32 block is
skipped and the bar degrades to a plain bottom-docked strip (the
`ABE_*` constants are defined unconditionally; a NameError there was a
real bug). For CI: run the bar under `Xvfb` with `DISPLAY=:99`; a
`timeout 5` run that exits 124 means it stayed alive = healthy.

## Appbar registration, code-level

`APPBARDATA` struct (cbSize, hWnd, uCallbackMessage, uEdge, rc, lParam).
Flow: `ABM_NEW` (register with a WM_USER-range callback) → propose rect
(edge + height) → `ABM_QUERYPOS` (Windows adjusts) → re-tighten to your
height (QUERYPOS may round) → `ABM_SETPOS` (final) → `SetWindowPos` with
HWND_TOPMOST | SWP_NOACTIVATE | SWP_SHOWWINDOW. On exit you MUST send
`ABM_REMOVE` or Windows keeps the reserved space forever — the classic
"my screen is 30px shorter after a crash". The bar sends ABM_REMOVE in
quit and in the finally-path even on exceptions. Callback messages
(`ABN_POSCHANGED`) arrive on the registered message id; handling them by
re-running SETPOS is what keeps the band stable across taskbar changes.

## Multi-monitor and autohide

`MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)` + `GetMonitorInfoW`
gives the monitor rect (rcMonitor) and work area (rcWork) — the bar
docks to the monitor it is on, not the primary. Auto-hide taskbars:
appbar registration fights the slide-out animation; strip mode is the
supported configuration there (that is why `sit_above_taskbar` defaults
true). Resolution changes: the `<Configure>` handler plus the 20 s loop
re-derive geometry; a bar stranded off-screen resolves itself within
one cycle.

## Startup timing

The appbar needs a real HWND, so registration is deferred ~60 ms after
window creation (`self.after(60, self._dock)`). If you re-parent or
destroy the window before that fires, guard with a `_closing` check.
The IPC server binds BEFORE the Tk mainloop starts (so a second
instance exits fast), then `DeskBar(cfg)` is constructed, then
`ipc.on_message` is wired — a tiny window where messages queue harmlessly
because the drain loop pulls them after the loop starts.
