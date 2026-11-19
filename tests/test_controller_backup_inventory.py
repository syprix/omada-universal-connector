from __future__ import annotations

import unittest

from app.controller_backup_inventory import project_controller_backup_inventory


class ControllerBackupInventoryTests(unittest.TestCase):
    def test_summarizes_listed_metadata_and_omits_file_names(self) -> None:
        result = project_controller_backup_inventory(
            {"fileList": [
                {"fileName": "/private/controller-older.cfg", "backupTime": 1_700_000_000_000,
                 "size": 4096},
                {"fileName": "controller-latest.cfg", "backupTime": 1_800_000_000_000,
                 "size": 8192},
            ]},
            {"partial": False, "data": {
                "enabled": True, "schedule_configured": True, "retention_days": 30,
                "saving_path_configured": True, "available_path_count": 4}},
            {"partial": False, "data": {"status": "running"}},
        )
        self.assertEqual(result["backup_file_count"], 2)
        self.assertEqual(result["latest_listed_backup_time_ms"], 1_800_000_000_000)
        self.assertEqual(result["total_listed_backup_bytes"], 12_288)
        self.assertEqual(result["backup_activity"], "running")
        self.assertEqual(result["schedule"], {
            "enabled": True, "schedule_configured": True, "retention_days": 30,
        })
        self.assertNotIn("controller-latest.cfg", repr(result))
        self.assertNotIn("/private", repr(result))
        self.assertNotIn("saving_path_configured", repr(result))

    def test_invalid_entries_and_list_limit_are_partial(self) -> None:
        files = [{"fileName": f"backup-{i}", "backupTime": i, "size": 1}
                 for i in range(513)]
        result = project_controller_backup_inventory(
            {"fileList": files}, {"partial": False, "data": {}},
            {"partial": False, "data": {"status": "idle_or_finished"}},
        )
        self.assertTrue(result["partial"])
        self.assertEqual(result["backup_file_count"], 512)
        self.assertEqual(result["omitted_backup_file_count"], 1)
        invalid = project_controller_backup_inventory(
            {"fileList": [{"fileName": "secret", "backupTime": "bad", "size": -1}]},
            {"partial": False, "data": {}},
            {"partial": False, "data": {"status": "unknown"}},
        )
        self.assertTrue(invalid["partial"])
        self.assertGreater(invalid["invalid_entry_count"], 0)
        self.assertIsNone(invalid["backup_activity"])


if __name__ == "__main__":
    unittest.main()
