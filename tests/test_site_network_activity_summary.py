import unittest

from app.site_network_activity_summary import (
    SiteNetworkActivitySummaryError, project_site_network_activity_summary,
)


class SiteNetworkActivitySummaryTests(unittest.TestCase):
    def test_projects_only_documented_aggregate_fields(self):
        result = project_site_network_activity_summary({
            "totalTraffic": 3000, "totalUpload": 1000, "totalDownload": 2000,
            "totalWiredCount": 2, "totalWirelessCount": 3, "totalClientCount": 5,
            "existData": True, "activityList": [{"clientName": "private"}],
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["total_traffic"], 3000)
        self.assertEqual(result["data"]["total_client_count"], 5)
        self.assertNotIn("private", repr(result))
        self.assertNotIn("activityList", repr(result))

    def test_counts_invalid_missing_and_unknown_fields_without_echoing_them(self):
        result = project_site_network_activity_summary({
            "totalTraffic": True, "existData": 1, "private": "secret",
        })
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["missing_field_count"], 5)
        self.assertNotIn("secret", repr(result))
        with self.assertRaises(SiteNetworkActivitySummaryError):
            project_site_network_activity_summary({str(i): i for i in range(13)})


if __name__ == "__main__":
    unittest.main()
