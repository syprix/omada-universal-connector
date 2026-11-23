import unittest

from app.controller_upgrade_log_summary import (
    ControllerUpgradeLogSummaryError, summarize_upgrade_log_page,
)


class ControllerUpgradeLogSummaryTests(unittest.TestCase):
    def test_aggregates_documented_fields_without_returning_identities(self):
        result = summarize_upgrade_log_page(
            {"totalRows": 2, "currentPage": 1, "currentSize": 2},
            [{"id": "private-id", "siteNames": ["private-site"], "operator": "user",
              "currentVersion": ["1.0"], "targetVersion": "2.0", "upgradeTime": "2026-01-01",
              "rollbacked": False, "failedDeviceNum": 0},
             {"rollbacked": True, "failedDeviceNum": 2, "upgradeTime": "2026-01-02"}],
        )
        self.assertEqual(result["rollbacked_counts"], {"true": 1, "false": 1})
        self.assertEqual(result["logs_with_failed_devices_count"], 1)
        self.assertTrue(result["coverage_complete"])
        for secret in ("private-id", "private-site", "user", "1.0", "2.0", "2026-01-01"):
            self.assertNotIn(secret, str(result))

    def test_marks_unknown_and_missing_fields_partial(self):
        result = summarize_upgrade_log_page(
            {"totalRows": 1, "currentPage": 1, "currentSize": 1}, [{"future": "private"}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["rollbacked_missing_count"], 1)
        self.assertEqual(result["failed_device_count_missing"], 1)
        self.assertNotIn("private", str(result))

    def test_rejects_bad_page_envelopes(self):
        for response, rows in (
            ({"totalRows": 1, "currentPage": 2, "currentSize": 1}, [{}]),
            ({"totalRows": 0, "currentPage": 1, "currentSize": 0}, [{}]),
            ({"totalRows": 101, "currentPage": 1, "currentSize": 101}, [{}] * 101),
        ):
            with self.assertRaises(ControllerUpgradeLogSummaryError):
                summarize_upgrade_log_page(response, rows)


if __name__ == "__main__":
    unittest.main()
