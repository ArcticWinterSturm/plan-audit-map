from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from planauditmap_desk.storage import DeskDatabase
from planauditmap_desk.tracker import normalize_agent_name


class StorageTests(unittest.TestCase):
    def test_record_heartbeat_finish_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = DeskDatabase(Path(tmp) / "desk.sqlite3")
            try:
                launch = db.record_launch(agent="Codex", instance_key="abc", pid=123, cwd=tmp)
                self.assertEqual(launch.agent, "Codex")

                active = db.active_launches(3600)
                self.assertEqual(len(active), 1)
                self.assertEqual(active[0].instance_key, "abc")

                db.heartbeat("abc")
                db.finish("abc", exit_code=7)
                active_after = db.active_launches(3600)
                self.assertEqual(active_after, [])

                recent = db.recent_launches(10)
                self.assertEqual(recent[0].exit_code, 7)

                db.set_state("last_seen_launch_id", "1")
                self.assertEqual(db.get_state("last_seen_launch_id"), "1")
            finally:
                db.close()

    def test_agent_summaries_count_launches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = DeskDatabase(Path(tmp) / "desk.sqlite3")
            try:
                db.record_launch(agent="Codex", instance_key="c1")
                db.record_launch(agent="Codex", instance_key="c2")
                db.finish("c2", 0)
                db.record_launch(agent="Hermes", instance_key="h1")
                summaries = {row["agent"]: row for row in db.agent_summaries(3600)}
                self.assertEqual(summaries["Codex"]["launch_count"], 2)
                self.assertEqual(summaries["Codex"]["active_count"], 1)
                self.assertEqual(summaries["Hermes"]["launch_count"], 1)
                self.assertEqual(summaries["Hermes"]["active_count"], 1)
            finally:
                db.close()

    def test_normalize_agent_name(self) -> None:
        self.assertEqual(normalize_agent_name("claude-code"), "Claude Code")
        self.assertEqual(normalize_agent_name("codex"), "Codex")
        self.assertEqual(normalize_agent_name("hermes"), "Hermes")


if __name__ == "__main__":
    unittest.main()
