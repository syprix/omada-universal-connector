import unittest

from app.site_switch_dashboard_summary import (
    SiteSwitchDashboardSummaryError, project_site_switch_dashboard_summary,
)


class SiteSwitchDashboardSummaryTests(unittest.TestCase):
    def test_projects_wired_network_totals(self):
        result = project_site_switch_dashboard_summary({
            "clients": 12, "portUtilization": 43, "connectedSwitchNum": 3,
            "totalTraffic": 2**40,
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"], {
            "wired_client_count": 12, "port_occupancy_value": 43,
            "connected_switch_count": 3, "total_traffic_bytes": 2**40,
        })

    def test_flags_missing_invalid_and_unknown_values(self):
        result = project_site_switch_dashboard_summary({
            "clients": -1, "connectedSwitchNum": True, "future": "private",
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["missing_field_count"], 2)
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))
        with self.assertRaises(SiteSwitchDashboardSummaryError):
            project_site_switch_dashboard_summary([])
        with self.assertRaises(SiteSwitchDashboardSummaryError):
            project_site_switch_dashboard_summary({f"x{i}": i for i in range(9)})


if __name__ == "__main__":
    unittest.main()
