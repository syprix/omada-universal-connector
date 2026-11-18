import unittest

from app.site_active_device_summary import (
    SiteActiveDeviceSummaryError, project_site_active_device_summary,
)


class SiteActiveDeviceSummaryTests(unittest.TestCase):
    def test_projects_traffic_and_status_without_device_identifiers(self):
        result = project_site_active_device_summary([
            {"status": 0, "name": "private-ap", "mac": "private-mac", "traffic": 1.5},
            {"status": 1, "model": "private-switch", "traffic": 2},
        ])
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"], {
            "device_count": 2, "connected_device_count": 1,
            "disconnected_device_count": 1, "total_traffic_value": 3.5,
            "maximum_device_traffic_value": 2.0,
        })
        for value in ("private-ap", "private-mac", "private-switch"):
            self.assertNotIn(value, repr(result))

    def test_marks_overflowed_total_partial(self):
        result = project_site_active_device_summary([
            {"status": 0, "traffic": 1e308},
            {"status": 0, "traffic": 1e308},
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertNotIn("total_traffic_value", result["data"])
        self.assertEqual(result["data"]["maximum_device_traffic_value"], 1e308)

    def test_flags_missing_invalid_and_unknown_data_and_enforces_bound(self):
        result = project_site_active_device_summary([
            {"status": 4, "traffic": -1, "future": "private"},
            {"status": 0},
            {"status": 0, "traffic": 10 ** 1000},
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 3)
        self.assertEqual(result["missing_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))
        with self.assertRaises(SiteActiveDeviceSummaryError):
            project_site_active_device_summary([{}] * 101)
        with self.assertRaises(SiteActiveDeviceSummaryError):
            project_site_active_device_summary({"devices": []})


if __name__ == "__main__":
    unittest.main()
