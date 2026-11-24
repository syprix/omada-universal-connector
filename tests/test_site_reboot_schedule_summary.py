from __future__ import annotations

import unittest

from app.site_reboot_schedule_summary import summarize_site_reboot_schedules


class SiteRebootScheduleSummaryTests(unittest.TestCase):
    def test_projects_schedule_fields_and_resolves_current_inventory_targets(self) -> None:
        switch_ref = "a" * 24
        schedule = {
            "id": "private-schedule-id",
            "name": "private-maintenance-name",
            "status": True,
            "deviceMacs": ["AA-BB-CC-DD-EE-FF"],
            "time": {"timingType": 2, "dayOfWeek": 1, "hour": 3, "minute": 15},
            "nextExecute": 1_800_000_000_000,
        }
        result = summarize_site_reboot_schedules(
            [schedule], {switch_ref: "aa:bb:cc:dd:ee:ff"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["schedule_columns"], [
            "enabled", "recurrence", "hour", "minute", "day_of_week_or_month_day",
            "target_count", "target_device_refs", "unresolved_target_count",
            "next_execution_time_ms",
        ])
        row = result["schedule_rows"][0]
        self.assertEqual(row, [True, "weekly", 3, 15, 1, 1, [switch_ref], 0,
                               1_800_000_000_000])
        self.assertEqual(result["schedule_clock_timezone"], "not_specified_by_source")
        self.assertNotIn("private-schedule-id", repr(result))
        self.assertNotIn("private-maintenance-name", repr(result))
        self.assertNotIn("aa:bb:cc:dd:ee:ff", repr(result))
        self.assertIn("does_not_confirm_a_reboot", result["schedule_semantics"])

    def test_unreported_result_is_partial_and_null_result_is_invalid(self) -> None:
        result = summarize_site_reboot_schedules(
            None, {}, result_reported=False)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["partial"])
        self.assertFalse(result["collection_reported"])
        self.assertIsNone(result["schedule_count"])
        self.assertEqual(result["schedule_rows"], [])
        from app.site_reboot_schedule_summary import SiteRebootScheduleError
        with self.assertRaises(SiteRebootScheduleError):
            summarize_site_reboot_schedules(None, {}, result_reported=True)

    def test_unmapped_targets_invalid_values_and_schedule_cap_are_partial(self) -> None:
        row = {"status": True, "deviceMacs": ["00:00:00:00:00:01"],
               "time": {"timingType": 1, "hour": 30, "minute": 0}}
        result = summarize_site_reboot_schedules([row] * 65, {})
        self.assertTrue(result["partial"])
        self.assertEqual(result["omitted_schedule_count"], 1)
        self.assertEqual(result["schedule_rows"][0][7], 1)
        self.assertGreater(result["invalid_entry_or_field_count"], 0)


if __name__ == "__main__":
    unittest.main()
