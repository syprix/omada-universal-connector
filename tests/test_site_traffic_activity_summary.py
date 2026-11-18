import unittest

from app.site_traffic_activity_summary import (
    SiteTrafficActivitySummaryError, project_site_traffic_activity_summary,
)


class SiteTrafficActivitySummaryTests(unittest.TestCase):
    def test_summarizes_ap_and_switch_samples(self):
        result = project_site_traffic_activity_summary({
            "apTrafficActivities": [
                {"time": 100, "txData": 2.0, "rxData": 8.0},
                {"time": 200, "txData": 6.0, "rxData": 10.0},
            ],
            "switchTrafficActivities": [
                {"time": 150, "txData": 1.0, "rxData": 3.0},
            ],
        })
        self.assertFalse(result["partial"])
        ap = result["data"]["access_point_traffic"]
        self.assertEqual(ap["sample_count"], 2)
        self.assertEqual(ap["mean_uplink_sample_mb_value"], 4)
        self.assertEqual(ap["peak_downlink_sample_mb_value"], 10)
        self.assertEqual(ap["earliest_sample_unix_seconds"], 100)
        self.assertEqual(ap["latest_sample_unix_seconds"], 200)
        self.assertEqual(result["data"]["switch_traffic"]["sample_count"], 1)

    def test_marks_missing_invalid_and_unknown_fields_partial(self):
        result = project_site_traffic_activity_summary({
            "apTrafficActivities": [{"time": 100, "txData": {"value": 2},
                                     "future": "omitted"}],
            "switchTrafficActivities": [],
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["invalid_field_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertGreater(result["data"]["missing_field_count"], 0)
        self.assertIsNone(result["data"]["access_point_traffic"]
                          ["mean_uplink_sample_mb_value"])
        self.assertNotIn("omitted", repr(result))

    def test_rejects_malformed_and_oversized_lists(self):
        with self.assertRaises(SiteTrafficActivitySummaryError):
            project_site_traffic_activity_summary({"apTrafficActivities": None,
                                                   "switchTrafficActivities": []})
        with self.assertRaises(SiteTrafficActivitySummaryError):
            project_site_traffic_activity_summary({
                "apTrafficActivities": [{"time": 1, "txData": 1, "rxData": 1}] * 2_001,
                "switchTrafficActivities": [],
            })


if __name__ == "__main__":
    unittest.main()
