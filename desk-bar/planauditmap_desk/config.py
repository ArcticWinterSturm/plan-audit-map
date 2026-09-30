from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

APP_NAME = "MapThinkDo Desk Bar"
APP_SLUG = "planauditmap-desk"
CONFIG_FILENAME = "desk-bar.json"
DB_FILENAME = "desk-bar.sqlite3"


DEFAULT_CONFIG: Dict[str, Any] = {
    "base_dir": "",
    "db_path": "",
    "poll_interval_ms": 1500,
    "show_on_new_launch": True,
    "bring_to_front_on_new_launch": True,
    "single_instance": True,
    "live_timeout_seconds": 75,
    "window": {
        "width": 460,
        "height": 720,
        "corner": "bottom-right",
        "margin_x": 24,
        "margin_y": 24,
        "frameless": False,
        "always_on_top": False,
        "remember_geometry": True,
        "start_minimized": False,
        "double_click_action": "minimize",
    },
    "autostart": {
        "enabled": False,
        "install_scope": "user",
    },
    "agents": {
        "aliases": {
            "claude": "Claude Code",
            "claude-code": "Claude Code",
            "codex": "Codex",
            "opencode": "OpenCode",
            "hermes": "Hermes",
            "chatgpt": "ChatGPT",
        }
    },
}


def default_base_dir(home: Optional[Path] = None) -> Path:
    root = Path.home() if home is None else Path(home)
    preferred = root / ".plan-audit-map"
    legacy = root / ".code-reasoning"
    if preferred.exists() or not legacy.exists():
        return preferred
    return legacy


def default_config_path(base_dir: Optional[Path] = None) -> Path:
    base = default_base_dir() if base_dir is None else Path(base_dir)
    return base / CONFIG_FILENAME


def default_db_path(base_dir: Optional[Path] = None) -> Path:
    base = default_base_dir() if base_dir is None else Path(base_dir)
    return base / DB_FILENAME


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class ConfigError(RuntimeError):
    pass


class AppConfig:
    def __init__(self, data: Dict[str, Any], config_path: Path) -> None:
        self.data = data
        self.config_path = config_path
        self.base_dir = Path(data["base_dir"]).expanduser()
        self.db_path = Path(data["db_path"]).expanduser()

    @property
    def poll_interval_ms(self) -> int:
        return int(self.data.get("poll_interval_ms", 1500))

    @property
    def live_timeout_seconds(self) -> int:
        return int(self.data.get("live_timeout_seconds", 75))

    def to_dict(self) -> Dict[str, Any]:
        return deepcopy(self.data)


def normalize_config_dict(raw: Optional[Dict[str, Any]] = None, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    cfg = _deep_merge(DEFAULT_CONFIG, raw or {})
    base = Path(cfg.get("base_dir") or (base_dir or default_base_dir())).expanduser()
    cfg["base_dir"] = str(base)
    cfg["db_path"] = str(Path(cfg.get("db_path") or default_db_path(base)).expanduser())
    return cfg


def load_config(path: Optional[os.PathLike[str] | str] = None) -> AppConfig:
    cfg_path = Path(path).expanduser() if path else default_config_path()
    if not cfg_path.exists():
        raise ConfigError(f"Config file does not exist: {cfg_path}")
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {cfg_path}: {exc}") from exc
    data = normalize_config_dict(raw, base_dir=cfg_path.parent)
    return AppConfig(data, cfg_path)


def ensure_config(path: Optional[os.PathLike[str] | str] = None) -> AppConfig:
    cfg_path = Path(path).expanduser() if path else default_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg_path.exists():
        return load_config(cfg_path)
    data = normalize_config_dict(base_dir=cfg_path.parent)
    cfg_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return AppConfig(data, cfg_path)


def save_config(config: AppConfig) -> None:
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    config.config_path.write_text(json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8")
