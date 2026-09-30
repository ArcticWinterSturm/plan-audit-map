# Skill: Tkinter pitfalls in the desk stack — threads, focus, clipboard, .pyw

## Threads: widgets are main-thread-only, full stop

Tcl runs a single event loop. Calling ANY widget method (`configure`,
`insert`, `update`) from a worker thread works… until it doesn't:
`RuntimeError: main thread is not in main loop`, random deadlocks,
crashes inside Tcl. Locks do not fix this — the call itself is illegal
from another thread. The correct pattern (used by the bar for IPC and
by the intervention worker):

- worker threads put dicts on a `queue.Queue`
- the Tk thread drains it on a timer: `self.after(120, self._drain)`
- only the Tk thread touches widgets

The inverse rule also applies: never block the Tk thread on I/O (an
HTTP embed call, a DB lock) — the window freezes and Windows flags it
"Not responding". That is why the paste bar's Analyze button disables
and the analysis runs in a daemon thread.

## after() callbacks vs destruction

Every `after` callback can fire after the widget is destroyed →
`tk.TclError: invalid command name` or worse. Wrap the body in
`try/except tk.TclError`, or guard with a `self._closing` flag that
every loop checks first. Timers re-arm themselves
(`self.after(20000, self._loop)`) — the re-arm must also be skipped
when closing, or the process never exits.

## overrideredirect popups: focus and close-on-outside-click

Borderless (`overrideredirect(True)`) windows: the OS will not give
them focus on show — call `focus_force()`. `FocusOut` fires mid-click,
so defer the check ~180 ms. And `focus_displayof()` is NOT a "did we
lose focus" test — it stays populated after another application takes
focus, so a popup using it never closes on outside clicks. The working
check: `focus_get()`; if it returns None, or the focused widget is not
this popup nor any of its `.master` ancestors, hide. Topmost
(`attributes("-topmost", True)`) keeps the popup above other windows
without focus games.

## The clipboard outlives the app only sometimes

`clipboard_clear()` + `clipboard_append(text)` hands the clipboard to
the Tk process. On WINDOWS the content survives the app exiting (the
OS renders it for later pastes). On X11/Linux the clipboard is
ownership-based: when the app exits, the content is GONE unless a
clipboard manager (GNOME/KDE usually ship one) took it. So
"intervention copied to clipboard → user quits the bar → paste is
empty" is expected X11 behaviour, not a copy bug — paste before
quitting, keep the bar running, or pipe through `xclip`/`xsel` if it
must outlive the process.

## .pyw, pythonw.exe and the missing stdio

`.pyw` files and `pythonw.exe` mean: no console, and `sys.stdin` /
`sys.stdout` may literally be `None`. Any `sys.stdin.buffer` access
must guard: `getattr(sys.stdin, "buffer", None)`. Symptom of the
unguarded version: `AttributeError: 'NoneType' object has no attribute
'buffer'` the moment the no-console script touches stdio. Conversely a
proxy that NEEDS real stdio (the launcher) must be run with
`python.exe` — its docs say so for exactly this reason. On Windows
prefer the `py -3` launcher when present (`where py`); `start_desk_bar.bat`
resolves this. Spawning GUI children without console flash:
`creationflags=0x08000000` (CREATE_NO_WINDOW) or STARTUPINFO with
SW_HIDE — Windows-only kwargs; passing them on Linux raises
`ValueError: subprocess in this platform...` — build kwargs
conditionally.

## Headless CI: Xvfb and importing .pyw

Tkinter needs an X server on Linux. CI recipe:
`Xvfb :99 -screen 0 1600x900x24 & ` then `DISPLAY=:99 python3 app.py`;
a `timeout 5` run that exits 124 (killed while alive) proves the GUI
came up and stayed up. To import a `.pyw` module in tests (the
extension is not in `importlib`'s default loader set):
```python
from importlib.machinery import SourceFileLoader
import importlib.util
loader = SourceFileLoader("name", "path.pyw")
spec = importlib.util.spec_from_loader("name", loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)
```

## Listbox filtering: the visible-index mapping pattern

Filtering a `Listbox` by deleting rows breaks every index that comes
out of it (`curselection()` returns the ROW, your data lives in the
original list). Maintain `self._visible: list[int]` mapping row → data
index: rebuild it on every redraw, translate `curselection()` through
it in every handler, and when selecting a data index externally, reset
the filter if it hides the target. Symptom of the bug: click a filtered
row, the detail pane shows a DIFFERENT item. The same discipline
applies to Treeviews with reordered/filtered children.

## Text widget as a log renderer

Rendered read-only logs: keep the widget `state="disabled"`, flip to
"normal" only around edits, then back. Use `tag_configure` per severity
color and insert with `("tag",)` tuples. After an update, `yview_moveto
(0.0)` (top) for transcripts or `see("end-1c")` to follow the tail.
For long transcripts, cap history (delete "1.0", "end-5000l") — Text
widgets are not append-only logs and will eat RAM otherwise.

## Fonts and DPI

`("Segoe UI", 10)` on Windows, `("Helvetica", 11)` elsewhere is a sane
default pair; monospace `Consolas`/`Menlo` for transcripts. Without
per-monitor DPI awareness (set BEFORE window creation), Windows scales
your window with blur and mouse coordinates lie in scaled space — see
the appbar skill. `option_add("*Font", …)` sets a global default but
per-widget explicit fonts win; audit both when text looks inconsistent.
