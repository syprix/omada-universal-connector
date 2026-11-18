import unittest

from app.site_cpu_usage_summary import (
    SiteCpuUsageSummaryError, project_site_cpu_usage_summary,
)


class SiteCpuUsageSummaryTests(unittest.TestCase):
    def test_aggregates_cpu_values_without_device_identity(self):
        result = project_site_cpu_usage_summary([
            {"name": "hidden-one", "mac": "02:00:00:00:00:01", "cpuUtil": 70,
             "model": "hidden-model", "modelVersion": "secret-version", "type": "AP"},
            {"name": "hidden-two", "mac": "02:00:00:00:00:02", "cpuUtil": 30,
             "model": "hidden-model", "modelVersion": "secret-version", "type": "switch"},
        ])
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["device_count"], 2)
        self.assertEqual(result["data"]["mean_cpu_util_value"], 50)
        self.assertEqual(result["data"]["minimum_cpu_util_value"], 30)
        self.assertEqual(result["data"]["maximum_cpu_util_value"], 70)
        for value in ("hidden-one", "02:00:00:00:00:01", "hidden-model", "secret-version"):
            self.assertNotIn(value, repr(result))

    def test_marks_missing_invalid_unknown_and_malformed_rows_partial(self):
        result = project_site_cpu_usage_summary([
            {"name": "hidden", "cpuUtil": -1},
            {"future": "omitted"},
            "bad-row",
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["missing_field_count"], 1)
        self.assertEqual(result["data"]["invalid_field_count"], 2)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertIsNone(result["data"]["maximum_cpu_util_value"])
        self.assertNotIn("omitted", repr(result))

    def test_rejects_non_list_and_more_than_five_rows(self):
        with self.assertRaises(SiteCpuUsageSummaryError):
            project_site_cpu_usage_summary({"result": []})
        with self.assertRaises(SiteCpuUsageSummaryError):
            project_site_cpu_usage_summary([{"cpuUtil": 1}] * 6)


if __name__ == "__main__":
    unittest.main()
