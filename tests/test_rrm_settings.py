from __future__ import annotations

import unittest

from app.rrm_settings import RrmSettingsError, project_rrm_settings


class RrmSettingsProjectionTests(unittest.TestCase):
    def test_projects_only_documented_typed_settings(self) -> None:
        result = project_rrm_settings({
            "mode": 1,
            "timeRangeEnable": True,
            "resource": 2,
            "timeRangeAction": 0,
            "timeRangeId": "private-profile-id",
        })
        self.assertEqual(result["data"], {
            "mode": 1, "timeRangeEnable": True, "resource": 2,
            "timeRangeAction": 0,
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["omitted_field_count"], 1)
        self.assertEqual(result["omitted_fields"], ["timeRangeId"])
        self.assertNotIn("private-profile-id", repr(result))

    def test_complete_projection_has_no_omissions(self) -> None:
        result = project_rrm_settings({
            "mode": 0, "timeRangeEnable": False, "resource": 1,
            "timeRangeAction": 1,
        })
        self.assertEqual(result["partial"], False)
        self.assertEqual(result["omitted_field_count"], 0)
        self.assertEqual(result["omitted_fields"], [])

    def test_missing_invalid_and_unknown_fields_are_reported_without_echoing_keys(self) -> None:
        result = project_rrm_settings({
            "mode": True,
            "timeRangeEnable": "true",
            "resource": 9,
            "timeRangeAction": -1,
            "customer-private-field-name": "sensitive",
        })
        self.assertEqual(result["data"], {})
        self.assertTrue(result["partial"])
        self.assertEqual(result["omitted_field_count"], 5)
        self.assertEqual(result["omitted_fields"], [
            "mode", "resource", "timeRangeAction", "timeRangeEnable", "unknown_fields",
        ])
        self.assertNotIn("customer-private-field-name", repr(result))
        self.assertNotIn("sensitive", repr(result))

    def test_rejects_non_object_and_oversized_field_sets(self) -> None:
        for value in (None, [], "not-object", {f"x{i}": i for i in range(65)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(RrmSettingsError):
                project_rrm_settings(value)


if __name__ == "__main__":
    unittest.main()
