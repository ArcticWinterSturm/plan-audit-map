#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mapthinkdo_bar.pyw — MapThinkDo taskbar desk bar (Windows).

A slim bar docked at the Windows taskbar.  Click it and you get an overview of
recent MapThinkDo activity; that overview has exactly one button — "SQL
Viewer" — which opens the MapThinkDo viewer against your memory database.

How it docks
------------
Two modes, chosen by `sit_above_taskbar` in ~/.map-think-do/desk-bar.json:

  * "appbar" (default) — registers a real Win32 application desktop toolbar
    with SHAppBarMessage(ABM_NEW / ABM_QUERYPOS / ABM_SETPOS).  Windows
    reserves screen space for it and moves the taskbar out of the way, so it
    is a genuine taskbar band rather than a window floating over everything.
    Position is renegotiated on a timer and after any display change.

  * "strip" — no appbar registration; the window is simply pinned just above
    the taskbar rect and kept topmost.  Use this if your taskbar is set to
    auto-hide, or if you would rather the taskbar stay put.

Either way it degrades to a plain bottom-docked strip if the Win32 calls are
unavailable (e.g. running on Linux/macOS, or under a stripped-down shell).

Single instance
---------------
The bar binds 127.0.0.1:<bar_port>.  If the port is taken it assumes another
instance is already running, hands it a "wake" message and exits.  The same
socket is how mapthinkdo_launcher.py streams live MCP activity into the
ticker, so you see tool calls land in real time.

