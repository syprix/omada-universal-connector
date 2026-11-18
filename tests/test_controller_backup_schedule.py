import unittest

from app.controller_backup_schedule import (
    ControllerBackupScheduleError, project_controller_backup_schedule,
)


class ControllerBackupScheduleTests(unittest.TestCase):
    def test_returns_bounded_schedule_facts_without_path_or_server_values(self):
        result = project_controller_backup_schedule({
            "enable": True, "retention": 30, "maxNumberOfFile": 20,
            "storageType": 0, "savingPath": "/private/backups",
            "availablePaths": ["/private/backups"], "occurrence": {"private": "value"},
            "fileServerConfig": {"host": "private-host", "password": "private-secret"},
            "dataSheets": ["knownClient", "omadaLog"], "retainUser": True,
        })
        self.assertTrue(result["data"]["enabled"])
        self.assertEqual(result["data"]["retention_days"], 30)
        self.assertEqual(result["data"]["storage_type"], "file_server")
        self.assertEqual(result["data"]["available_path_count"], 1)
        self.assertEqual(result["data"]["data_sheet_count"], 2)
        for secret in ("private-host", "private-secret", "/private/backups", "knownClient"):
            self.assertNotIn(secret, repr(result))

    def test_invalid_and_missing_fields_are_explicit(self):
        result = project_controller_backup_schedule({"enable": "yes", "retention": 12})
        self.assertEqual(result["missing_field_count"], 0)
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertTrue(result["partial"])

    def test_rejects_non_object_or_oversized_result(self):
        for raw in ([], {str(i): i for i in range(33)}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ControllerBackupScheduleError):
                project_controller_backup_schedule(raw)


if __name__ == "__main__":
    unittest.main()
