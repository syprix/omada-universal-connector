import unittest

from app.site_device_memory_summary import (
    SiteDeviceMemorySummaryError, project_site_device_memory_summary,
)


class SiteDeviceMemorySummaryTests(unittest.TestCase):
    def test_projects_memory_percentages_without_device_identifiers(self):
        result = project_site_device_memory_summary([
            {"name": "private-device", "mac": "private-mac", "memUsage": 46,
             "model": "private-model"},
            {"type": "ap", "memUsage": 90},
        ])
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"], {
            "device_count": 2, "maximum_memory_usage_percent": 90,
            "average_memory_usage_percent": 68.0,
        })
        for value in ("private-device", "private-mac", "private-model"):
            self.assertNotIn(value, repr(result))

    def test_flags_missing_invalid_and_unknown_data_and_enforces_bound(self):
        result = project_site_device_memory_summary([
            {"memUsage": 101, "future": "hidden"}, {"name": "hidden"},
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["missing_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("hidden", repr(result))
        with self.assertRaises(SiteDeviceMemorySummaryError):
            project_site_device_memory_summary([{}] * 101)
        with self.assertRaises(SiteDeviceMemorySummaryError):
            project_site_device_memory_summary({"rows": []})


if __name__ == "__main__":
    unittest.main()
