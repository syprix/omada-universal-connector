import unittest

from app.site_isp_load_summary import (
    SiteIspLoadSummaryError, project_site_isp_load_summary,
)


class SiteIspLoadSummaryTests(unittest.TestCase):
    def test_aggregates_wan_rate_and_latency_without_port_names(self):
        result = project_site_isp_load_summary([
            {"portId": 1, "portName": "private-wan-a", "data": [
                {"time": 100, "totalRate": 300, "latency": 40},
                {"time": 200, "totalRate": 500, "latency": 20},
            ]},
            {"portId": 2, "portName": "private-wan-b", "data": [
                {"time": 150, "totalRate": 100, "latency": 60},
            ]},
        ])
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["port_count"], 2)
        self.assertEqual(result["data"]["sample_count"], 3)
        self.assertEqual(result["data"]["mean_total_rate_value"], 300)
        self.assertEqual(result["data"]["peak_total_rate_value"], 500)
        self.assertEqual(result["data"]["mean_latency_ms"], 40)
        self.assertEqual(result["data"]["minimum_latency_ms"], 20)
        self.assertEqual(result["data"]["maximum_latency_ms"], 60)
        self.assertEqual(result["data"]["earliest_sample_unix_seconds"], 100)
        self.assertNotIn("private-wan", repr(result))

    def test_marks_missing_invalid_and_unknown_fields_partial(self):
        result = project_site_isp_load_summary([
            {"portName": "hidden", "data": [{"time": 1, "totalRate": -2,
                                                "latency": 1001, "future": "omitted"}]}
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["missing_field_count"], 0)
        self.assertEqual(result["data"]["invalid_field_count"], 2)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertIsNone(result["data"]["mean_latency_ms"])
        self.assertNotIn("omitted", repr(result))

    def test_rejects_malformed_and_oversized_responses(self):
        with self.assertRaises(SiteIspLoadSummaryError):
            project_site_isp_load_summary({"data": []})
        with self.assertRaises(SiteIspLoadSummaryError):
            project_site_isp_load_summary([{"data": []}] * 65)
        with self.assertRaises(SiteIspLoadSummaryError):
            project_site_isp_load_summary([{"data": [{"time": 1,
                                                         "totalRate": 1,
                                                         "latency": 1}] * 5_001}])


if __name__ == "__main__":
    unittest.main()
