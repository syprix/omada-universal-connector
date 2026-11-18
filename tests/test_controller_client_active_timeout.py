import unittest

from app.controller_client_active_timeout import (
    ControllerClientActiveTimeoutError, project_controller_client_active_timeout,
)


class ControllerClientActiveTimeoutTests(unittest.TestCase):
    def test_projects_documented_int32_value_without_enforcing_contradictory_example_range(self):
        for value in (0, 3, 10, 11):
            with self.subTest(value=value):
                result = project_controller_client_active_timeout({"clientActiveTimeoutMin": value})
                self.assertEqual(result["data"]["active_timeout_minutes"], value)
                self.assertFalse(result["partial"])

    def test_missing_invalid_and_extra_values(self):
        missing = project_controller_client_active_timeout({})
        self.assertTrue(missing["partial"])
        self.assertEqual(missing["data"]["missing_count"], 1)
        for value in (True, 1.5, "5", None, -2**31 - 1, 2**31):
            with self.subTest(value=value):
                result = project_controller_client_active_timeout({"clientActiveTimeoutMin": value})
                self.assertIsNone(result["data"]["active_timeout_minutes"])
                self.assertEqual(result["data"]["invalid_count"], 1)
        extra = project_controller_client_active_timeout({"clientActiveTimeoutMin": 5, "private": "omit"})
        self.assertEqual(extra["data"]["unknown_field_count"], 1)
        self.assertNotIn("private", str(extra))

    def test_rejects_wrong_response_shape_and_unbounded_fields(self):
        for value in (None, [], "bad", {str(i): i for i in range(17)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(ControllerClientActiveTimeoutError):
                project_controller_client_active_timeout(value)


if __name__ == "__main__":
    unittest.main()
