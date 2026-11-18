import unittest

from app.site_device_traffic_summary import (
    SiteDeviceTrafficSummaryError, project_site_device_traffic_summary,
)


class SiteDeviceTrafficSummaryTests(unittest.TestCase):
    def test_aggregates_documented_traffic_and_omits_device_details(self):
        result = project_site_device_traffic_summary({
            "aps": [{"name": "private-ap", "mac": "private-id", "traffic": 12.5}],
            "switches": [{"name": "private-switch", "traffic": 2.25}],
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["access_point_row_count"], 1)
        self.assertEqual(result["data"]["ap_traffic_mb"], 12.5)
        self.assertEqual(result["data"]["switch_traffic_mb"], 2.25)
        self.assertNotIn("private-ap", repr(result))
        self.assertNotIn("private-id", repr(result))

    def test_invalid_rows_and_unknown_fields_are_counted(self):
        result = project_site_device_traffic_summary({
            "aps": [{"traffic": True}], "switches": [{"traffic": 1, "extra": "hidden"}],
        })
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("hidden", repr(result))
        with self.assertRaises(SiteDeviceTrafficSummaryError):
            project_site_device_traffic_summary({"aps": [{}] * 1001, "switches": []})


if __name__ == "__main__":
    unittest.main()
