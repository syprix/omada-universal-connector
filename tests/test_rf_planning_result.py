from __future__ import annotations

import unittest

from app.rf_planning_result import RfPlanningResultError, project_rf_planning_result


class RfPlanningResultTests(unittest.TestCase):
    def test_projects_documented_status_and_indices(self) -> None:
        result = project_rf_planning_result({
            "planningHistroyId": "private-planning-id", "status": 0,
            "beforeIndex": 56, "afterIndex": 78, "failType": 0,
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"], {
            "status": 0, "before_index": 56, "after_index": 78,
            "failure_stage": 0,
        })
        self.assertNotIn("private-planning-id", repr(result))

    def test_status_is_required_and_values_are_bounded(self) -> None:
        missing = project_rf_planning_result({"afterIndex": 30})
        self.assertTrue(missing["partial"])
        self.assertEqual(missing["missing_fields"], ["status"])
        invalid = project_rf_planning_result({
            "status": 4, "beforeIndex": True, "afterIndex": 101, "failType": -1,
        })
        self.assertTrue(invalid["partial"])
        self.assertEqual(invalid["data"], {})
        self.assertEqual(invalid["omitted_field_count"], 4)

    def test_unknown_fields_are_redacted_and_oversized_shapes_rejected(self) -> None:
        result = project_rf_planning_result({"status": 2, "deviceName": "private-ap"})
        self.assertTrue(result["partial"])
        self.assertNotIn("private-ap", repr(result))
        with self.assertRaises(RfPlanningResultError):
            project_rf_planning_result({f"key{i}": i for i in range(17)})


if __name__ == "__main__":
    unittest.main()