Run with pythonw.exe (no console window).  Stdlib only.
"""

from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mtd_shared  # noqa: E402

APP = "mapthinkdo-bar"
IS_WIN = sys.platform.startswith("win")

# ABE_* edge ids are needed by Dock on every platform (on non-Windows the
# dock degrades to a plain strip but still classifies the edge) — defining
# them unconditionally fixes a NameError that crashed _dock() on Linux.
ABE_LEFT, ABE_TOP, ABE_RIGHT, ABE_BOTTOM = 0, 1, 2, 3

THEME = {
    "bg": "#15161c",
    "bg_alt": "#1d1f29",
    "fg": "#e6e8f0",
    "dim": "#8b90a6",
    "accent": "#7aa2f7",
    "ok": "#4ade80",
    "warn": "#fbbf24",
    "err": "#f87171",
    "call": "#7aa2f7",
    "result": "#4ade80",
    "thought": "#c4b5fd",
    "session": "#fbbf24",
}

# ---------------------------------------------------------------------------
# Win32 application-desktop-toolbar support
# ---------------------------------------------------------------------------

if IS_WIN:  # pragma: no cover - platform specific
    try:  # DPI awareness must be set before any window is created.
        ctypes = __import__("ctypes")
        _shcore = ctypes.windll.shcore
        _shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:  # noqa: BLE001
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            ctypes = None
    else:
        ctypes = __import__("ctypes")

    import ctypes as _ctypes  # noqa: E402
    from ctypes import wintypes  # noqa: E402

    ABM_NEW = 0x00000000
    ABM_REMOVE = 0x00000001
    ABM_QUERYPOS = 0x00000002
    ABM_SETPOS = 0x00000003
    ABM_GETTASKBARPOS = 0x00000005
    ABM_ACTIVATE = 0x00000006
    ABM_WINDOWPOSCHANGED = 0x00000009


    WM_USER = 0x0400
    ABN_POSCHANGED = 0x00000001
    APPBAR_CALLBACK = WM_USER + 0x02A0

    MONITOR_DEFAULTTONEAREST = 0x00000002
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    SWP_NOZORDER = 0x0004

    class RECT(_ctypes.Structure):
        _fields_ = [("left", _ctypes.c_long), ("top", _ctypes.c_long),
                    ("right", _ctypes.c_long), ("bottom", _ctypes.c_long)]

    class APPBARDATA(_ctypes.Structure):
        # DWORD cbSize; HWND hWnd; UINT uCallbackMessage; UINT uEdge;
        # RECT rc; LPARAM lParam;
        _fields_ = [("cbSize", wintypes.DWORD),
                    ("hWnd", _ctypes.c_void_p),
                    ("uCallbackMessage", wintypes.UINT),
                    ("uEdge", wintypes.UINT),
                    ("rc", RECT),
                    ("lParam", _ctypes.c_ssize_t)]

    class MONITORINFO(_ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                    ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

    _shell32 = _ctypes.windll.shell32
    _user32 = _ctypes.windll.user32

    _SHAppBarMessage = _shell32.SHAppBarMessage
    _SHAppBarMessage.argtypes = [wintypes.DWORD, _ctypes.POINTER(APPBARDATA)]
    _SHAppBarMessage.restype = wintypes.UINT

    _SetWindowPos = _user32.SetWindowPos
    _SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, _ctypes.c_int,
                              _ctypes.c_int, _ctypes.c_int, _ctypes.c_int,
                              wintypes.UINT]
    _SetWindowPos.restype = wintypes.BOOL
else:  # pragma: no cover - non-Windows
    _ctypes = None
    APPBARDATA = None
    RECT = None


class Dock:
    """Thin wrapper over the Win32 appbar API with graceful fallback."""

    def __init__(self, hwnd: int, edge: str = "bottom",
                 sit_above_taskbar: bool = False) -> None:
        self.hwnd = hwnd
        self.edge = ABE_BOTTOM if edge == "bottom" else ABE_TOP
        self.sit_above_taskbar = sit_above_taskbar
        self.mode = "none"
        self.registered = False

    # -- geometry helpers --------------------------------------------------

    def monitor_rect(self):
        if not _ctypes:
            return (0, 0, 1920, 1080)
        try:
            hmon = _user32.MonitorFromWindow(int(self.hwnd),
                                             MONITOR_DEFAULTTONEAREST)
            info = MONITORINFO()
            info.cbSize = _ctypes.sizeof(MONITORINFO)
            if _user32.GetMonitorInfoW(_ctypes.c_void_p(hmon),
                                       _ctypes.byref(info)):
                rc = info.rcMonitor
                return (rc.left, rc.top, rc.right, rc.bottom)
        except Exception:  # noqa: BLE001
            pass
        try:
            return (0, 0, _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1))
        except Exception:  # noqa: BLE001
            return (0, 0, 1920, 1080)

    def taskbar_rect(self):
        if not _ctypes:
            return None
        try:
            abd = APPBARDATA()
            abd.cbSize = _ctypes.sizeof(APPBARDATA)
            abd.hWnd = 0
            if _SHAppBarMessage(ABM_GETTASKBARPOS, _ctypes.byref(abd)):
                return (abd.rc.left, abd.rc.top, abd.rc.right, abd.rc.bottom,
                        abd.uEdge)
        except Exception:  # noqa: BLE001
            pass
        return None

    # -- registration ------------------------------------------------------

    def register(self) -> bool:
        if not _ctypes or self.sit_above_taskbar:
            self.mode = "strip"
            return False
        try:
            abd = APPBARDATA()
            abd.cbSize = _ctypes.sizeof(APPBARDATA)
            abd.hWnd = _ctypes.c_void_p(int(self.hwnd))
            abd.uCallbackMessage = APPBAR_CALLBACK
            if _SHAppBarMessage(ABM_NEW, _ctypes.byref(abd)):
                self.registered = True
                self.mode = "appbar"
                return True
        except Exception as exc:  # noqa: BLE001
            print(f"[{APP}] appbar registration failed: {exc}", file=sys.stderr)
        self.mode = "strip"
        return False

    def unregister(self) -> None:
        if not _ctypes or not self.registered:
            return
        try:
            abd = APPBARDATA()
            abd.cbSize = _ctypes.sizeof(APPBARDATA)
            abd.hWnd = _ctypes.c_void_p(int(self.hwnd))
            _SHAppBarMessage(ABM_REMOVE, _ctypes.byref(abd))
        except Exception:  # noqa: BLE001
            pass
        self.registered = False

    # -- positioning -------------------------------------------------------

    def position(self, height: int) -> Optional[tuple]:
        """Return (x, y, w, h) for the bar, or None to fall back to Tk geometry."""
        if not _ctypes:
            return None

        left, top, right, bottom = self.monitor_rect()
        screen_w = right - left
        screen_h = bottom - top

        if self.mode == "appbar":
            try:
                abd = APPBARDATA()
                abd.cbSize = _ctypes.sizeof(APPBARDATA)
                abd.hWnd = _ctypes.c_void_p(int(self.hwnd))
                abd.uEdge = self.edge
                if self.edge == ABE_BOTTOM:
                    abd.rc = RECT(left, bottom - height, right, bottom)
                else:
                    abd.rc = RECT(left, top, right, top + height)
                _SHAppBarMessage(ABM_QUERYPOS, _ctypes.byref(abd))
                if self.edge == ABE_BOTTOM:
                    abd.rc.top = abd.rc.bottom - height
                else:
                    abd.rc.bottom = abd.rc.top + height
                _SHAppBarMessage(ABM_SETPOS, _ctypes.byref(abd))
                rc = abd.rc
                _SetWindowPos(_ctypes.c_void_p(int(self.hwnd)),
                              _ctypes.c_void_p(HWND_TOPMOST),
                              rc.left, rc.top,
                              rc.right - rc.left, rc.bottom - rc.top,
                              SWP_NOACTIVATE | SWP_SHOWWINDOW)
                return (rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top)
            except Exception as exc:  # noqa: BLE001
                print(f"[{APP}] appbar positioning failed: {exc}", file=sys.stderr)
                self.mode = "strip"

        # "strip": pin just above (or below) the taskbar, topmost.
        tb = self.taskbar_rect()
        if tb and tb[4] == ABE_BOTTOM:
            tb_left, tb_top, tb_right, tb_bottom, _edge = tb
            x, w = tb_left, tb_right - tb_left
            y = tb_top - height if self.edge == ABE_BOTTOM else 0
        elif tb and tb[4] == ABE_TOP:
            # Taskbar docked at the top: sit directly under it.
            tb_left, tb_top, tb_right, tb_bottom, _edge = tb
            x, w = tb_left, tb_right - tb_left
            y = tb_bottom if self.edge == ABE_BOTTOM else tb_top - height
        else:
            x, w = left, screen_w
            y = bottom - height if self.edge == ABE_BOTTOM else top
        try:
            _SetWindowPos(_ctypes.c_void_p(int(self.hwnd)),
                          _ctypes.c_void_p(HWND_TOPMOST),
                          int(x), int(y), int(w), int(height),
                          SWP_NOACTIVATE | SWP_SHOWWINDOW)
        except Exception:  # noqa: BLE001
            return None
        return (x, y, w, height)


# ---------------------------------------------------------------------------
# IPC server (single instance + live activity from the launcher)
# ---------------------------------------------------------------------------

class IpcServer(threading.Thread):
    """Tiny line-oriented JSON server on localhost."""

    def __init__(self, port: int, on_message, log=print) -> None:
        super().__init__(name="bar-ipc", daemon=True)
        self.port = port
        self.on_message = on_message
        self.log = log
        self.sock: Optional[socket.socket] = None
        self._stop = threading.Event()

    def bind(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("127.0.0.1", self.port))
            self.sock.listen(16)
            self.sock.settimeout(0.5)
            return True
        except OSError as exc:
            self.log(f"[{APP}] cannot bind port {self.port}: {exc}")
            return False

    def run(self) -> None:
        if self.sock is None:
            return
        while not self._stop.is_set():
            try:
                conn, _addr = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(5.0)
            buf = b""
            try:
                while not self._stop.is_set():
                    data = conn.recv(65536)
                    if not data:
                        break
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            continue
                        try:
                            reply = self.on_message(msg)
                        except Exception as exc:  # noqa: BLE001
                            reply = {"ok": False, "error": str(exc)}
                        if reply is not None:
                            conn.sendall(
                                (json.dumps(reply, default=str) + "\n").encode("utf-8"))
            except (socket.timeout, OSError):
                pass

    def stop(self) -> None:
        self._stop.set()
        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass


def send_local(port: int, payload: Dict[str, Any], timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
            sock.sendall((json.dumps(payload, default=str) + "\n").encode("utf-8"))
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Overview popup
# ---------------------------------------------------------------------------

class Overview(tk.Toplevel):
    """Recent-activity overview + the Intervention paste bar.

    Two tabs: "Recent activity" (the original view — its only button remains
    SQL Viewer) and "Intervene" (paste a circling agent's output, get a
    ready-to-paste intervention built from the skills folder + memory DB).
    """

    def __init__(self, master: "DeskBar") -> None:
        super().__init__(master)
        self.bar = master
        self.title("MapThinkDo — Recent Activity")
        self.configure(bg=THEME["bg"])
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.resizable(False, False)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = tk.Frame(self, bg=THEME["bg_alt"])
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, text="MapThinkDo — recent activity",
                 bg=THEME["bg_alt"], fg=THEME["fg"],
                 font=("Segoe UI", 11, "bold")).pack(side="left", padx=10, pady=6)
        self.stats_label = tk.Label(header, text="", bg=THEME["bg_alt"],
                                    fg=THEME["dim"], font=("Segoe UI", 9))
        self.stats_label.pack(side="right", padx=10)

        body = tk.Frame(self, bg=THEME["bg"])
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(6, 2))

        # ---- tabs: activity / intervene -----------------------------------
        self.tabs = ttk.Notebook(body)
        self.tabs.pack(fill="both", expand=True)

        activity = tk.Frame(self.tabs, bg=THEME["bg"])
        self.tabs.add(activity, text="Recent activity")

        self.text = tk.Text(activity, wrap="none", bg=THEME["bg"], fg=THEME["fg"],
                            insertbackground=THEME["fg"], relief="flat",
                            font=("Consolas", 10), width=96, height=20,
                            padx=8, pady=6, spacing1=1, spacing3=1)
        sb = ttk.Scrollbar(activity, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set, state="disabled")
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        for tag, color in (("time", THEME["dim"]), ("call", THEME["call"]),
                           ("result", THEME["result"]), ("error", THEME["err"]),
                           ("thought", THEME["thought"]),
                           ("session", THEME["session"]),
                           ("dim", THEME["dim"]), ("text", THEME["fg"])):
            self.text.tag_configure(tag, foreground=color)
        self.text.tag_configure("bold", font=("Consolas", 10, "bold"))

        # -- the Intervene tab (paste bar) ----------------------------------
        ivp = tk.Frame(self.tabs, bg=THEME["bg"])
        self.tabs.add(ivp, text=" Intervene")
        ivp.columnconfigure(0, weight=1)

        tk.Label(ivp, bg=THEME["bg"], fg=THEME["dim"], font=("Segoe UI", 9),
                 anchor="w", justify="left", text=
                 "Paste the circling agent's last few messages, then Analyze (or Ctrl+Enter). "
                 "You get a copy-paste intervention: retrieved skill chunks + a "
                 "'use map-think-do NOW' call + a measured improvement estimate.").grid(
            row=0, column=0, sticky="ew", padx=6, pady=(4, 2))

        self.paste_text = tk.Text(ivp, wrap="word", bg=THEME["bg_alt"],
                                  fg=THEME["fg"], insertbackground=THEME["fg"],
                                  relief="flat", font=("Consolas", 10),
                                  height=7, padx=8, pady=6)
        self.paste_text.grid(row=1, column=0, sticky="ew", padx=6, pady=2)
        self.paste_text.bind("<Control-Return>",
                             lambda _e: self.bar.run_intervention())

        btns = tk.Frame(ivp, bg=THEME["bg"])
        btns.grid(row=2, column=0, sticky="ew", padx=6, pady=2)
        self.ivp_analyse_btn = tk.Button(
            btns, text="Analyze", command=self.bar.run_intervention,
            bg=THEME["accent"], fg="#0b0d12", activebackground="#93b4ff",
            activeforeground="#0b0d12", relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"), padx=18, pady=4, cursor="hand2")
        self.ivp_analyse_btn.pack(side="left")
        self.ivp_copy_btn = tk.Button(
            btns, text="Copy intervention", command=self.bar.copy_intervention,
            bg=THEME["bg_alt"], fg=THEME["fg"],
            activebackground=THEME["bg_alt"], relief="flat", bd=0,
            font=("Segoe UI", 10), padx=14, pady=4, cursor="hand2",
            state="disabled")
        self.ivp_copy_btn.pack(side="left", padx=6)
        tk.Button(btns, text="Clear", command=self.clear_intervention,
                  bg=THEME["bg_alt"], fg=THEME["dim"],
                  activebackground=THEME["bg_alt"], relief="flat", bd=0,
                  font=("Segoe UI", 10), padx=14, pady=4, cursor="hand2"
                  ).pack(side="left")
        self.ivp_status = tk.Label(btns, text="", bg=THEME["bg"],
                                   fg=THEME["dim"], font=("Segoe UI", 9))
        self.ivp_status.pack(side="right")

        self.ivp_result = tk.Text(ivp, wrap="word", bg=THEME["bg"],
                                  fg=THEME["fg"], insertbackground=THEME["fg"],
                                  relief="flat", font=("Consolas", 10),
                                  height=13, padx=8, pady=6, state="disabled")
        rsb = ttk.Scrollbar(ivp, orient="vertical", command=self.ivp_result.yview)
        self.ivp_result.configure(yscrollcommand=rsb.set)
        self.ivp_result.grid(row=3, column=0, sticky="nsew", padx=6, pady=(2, 4))
        rsb.grid(row=3, column=1, sticky="ns", pady=(2, 4))
        ivp.rowconfigure(3, weight=1)
        for tag, color in (("hdr", THEME["accent"]), ("ok", THEME["ok"]),
                           ("err", THEME["err"]), ("dim", THEME["dim"]),
                           ("text", THEME["fg"]), ("chunk", THEME["thought"]),
                           ("num", THEME["session"])):
            self.ivp_result.tag_configure(tag, foreground=color)

        footer = tk.Frame(self, bg=THEME["bg"])
        footer.grid(row=2, column=0, sticky="ew", pady=(4, 10))
        footer.columnconfigure(0, weight=1)

        self.hint = tk.Label(footer,
                             text="Esc or click outside to close · Ctrl+Enter = Analyze",
                             bg=THEME["bg"], fg=THEME["dim"], font=("Segoe UI", 8))
        self.hint.grid(row=0, column=0, sticky="w", padx=12)

        # The one and only button.
        self.viewer_btn = tk.Button(
            footer, text="SQL Viewer", command=self.bar.open_viewer,
            bg=THEME["accent"], fg="#0b0d12", activebackground="#93b4ff",
            activeforeground="#0b0d12", relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"), padx=22, pady=6, cursor="hand2")
        self.viewer_btn.grid(row=0, column=1, sticky="e", padx=12)

        self.bind("<Escape>", lambda _e: self.hide())
        self.bind("<FocusOut>", self._on_focus_out)
        self._closing = False

    def _on_focus_out(self, _event=None) -> None:
        # Defer: Tk fires FocusOut while the button click is in flight.
        self.after(180, self._maybe_hide)

    def _maybe_hide(self) -> None:
        # The old check used focus_displayof(), which stays populated even
        # after another application steals the focus, so the popup never
        # closed on outside clicks.  Instead: hide unless a widget inside
        # this popup still holds the keyboard focus.
        try:
            focus = self.focus_get()
        except tk.TclError:
            focus = None
        if focus is None:
            self.hide()
            return
        node = focus
        while node is not None:
            if node is self:
                return  # focus is still ours; keep the popup open
            try:
                node = getattr(node, "master", None)
            except tk.TclError:
                break
        self.hide()

    # -- intervene helpers ---------------------------------------------------

    def clear_intervention(self) -> None:
        self.paste_text.delete("1.0", "end")
        self.ivp_result.configure(state="normal")
        self.ivp_result.delete("1.0", "end")
        self.ivp_result.configure(state="disabled")
        self.ivp_copy_btn.configure(state="disabled")
        self.set_ivp_status("")

    def set_ivp_status(self, text: str) -> None:
        self.ivp_status.configure(text=text[:160])

    def show_intervene_tab(self) -> None:
        try:
            self.tabs.select(1)
        except tk.TclError:
            pass

    def render_intervention(self, result: Dict[str, Any]) -> None:
        """Paint the analysis result into the Intervene tab."""
        w = self.ivp_result
        w.configure(state="normal")
        w.delete("1.0", "end")
        if not result.get("ok"):
            w.insert("end", result.get("error") or "analysis failed\n", ("err",))
        else:
            prov = result.get("provider", "")
            w.insert("end",
                     f"embedding: {prov} · index: "
                     f"{result.get('index_files', 0)} files / "
                     f"{result.get('index_chunks', 0)} chunks · "
                     f"{result.get('elapsed_ms', 0)} ms\n", ("dim",))
            est = result.get("estimate") or {}
            w.insert("end", "\n→ estimated improvement from re-engaging "
                            "map-think-do: ", ("text",))
            w.insert("end", f"~{est.get('estimate', '?')}%\n", ("num",))
            w.insert("end", f"  work: {est.get('work', '')}\n\n", ("dim",))
            for ch in result.get("chunks", []):
                w.insert("end", f"● {ch.get('file')} :: {ch.get('title')} "
                                f"(sim {ch.get('score')})\n", ("chunk",))
            w.insert("end", "\nThe full intervention is on the clipboard — "
                            "paste it into the circling agent.\n", ("ok",))
        w.configure(state="disabled")
        self.ivp_copy_btn.configure(state="normal")

    def show(self, items: List[Dict[str, Any]], stats: Dict[str, Any]) -> None:
        self.render(items, stats)
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.position_above_bar()
        self.focus_force()

    def hide(self) -> None:
        try:
            self.withdraw()
        except tk.TclError:
            pass

    def position_above_bar(self) -> None:
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        bar = self.bar
        try:
            bx = bar.winfo_x()
            by = bar.winfo_y()
            bw = bar.winfo_width()
        except tk.TclError:
            bx, by, bw = 0, 0, w
        screen_h = bar.winfo_screenheight()
        # Prefer directly above the bar; flip below if there is no room.
        y = by - h - 4
        if y < 4:
            y = by + bar.winfo_height() + 4
        x = max(4, min(bx + bw - w, bar.winfo_screenwidth() - w - 8))
        y = max(4, min(y, screen_h - h - 8))
        self.geometry(f"{w}x{h}+{int(x)}+{int(y)}")

    def render(self, items: List[Dict[str, Any]], stats: Dict[str, Any]) -> None:
        self.stats_label.configure(
            text="{sessions} sessions · {thoughts} thoughts · {events} MCP events · db {size} MB".format(
                sessions=stats.get("sessions", 0),
                thoughts=stats.get("thoughts", 0),
                events=stats.get("raw_events", 0),
                size=stats.get("db_size_mb", 0.0),
            ))

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")

        if not items:
            self.text.insert("end", "No activity yet.\n\n", ("dim",))
            self.text.insert(
                "end",
                "Once an MCP client calls the map-think-do tool, sessions,\n"
                "thoughts and raw MCP events will appear here.\n\n", ("dim",))
            dbp = stats.get("db_path")
            if dbp:
                self.text.insert("end", f"Watching: {dbp}\n", ("dim",))
                if not stats.get("exists"):
                    self.text.insert(
                        "end",
                        "(that file does not exist yet — it is created on first use)",
                        ("dim",))
        else:
            for item in items:
                kind = item.get("kind", "")
                when = mtd_shared.format_ts(item.get("ts"), "time")
                ago = mtd_shared.human_ago(item.get("ts"))
                self.text.insert("end", f"{when:>8}  ", ("time",))
                self.text.insert("end", f"{item.get('detail', ''):<16}", (kind,))
                self.text.insert("end", f" {ago:<9}", ("dim",))
                sid = (item.get("session") or "")[:14]
                if sid:
                    self.text.insert("end", f"{sid:<16}", ("dim",))
                text = (item.get("text") or "").replace("\n", " ").strip()
                self.text.insert("end", text[:220], ("text",))
                self.text.insert("end", "\n")

        self.text.configure(state="disabled")
        self.text.yview_moveto(0.0)


# ---------------------------------------------------------------------------
# The desk bar
# ---------------------------------------------------------------------------

class DeskBar(tk.Tk):
    def __init__(self, cfg: Dict[str, Any]) -> None:
        super().__init__()
        self.cfg = cfg
        self.desk = mtd_shared.desk_dir()
        self.reader = mtd_shared.ActivityReader(mtd_shared.db_path())

        self._queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.activity: List[Dict[str, Any]] = []
        self.stats: Dict[str, Any] = {}
        self.server_up = False
        self._live: List[Dict[str, Any]] = []
        self._hidden = False
        self._closing = False
        self._ivp_busy = False
        self._last_intervention: Optional[str] = None

        self.title("MapThinkDo")
        self.configure(bg=THEME["bg"])
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", float(cfg.get("opacity") or 0.96))
        except tk.TclError:
            pass

        self._build()
        self.overview: Optional[Overview] = None
        self._ensure_overview()

        # Win32 appbar: needs a real HWND, so wait until the window exists.
        self.after(60, self._dock)
        # Renegotiate the dock occasionally (display changes, taskbar moves,
        # auto-hide toggles).  Cheap: one SHAppBarMessage round-trip.
        self.after(1500, self._redock_loop)

        self.protocol("WM_DELETE_WINDOW", self.quit_bar)
        self.bind("<Escape>", lambda _e: self._hide_overview())
        self._poll()
        self._drain()

    # -- UI ----------------------------------------------------------------

    def _build(self) -> None:
        bar = tk.Frame(self, bg=THEME["bg"], height=int(self.cfg.get("bar_height") or 30))
        bar.pack(fill="both", expand=True)
        bar.pack_propagate(False)
        self.bar_frame = bar

        self.led = tk.Canvas(bar, width=12, height=12, bg=THEME["bg"],
                             highlightthickness=0)
        self.led.pack(side="left", padx=(10, 4))
        self.led_oval = self.led.create_oval(2, 2, 11, 11, fill=THEME["dim"],
                                             outline="")

        tk.Label(bar, text="MapThinkDo", bg=THEME["bg"], fg=THEME["accent"],
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(2, 4))

        self.ivp_btn = tk.Label(bar, text=" Intervene", bg=THEME["bg"],
                                fg=THEME["session"], font=("Segoe UI", 9, "bold"),
                                cursor="hand2")
        self.ivp_btn.pack(side="left", padx=(4, 8))

        self.ticker = tk.Label(bar, text="watching for activity…", bg=THEME["bg"],
                               fg=THEME["fg"], font=("Segoe UI", 9), anchor="w")
        self.ticker.pack(side="left", fill="x", expand=True, padx=4)

        self.counts = tk.Label(bar, text="", bg=THEME["bg"], fg=THEME["dim"],
                               font=("Segoe UI", 9))
        self.counts.pack(side="right", padx=(8, 10))

        for widget in (bar, self.ticker, self.counts):
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Button-3>", self._on_right_click)
        self.led.bind("<Button-1>", self._on_click)
        self.led.bind("<Button-3>", self._on_right_click)
        self.ivp_btn.bind("<Button-1>", lambda _e: self.open_intervene())
        self.ivp_btn.bind("<Button-3>", self._on_right_click)

        self.menu = tk.Menu(self, tearoff=0, bg=THEME["bg_alt"], fg=THEME["fg"],
                            activebackground=THEME["accent"],
                            activeforeground="#0b0d12")
        self.menu.add_command(label="Show overview", command=self.toggle_overview)
        self.menu.add_command(label=" Intervention paste bar…",
                              command=self.open_intervene)
        self.menu.add_command(label="Open SQL Viewer", command=self.open_viewer)
        self.menu.add_separator()
        self.menu.add_command(label="Refresh now", command=self.refresh)
        self.menu.add_command(label="Hide bar (launcher will wake it)",
                              command=self.hide_bar)
        self.menu.add_separator()
        self.menu.add_command(label="Quit", command=self.quit_bar)

    def _ensure_overview(self) -> None:
        if self.overview is None:
            self.overview = Overview(self)
            self.overview.withdraw()

    # -- docking -----------------------------------------------------------

    def _dock(self) -> None:
        try:
            self.update_idletasks()
            hwnd = self.winfo_id()
        except tk.TclError:
            hwnd = 0
        self.dock = Dock(hwnd, edge=str(self.cfg.get("dock_edge") or "bottom"),
                         sit_above_taskbar=bool(self.cfg.get("sit_above_taskbar")))
        self.dock.register()
        self._reposition(first=True)

    def _redock_loop(self) -> None:
        """Periodically re-assert our docked position (every ~20s)."""
        if self._closing:
            return
        try:
            if not self._hidden and getattr(self, "dock", None):
                rect = self.dock.position(int(self.cfg.get("bar_height") or 30))
                if rect:
                    x, y, w, h = rect
                    cur = (self.winfo_x(), self.winfo_y(),
                           self.winfo_width(), self.winfo_height())
                    if (x, y, w, h) != cur:
                        self.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")
        except Exception:  # noqa: BLE001 - never let the timer kill the bar
            pass
        self.after(20000, self._redock_loop)

    def _reposition(self, first: bool = False) -> None:
        height = int(self.cfg.get("bar_height") or 30)
        rect = None
        try:
            if getattr(self, "dock", None):
                rect = self.dock.position(height)
        except Exception as exc:  # noqa: BLE001
            print(f"[{APP}] reposition failed: {exc}", file=sys.stderr)
        if rect:
            x, y, w, h = rect
            self.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")
        elif first:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            self.geometry(f"{sw}x{height}+0+{sh - height}")
        if not self._hidden:
            try:
                self.deiconify()
                self.lift()
                self.attributes("-topmost", True)
            except tk.TclError:
                pass

    # -- interaction -------------------------------------------------------

    def _on_click(self, _event=None) -> None:
        self.toggle_overview()

    def _on_right_click(self, event=None) -> None:
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def toggle_overview(self, intervene: bool = False) -> None:
        self._ensure_overview()
        if self.overview.state() == "withdrawn":
            self.refresh()
            if intervene:
                self.overview.show_intervene_tab()
            self.overview.show(self.activity, self.stats)
        elif intervene:
            # already open: jump straight to the paste bar
            self.overview.show_intervene_tab()
            self.overview.show(self.activity, self.stats)
        else:
            self._hide_overview()

    def open_intervene(self) -> None:
        """Open the overview popup on the Intervention paste-bar tab."""
        self._ensure_overview()
        if self._hidden:
            self.show_bar()
        self.refresh()
        self.overview.show_intervene_tab()
        self.overview.show(self.activity, self.stats)

    def _hide_overview(self) -> None:
        if self.overview is not None:
            self.overview.hide()

    def hide_bar(self) -> None:
        self._hidden = True
        self._hide_overview()
        self.withdraw()

    def show_bar(self) -> None:
        self._hidden = False
        self._reposition()

    def quit_bar(self, *_a) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            if getattr(self, "dock", None):
                self.dock.unregister()
        except Exception:  # noqa: BLE001
            pass
        try:
            super().quit()
            self.destroy()
        except tk.TclError:
            pass

    # -- SQL viewer --------------------------------------------------------

    def open_viewer(self) -> None:
        """Launch the MapThinkDo SQL viewer against the memory database."""
        viewer = self.cfg.get("viewer_script") or "mapthinkdo_viewer.py"
        vpath = Path(viewer)
        if not vpath.is_absolute():
            vpath = self.desk / vpath
        if not vpath.exists():
            self._flash("viewer script not found: %s" % vpath)
            return

        db = str(self.reader.path)
        exe = self.cfg.get("pythonw_exe") or ""
        popen_kwargs: Dict[str, Any] = {}
        if not exe:
            exe = sys.executable or "python"
            if IS_WIN:
                cand = Path(exe).with_name("pythonw.exe")
                if cand.exists():
                    exe = str(cand)
                else:
                    # python.exe without a console: CREATE_NO_WINDOW.
                    popen_kwargs["creationflags"] = 0x08000000
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    popen_kwargs["startupinfo"] = startupinfo
        try:
            # NOTE: creationflags/startupinfo are Windows-only kwargs; passing
            # them on Linux/macOS raised ValueError and killed the click.
            subprocess.Popen([exe, str(vpath), db], cwd=str(self.desk),
                             close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, **popen_kwargs)
            self._flash("opening SQL Viewer…")
        except OSError as exc:
            self._flash("could not open viewer: %s" % exc)

    def _flash(self, message: str) -> None:
        self.ticker.configure(text=message)
        self.after(2500, self._render_ticker)

    # -- intervention paste bar ----------------------------------------------

    def run_intervention(self) -> None:
        """Analyze the pasted trace in a worker thread (never block Tk)."""
        if self._ivp_busy:
            self.overview.set_ivp_status("analysis already running…")
            return
        self._ensure_overview()
        paste = self.overview.paste_text.get("1.0", "end").strip()
        if not paste:
            self.overview.set_ivp_status("paste the agent's last messages first")
            self.overview.show_intervene_tab()
            return
        self._ivp_busy = True
        self.overview.ivp_analyse_btn.configure(state="disabled")
        self.overview.set_ivp_status("analyzing…")
        self._flash(" building intervention…")
        cfg = dict(self.cfg)
        if not isinstance(cfg.get("intervention"), dict):
            cfg["intervention"] = {}

        def post(text: str) -> None:
            # called from the worker thread; the queue is thread-safe and the
            # Tk thread drains it every 120 ms
            self._queue.put({"type": "intervention-status", "text": text})

        def work() -> None:
            try:
                import mtd_intervention
                result = mtd_intervention.build_intervention(paste, cfg, log=post)
            except Exception as exc:  # noqa: BLE001 - surface, never crash the bar
                result = {"ok": False, "error": f"intervention failed: {exc}",
                          "message": ""}
            self._queue.put({"type": "intervention", "result": result})

        threading.Thread(target=work, name="intervention", daemon=True).start()

    def copy_intervention(self) -> None:
        """Put the last intervention block on the clipboard."""
        if not self._last_intervention:
            self.overview.set_ivp_status("nothing to copy yet — run Analyze first")
            return
        self.clipboard_clear()
        self.clipboard_append(self._last_intervention)
        self.overview.set_ivp_status("intervention copied to clipboard")

    def _finish_intervention(self, result: Dict[str, Any]) -> None:
        self._ivp_busy = False
        try:
            self.overview.ivp_analyse_btn.configure(state="normal")
        except tk.TclError:
            return
        if result.get("ok"):
            self._last_intervention = result.get("message", "")
            # auto-copy: keeps the whole flow at exactly two C+V round trips
            self.clipboard_clear()
            self.clipboard_append(self._last_intervention)
            est = (result.get("estimate") or {}).get("estimate", "?")
            self.overview.render_intervention(result)
            self.overview.set_ivp_status(
                f"copied to clipboard (~{est}% estimate)")
            self._flash(f" intervention ready (~{est}%) — on clipboard")
        else:
            self._last_intervention = None
            self.overview.render_intervention(result)
            self.overview.set_ivp_status("failed — see result pane")

    # -- data --------------------------------------------------------------

    def refresh(self) -> None:
        try:
            self.stats = self.reader.stats()
            self.activity = self.reader.recent_activity(
                int(self.cfg.get("activity_limit") or 60))
        except Exception as exc:  # noqa: BLE001
            self.activity = []
            self.stats = {"db_path": str(self.reader.path), "error": str(exc)}
        self._render_ticker()
        self._render_counts()
        if self.overview is not None and self.overview.state() != "withdrawn":
            self.overview.render(self.activity, self.stats)

    def _render_ticker(self) -> None:
        # Live (IPC-pushed) messages are preferred for ~45s; after that the
        # ticker falls back to the database activity feed so it never gets
        # stuck on the last tool call forever.
        cutoff = time.time() - 45
        if self._live:
            self._live = [i for i in self._live if i.get("epoch", 0) >= cutoff]
        if self._live:
            item = self._live[-1]
            prefix = {"call": "→", "result": "←", "error": ""}.get(
                item.get("kind", ""), "·")
            text = item.get("text") or item.get("detail") or ""
            self.ticker.configure(text=f"{prefix} {text[:180]}")
            return
        if self.activity:
            item = self.activity[0]
            when = mtd_shared.human_ago(item.get("ts"))
            text = (item.get("text") or item.get("detail") or "").strip()
            self.ticker.configure(text=f"{item.get('detail','')} · {when} · {text[:170]}")
        else:
            self.ticker.configure(text="watching for activity…")

    def _render_counts(self) -> None:
        s = self.stats or {}
        self.counts.configure(
            text="{sessions}S {thoughts}T {events}E".format(
                sessions=s.get("sessions", 0), thoughts=s.get("thoughts", 0),
                events=s.get("raw_events", 0)))
        color = THEME["ok"] if self.server_up else THEME["dim"]
        if s.get("sessions"):
            color = THEME["ok"]
        self.led.itemconfigure(self.led_oval, fill=color)

    # -- loops -------------------------------------------------------------

    def _poll(self) -> None:
        """Re-read the database on a timer (cheap; WAL readers don't block)."""
        try:
            self.refresh()
        except Exception:  # noqa: BLE001
            pass
        self.after(int(float(self.cfg.get("poll_seconds") or 3) * 1000), self._poll)

    def _drain(self) -> None:
        """Process messages posted from the IPC thread (Tk is single-threaded)."""
        try:
            while True:
                msg = self._queue.get_nowait()
                self._handle_ipc(msg)
        except queue.Empty:
            pass
        self.after(120, self._drain)

    def _handle_ipc(self, msg: Dict[str, Any]) -> None:
        kind = msg.get("type")
        if kind == "quit":
            self.quit_bar()
        elif kind == "wake":
            if self._hidden:
                self.show_bar()
            self.lift()
        elif kind == "show":
            self.show_bar()
            self.toggle_overview()
        elif kind == "intervene":
            self.open_intervene()
        elif kind == "intervention":
            self._finish_intervention(msg.get("result") or {})
        elif kind == "intervention-status":
            try:
                self.overview.set_ivp_status(str(msg.get("text") or ""))
            except (AttributeError, tk.TclError):
                pass
        elif kind == "server":
            self.server_up = (msg.get("state") == "up")
            self._render_counts()
        elif kind == "mcp":
            direction = msg.get("direction")
            tool = msg.get("tool") or msg.get("method") or "mcp"
            if "error" in msg:
                kind_name, detail = "error", f" {tool}"
            elif direction == "request":
                kind_name, detail = "call", f"→ {tool}"
            else:
                kind_name, detail = "result", f"← {tool}"
            text = msg.get("text") or ""
            if not text and msg.get("thought_number"):
                text = "thought {}/{}".format(msg.get("thought_number"),
                                              msg.get("total_thoughts") or "?")
            self._live.append({
                "kind": kind_name, "detail": detail, "text": text,
                "ts": mtd_shared.iso_now(),
                "epoch": time.time(),
                "session": msg.get("session_id") or "",
            })
            if len(self._live) > 40:
                del self._live[:-40]
            self._render_ticker()
            # Keep the overview honest while it is open.
            self.after(400, self.refresh)

    # -- IPC ---------------------------------------------------------------

    def on_ipc(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if msg.get("type") == "ping":
            return {"type": "pong"}
        self._queue.put(msg)
        return {"ok": True}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    quiet = "--quiet" in argv

    def log(msg: str) -> None:
        if not quiet:
            try:
                sys.stderr.write(msg + "\n")
                sys.stderr.flush()
            except Exception:  # noqa: BLE001
                pass

    cfg = mtd_shared.load_bar_config()
    port = int(cfg.get("bar_port") or 38457)

    # Single instance: if something is already listening, wake it and exit.
    if send_local(port, {"type": "ping"}):
        send_local(port, {"type": "wake"})
        log(f"[{APP}] already running on port {port}")
        return 0

    ipc = IpcServer(port, None, log=log)  # noqa: E501 - callback attached below
    if not ipc.bind():
        log(f"[{APP}] port {port} busy; assuming another instance is running")
        return 1

    app = DeskBar(cfg)
    ipc.on_message = app.on_ipc
    ipc.start()

    try:
        app.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        ipc.stop()
        try:
            app.dock.unregister()
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
