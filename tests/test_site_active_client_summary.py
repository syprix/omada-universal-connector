import unittest

from app.site_active_client_summary import (
    SiteActiveClientSummaryError, project_site_active_client_summary,
)


class SiteActiveClientSummaryTests(unittest.TestCase):
    def test_projects_counts_and_traffic_without_client_identity(self):
        result = project_site_active_client_summary([
            {"name": "hidden-one", "wireless": True, "type": "phone",
             "model": "hidden-model", "mac": "02:00:00:00:00:01", "totalTraffic": 90},
            {"name": "hidden-two", "wireless": False, "type": "laptop",
             "model": "hidden-model", "mac": "02:00:00:00:00:02", "totalTraffic": 40},
        ])
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["client_count"], 2)
        self.assertEqual(result["data"]["wireless_client_count"], 1)
        self.assertEqual(result["data"]["wired_client_count"], 1)
        self.assertEqual(result["data"]["total_client_traffic_value"], 130)
        self.assertEqual(result["data"]["maximum_client_traffic_value"], 90)
        for value in ("hidden-one", "hidden-two", "hidden-model", "02:00:00:00:00:01"):
            self.assertNotIn(value, repr(result))

    def test_marks_missing_invalid_and_unknown_fields_partial(self):
        result = project_site_active_client_summary([
            {"wireless": "yes", "totalTraffic": -1},
            {"wireless": True, "future": "omitted"},
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["missing_field_count"], 1)
        self.assertEqual(result["data"]["invalid_field_count"], 2)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("omitted", repr(result))

    def test_rejects_malformed_or_overlarge_result(self):
        with self.assertRaises(SiteActiveClientSummaryError):
            project_site_active_client_summary({"data": []})
        with self.assertRaises(SiteActiveClientSummaryError):
            project_site_active_client_summary([{}] * 1_001)

    def test_marks_aggregates_incomplete_for_malformed_rows(self):
        result = project_site_active_client_summary([
            {"wireless": True, "totalTraffic": 10}, "invalid-row"
        ])
        self.assertTrue(result["partial"])
        self.assertIsNone(result["data"]["wireless_client_count"])
        self.assertIsNone(result["data"]["total_client_traffic_value"])


if __name__ == "__main__":
    unittest.main()
