import unittest

from app.controller_retention import (
    ControllerRetentionError, project_controller_retention,
)


class ControllerRetentionTests(unittest.TestCase):
    def test_projects_flags_values_and_available_days(self):
        result = project_controller_retention({
            "clientsDataEnable": True, "clientHealthEnable": False,
            "knownClient": 31, "clientHistory": -1,
            "knownClientAvailableRetentionDays": [1, 7, 31, 90, 180, 365],
        })
        self.assertEqual(result["data"]["flags"], {
            "clients_data_enable": True, "client_health_enable": False,
        })
        self.assertEqual(result["data"]["retention_values"], {
            "known_client": 31, "client_history": -1,
            "known_client_available_retention_days": [1, 7, 31, 90, 180, 365],
        })
        self.assertTrue(result["partial"])

    def test_invalid_types_unknowns_and_oversized_arrays_are_bounded(self):
        result = project_controller_retention({
            "clientsDataEnable": 1, "knownClient": True,
            "dailyAvailableRetentionDays": [7, "31", 90],
            "unrecognized": "private",
        })
        self.assertEqual(result["data"]["invalid_count"], 3)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertEqual(result["data"]["required_missing_count"], 0)
        self.assertEqual(result["data"]["retention_values"]["daily_available_retention_days"], [7, 90])
        self.assertNotIn("private", str(result))
        oversized = project_controller_retention({
            "clientsDataEnable": True,
            "knownClientAvailableRetentionDays": list(range(65)),
        })
        self.assertEqual(oversized["data"]["invalid_count"], 1)
        self.assertNotIn("known_client_available_retention_days",
                         oversized["data"]["retention_values"])
        self.assertTrue(oversized["partial"])
        with self.assertRaisesRegex(ControllerRetentionError, "response_invalid"):
            project_controller_retention([])

    def test_required_boolean_missing_marks_partial(self):
        result = project_controller_retention({"hourly": 7})
        self.assertEqual(result["data"]["required_missing_count"], 1)
        self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
