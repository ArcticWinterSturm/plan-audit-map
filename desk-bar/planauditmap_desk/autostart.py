from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import Optional

from .config import AppConfig, APP_NAME, APP_SLUG

WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WINDOWS_VALUE_NAME = "MapThinkDoDeskBar"


def _pythonw_executable() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        candidate = exe.with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
    return str(exe)


def launcher_script_path(config: AppConfig) -> Path:
    suffix = ".cmd" if os.name == "nt" else ".sh"
    return config.base_dir / f"{APP_SLUG}-launcher{suffix}"


def write_launcher_script(config: AppConfig) -> Path:
    script = launcher_script_path(config)
    config.base_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        pythonw = _pythonw_executable()
        body = (
            "@echo off\r\n"
            f'"{pythonw}" -m planauditmap_desk desk --config "{config.config_path}"\r\n'
        )
        script.write_text(body, encoding="utf-8")
    else:
        python = sys.executable
        body = (
            "#!/usr/bin/env sh\n"
            f'exec "{python}" -m planauditmap_desk desk --config "{config.config_path}"\n'
        )
        script.write_text(body, encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def install_autostart(config: AppConfig) -> Path:
    script = write_launcher_script(config)
    if os.name == "nt":
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, WINDOWS_VALUE_NAME, 0, winreg.REG_SZ, str(script))
        return script

    desktop_dir = Path.home() / ".config" / "autostart"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = desktop_dir / f"{APP_SLUG}.desktop"
    content = f"""[Desktop Entry]
Type=Application
Version=1.0
Name={APP_NAME}
Comment=MapThinkDo cross-agent activity bar
Exec={script}
Terminal=false
X-GNOME-Autostart-enabled=true
"""
    desktop_file.write_text(content, encoding="utf-8")
    return desktop_file


def remove_autostart(config: AppConfig) -> bool:
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, WINDOWS_VALUE_NAME)
            return True
        except FileNotFoundError:
            return False

    desktop_file = Path.home() / ".config" / "autostart" / f"{APP_SLUG}.desktop"
    if desktop_file.exists():
        desktop_file.unlink()
        return True
    return False


def autostart_status(config: AppConfig) -> str:
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, WINDOWS_VALUE_NAME)
            return f"enabled: {value}"
        except FileNotFoundError:
            return "disabled"

    desktop_file = Path.home() / ".config" / "autostart" / f"{APP_SLUG}.desktop"
    return f"enabled: {desktop_file}" if desktop_file.exists() else "disabled"
