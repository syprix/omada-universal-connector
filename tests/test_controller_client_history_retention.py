import unittest

from app.controller_client_history_retention import (
    ControllerClientHistoryRetentionError,
    project_controller_client_history_retention,
)


class ControllerClientHistoryRetentionTests(unittest.TestCase):
    def test_projects_documented_flags(self):
        result = project_controller_client_history_retention({
            "clientsDataEnable": True, "clientStatEnable": False,
        })
        self.assertEqual(result["data"]["client_history_enabled"], True)
        self.assertEqual(result["data"]["client_trend_enabled"], False)
        self.assertFalse(result["partial"])

    def test_missing_invalid_and_unknown_values_are_partial_and_redacted(self):
        result = project_controller_client_history_retention({
            "clientsDataEnable": 1, "private": "secret",
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["missing_count"], 1)
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("secret", str(result))

    def test_rejects_wrong_shape_and_unbounded_object(self):
        for value in (None, [], "bad", {str(i): i for i in range(17)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(
                    ControllerClientHistoryRetentionError):
                project_controller_client_history_retention(value)


if __name__ == "__main__":
    unittest.main()
