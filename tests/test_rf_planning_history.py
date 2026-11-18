from __future__ import annotations

import unittest

from app.rf_planning_history import RfPlanningHistoryError, project_rf_planning_history


class RfPlanningHistoryTests(unittest.TestCase):
    def test_projects_documented_history_and_redacts_ids_messages_and_macs(self) -> None:
        result = project_rf_planning_history({
            "totalRows": 1, "currentPage": 1, "currentSize": 100,
            "data": [{
                "planningHistroyId": "private-history-id", "time": 1_800_000_000_000,
                "beforeIndex": 54, "afterIndex": 79, "apNum": 7, "length": 38,
                "mode": 1, "isScanSuccess": True, "isAppliedSuccess": True,
                "currentConfig": 1, "msg": "private message", "msgType": 0,
                "failedMacs2g": "AA:BB:CC:DD:EE:FF",
            }],
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["items"][0]["after_index"], 79)
        self.assertEqual(result["data"]["count"], 1)
        for secret in ("private-history-id", "private message", "AA:BB:CC:DD:EE:FF"):
            self.assertNotIn(secret, repr(result))

    def test_truncated_and_invalid_records_are_partial(self) -> None:
        result = project_rf_planning_history({
            "totalRows": 120, "currentPage": 1, "currentSize": 100,
            "data": [{"time": True}, None],
        })
        self.assertTrue(result["partial"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["omitted_field_count"], 2)
        self.assertIn("invalid_records", result["omitted_fields"])

    def test_bounds_and_invalid_pagination_fail_closed(self) -> None:
        with self.assertRaises(RfPlanningHistoryError):
            project_rf_planning_history({"data": [{}] * 101})
        bad_page = project_rf_planning_history({
            "totalRows": 0, "currentPage": 0, "currentSize": 100, "data": [],
        })
        self.assertTrue(bad_page["partial"])
        self.assertIn("invalid_pagination", bad_page["omitted_fields"])

    def test_time_window_omits_records_with_missing_or_out_of_window_time(self) -> None:
        result = project_rf_planning_history({
            "totalRows": 3, "currentPage": 1, "currentSize": 100,
            "data": [
                {"time": 100, "afterIndex": 70},
                {"time": 50, "afterIndex": 60},
                {"afterIndex": 80},
            ],
        }, start_ms=90, end_ms=110)
        self.assertEqual(result["data"]["items"], [{"time_ms": 100, "after_index": 70}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["omitted_field_count"], 2)
        self.assertIn("out_of_window_records", result["omitted_fields"])
        self.assertIn("missing_record_time", result["omitted_fields"])

    def test_history_ids_are_only_exposed_as_validated_opaque_references(self) -> None:
        ref = "c" * 24
        result = project_rf_planning_history({
            "totalRows": 1, "currentPage": 1, "currentSize": 100,
            "data": [{"planningHistroyId": "private-id", "time": 100}],
        }, history_ref_for_id=lambda _history_id: ref)
        self.assertEqual(result["data"]["items"][0]["history_ref"], ref)
        self.assertNotIn("private-id", repr(result))
        invalid = project_rf_planning_history({
            "totalRows": 1, "currentPage": 1, "currentSize": 100,
            "data": [{"planningHistroyId": "private-id", "time": 100}],
        }, history_ref_for_id=lambda _history_id: "invalid")
        self.assertTrue(invalid["partial"])
        self.assertIn("invalid_history_reference", invalid["omitted_fields"])


if __name__ == "__main__":
    unittest.main()
