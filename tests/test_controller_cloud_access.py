import unittest

from app.controller_cloud_access import (
    ControllerCloudAccessError, project_controller_cloud_access,
)


class ControllerCloudAccessTests(unittest.TestCase):
    def test_projects_status_without_exposing_owner(self):
        result = project_controller_cloud_access({
            "enable": True, "status": 1, "owner": "private-account",
        })
        self.assertEqual(result["data"], {
            "enabled": True, "connection": "connected", "owner_present": True,
        })
        self.assertNotIn("private-account", repr(result))
        self.assertFalse(result["partial"])

    def test_invalid_unknown_and_missing_fields_are_counted(self):
        result = project_controller_cloud_access({"enable": 1, "status": 9, "extra": "private"})
        self.assertEqual(result["missing_field_count"], 0)
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_rejects_non_object_or_oversized_result(self):
        for raw in ([], {str(i): i for i in range(17)}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ControllerCloudAccessError):
                project_controller_cloud_access(raw)


if __name__ == "__main__":
    unittest.main()
