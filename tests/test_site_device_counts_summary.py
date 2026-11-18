import unittest

from app.site_device_counts_summary import (
    SiteDeviceCountsSummaryError, project_site_device_counts_summary,
)


class SiteDeviceCountsSummaryTests(unittest.TestCase):
    def test_sums_documented_category_counts_without_returning_type_names(self):
        result = project_site_device_counts_summary([
            {"type": "access point", "total": 12, "preConfig": 1,
             "connected": 10, "disconnectedCount": 1},
            {"type": "switch", "total": 3, "preConfig": 0,
             "connected": 3, "disconnectedCount": 0},
        ])
        self.assertEqual(result["data"]["device_category_count"], 2)
        self.assertEqual(result["data"]["total_device_count"], 15)
        self.assertEqual(result["data"]["connected_device_count"], 13)
        self.assertEqual(result["data"]["preconfigured_device_count"], 1)
        self.assertFalse(result["partial"])
        self.assertNotIn("access point", repr(result))
        self.assertNotIn("switch", repr(result))

    def test_counts_missing_invalid_and_unknown_fields(self):
        result = project_site_device_counts_summary([
            {"total": -1, "connected": True, "unknown": "hidden"},
        ])
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["missing_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("hidden", repr(result))
        with self.assertRaises(SiteDeviceCountsSummaryError):
            project_site_device_counts_summary([{}] * 101)


if __name__ == "__main__":
    unittest.main()
