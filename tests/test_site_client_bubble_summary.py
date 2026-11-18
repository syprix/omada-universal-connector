import unittest

from app.site_client_bubble_summary import (
    SiteClientBubbleSummaryError, project_site_client_bubble_summary,
)


class SiteClientBubbleSummaryTests(unittest.TestCase):
    def test_aggregates_traffic_and_radio_metrics_without_identity(self):
        result = project_site_client_bubble_summary([
            {"name": "hidden-one", "type": "phone", "mac": "02:00:00:00:00:01",
             "apName": "private-ap", "traffic": 90, "upload": 30, "download": 60,
             "rssi": -50, "snr": 40, "healthScore": 90},
            {"name": "hidden-two", "type": "laptop", "mac": "02:00:00:00:00:02",
             "apName": "private-ap", "traffic": 40, "upload": 10, "download": 30,
             "rssi": -70, "snr": 20, "healthScore": 70},
        ])
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["client_count"], 2)
        self.assertEqual(result["data"]["total_client_traffic_value"], 130)
        self.assertEqual(result["data"]["total_client_upload_value"], 40)
        self.assertEqual(result["data"]["total_client_download_value"], 90)
        self.assertEqual(result["data"]["average_client_rssi_value"], -60)
        self.assertEqual(result["data"]["minimum_client_rssi_value"], -70)
        self.assertEqual(result["data"]["maximum_client_rssi_value"], -50)
        self.assertEqual(result["data"]["average_client_snr_value"], 30)
        self.assertEqual(result["data"]["average_client_health_score_value"], 80)
        for value in ("hidden-one", "02:00:00:00:00:01", "private-ap"):
            self.assertNotIn(value, repr(result))

    def test_marks_missing_invalid_unknown_and_malformed_rows_partial(self):
        result = project_site_client_bubble_summary([
            {"traffic": -1, "upload": 2, "download": 3, "rssi": "bad",
             "healthScore": 1, "future": "omitted"},
            "invalid-row",
        ])
        self.assertTrue(result["partial"])
        self.assertGreater(result["data"]["missing_field_count"], 0)
        self.assertEqual(result["data"]["invalid_field_count"], 2)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertIsNone(result["data"]["total_client_traffic_value"])
        self.assertNotIn("omitted", repr(result))

    def test_rejects_non_list_and_overlarge_response(self):
        with self.assertRaises(SiteClientBubbleSummaryError):
            project_site_client_bubble_summary({"result": []})
        with self.assertRaises(SiteClientBubbleSummaryError):
            project_site_client_bubble_summary([{}] * 1_001)

    def test_rejects_values_outside_declared_integer_formats(self):
        result = project_site_client_bubble_summary([
            {"traffic": (1 << 63), "upload": 1, "download": 1,
             "rssi": (1 << 31), "snr": 1, "healthScore": 1}
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["invalid_field_count"], 2)
        self.assertIsNone(result["data"]["total_client_traffic_value"])
        self.assertIsNone(result["data"]["maximum_client_rssi_value"])


if __name__ == "__main__":
    unittest.main()
