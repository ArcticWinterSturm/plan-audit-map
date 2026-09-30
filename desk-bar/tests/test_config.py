from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from planauditmap_desk.config import CONFIG_FILENAME, default_base_dir, ensure_config, normalize_config_dict


class ConfigTests(unittest.TestCase):
    def test_default_base_dir_prefers_planauditmap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            result = default_base_dir(home)
            self.assertEqual(result, home / ".plan-audit-map")

    def test_default_base_dir_uses_legacy_when_only_legacy_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            legacy = home / ".code-reasoning"
            legacy.mkdir()
            result = default_base_dir(home)
            self.assertEqual(result, legacy)

    def test_ensure_config_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / CONFIG_FILENAME
            cfg = ensure_config(path)
            self.assertTrue(path.exists())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(Path(payload["base_dir"]), Path(tmp))
            self.assertEqual(cfg.config_path, path)

    def test_normalize_config_fills_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = normalize_config_dict({"window": {"width": 500}}, base_dir=Path(tmp))
            self.assertEqual(data["window"]["width"], 500)
            self.assertTrue(str(data["db_path"]).endswith("desk-bar.sqlite3"))


if __name__ == "__main__":
    unittest.main()
