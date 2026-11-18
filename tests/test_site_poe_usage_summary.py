import unittest

from app.site_poe_usage_summary import (
    SitePoeUsageSummaryError, project_site_poe_usage_summary,
)


class SitePoeUsageSummaryTests(unittest.TestCase):
    def test_aggregates_power_and_port_counts_without_device_identity(self):
        result = project_site_poe_usage_summary([
            {"mac": "aa:bb:cc:dd:ee:ff", "name": "Private switch", "portNum": 24,
             "totalPowerUsed": 80, "totalPower": 370},
            {"mac": "11:22:33:44:55:66", "portNum": 8,
             "totalPowerUsed": 12, "totalPower": 120},
        ])
        self.assertEqual(result["data"], {
            "switch_count": 2, "reported_port_count": 32,
            "total_power_used_watts": 92, "rated_poe_capacity_watts": 490,
            "switches_with_power_usage_count": 2, "switches_with_capacity_count": 2,
        })
        self.assertFalse(result["partial"])
        self.assertNotIn("Private switch", repr(result))
        self.assertNotIn("aa:bb:cc:dd:ee:ff", repr(result))

    def test_counts_invalid_and_unknown_fields(self):
        result = project_site_poe_usage_summary([
            {"totalPowerUsed": True, "totalPower": -1, "portNum": "bad",
             "unknown": "hidden"},
        ])
        self.assertEqual(result["invalid_field_count"], 3)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("hidden", repr(result))
        with self.assertRaises(SitePoeUsageSummaryError):
            project_site_poe_usage_summary([{}] * 501)


if __name__ == "__main__":
    unittest.main()
