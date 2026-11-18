from __future__ import annotations

import unittest

from app.experience_index import ExperienceIndexError, project_experience_index


class ExperienceIndexTests(unittest.TestCase):
    def test_projects_documented_optimization_history(self) -> None:
        result = project_experience_index({"lastScan": [{
            "time": 1_800_000_000_000,
            "beforeIndex": 62,
            "afterIndex": 81,
            "isAppliedSuccess": True,
            "apNum": 12,
            "length": 48,
            "mode": 1,
        }]})
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["last_scan"], [{
            "time_ms": 1_800_000_000_000,
            "before_index": 62,
            "after_index": 81,
            "applied_success": True,
            "ap_count": 12,
            "duration_seconds": 48,
            "mode": 1,
        }])

    def test_unknown_fields_are_omitted_and_invalid_values_partial(self) -> None:
        result = project_experience_index({"lastScan": [{
            "time": True, "beforeIndex": 101, "afterIndex": 77,
            "isAppliedSuccess": "yes", "apNum": -1, "length": 5,
            "mode": 2, "clientMac": "AA:BB:CC:DD:EE:FF",
        }]})
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["last_scan"], [
            {"after_index": 77, "duration_seconds": 5},
        ])
        self.assertIn("unknown_fields", result["omitted_fields"])
        self.assertNotIn("clientMac", repr(result))

    def test_empty_and_missing_history(self) -> None:
        self.assertFalse(project_experience_index({"lastScan": []})["partial"])
        self.assertEqual(project_experience_index({})["missing_fields"], ["lastScan"])

    def test_bounds_fail_closed(self) -> None:
        for raw in (None, {"lastScan": [None] * 101},
                    {f"extra{i}": i for i in range(17)}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ExperienceIndexError):
                project_experience_index(raw)


if __name__ == "__main__":
    unittest.main()
