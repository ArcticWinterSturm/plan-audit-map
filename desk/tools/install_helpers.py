#!/usr/bin/env python3
"""install_helpers.py — shared post-build setup for plan-audit-map-desk.

Called by install.bat (and reusable on any OS):

    python install_helpers.py <desk_dir> <dist_index.js> <python_exe> \
        <desk-bar.json> <node_exe> <connect_dir>

Writes ~/.plan-audit-map/desk-bar.json (merged over any existing config) and
resolves connect/*.json templates (with __NODE__, __PYTHON__, __DIST_INDEX__,
__DESK_DIR__ tokens) into connect/*.local.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def fwd(p: str) -> str:
    return str(Path(p)).replace("\\", "/")


def main() -> int:
    if len(sys.argv) < 7:
        print(__doc__)
        return 2
    desk, dist_index, py, cfg_path, node, connect = sys.argv[1:7]

    # ---- desk-bar.json (merge) -------------------------------------------
    p = Path(cfg_path)
    cfg = {}
    if p.exists():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    cfg.update(
        {
            "enabled": True,
            "viewer_script": str(Path(desk) / "planauditmap_viewer.py"),
            "server_command": ["node", str(Path(dist_index))],
            "log_raw_events": True,
            "mirror_jsonl": True,
            "python_exe": py,
        }
    )
    # intervention paste bar: point at the shipped skills folder (the ONE
    # folder it chunks + embeds) when the user hasn't chosen their own
    ivp = cfg.get("intervention")
    if not isinstance(ivp, dict):
        ivp = {}
    if not ivp.get("skills_dir"):
        shipped = Path(desk).parent / "skills"
        if shipped.is_dir():
            ivp["skills_dir"] = str(shipped)
    cfg["intervention"] = ivp
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"wrote {p}")

    # ---- connection templates ---------------------------------------------
    tokens = {
        "__NODE__": fwd(node),
        "__DIST_INDEX__": fwd(dist_index),
        "__PYTHON__": fwd(py) or "python",
        "__DESK_DIR__": fwd(desk),
    }
    resolved = 0
    for tpl in sorted(Path(connect).glob("*.json")):
        if tpl.name.endswith(".local.json"):
            continue
        text = tpl.read_text(encoding="utf-8")
        for token, value in tokens.items():
            text = text.replace(token, value)
        try:
            obj = json.loads(text)  # validate before writing
        except json.JSONDecodeError as exc:
            print(f"skip {tpl.name}: {exc}")
            continue
        out = tpl.with_name(tpl.stem + ".local.json")
        out.write_text(json.dumps(obj, indent=2), encoding="utf-8")
        print(f"resolved {out.name}")
        resolved += 1
    print(f"{resolved} connection file(s) resolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
