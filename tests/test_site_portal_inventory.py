"""Synthetic redaction and bounds tests for site_portal_inventory_coverage."""
import unittest

from app.site_portal_inventory import (
    SitePortalInventoryError, summarize_site_portal_inventory,
)


class SitePortalInventoryCoverageTests(unittest.TestCase):
    def test_valid_empty_array_is_distinct(self):
        result = summarize_site_portal_inventory([])
        self.assertEqual(result["data"], {
            "portal_count": 0,
            "empty": True,
            "activation_coverage": {
                "true_count": 0, "false_count": 0, "missing_count": 0,
                "invalid_count": 0, "uninspected_portal_count": 0,
            },
            "ssid_list_coverage": {
                "present_count": 0, "missing_count": 0, "invalid_count": 0,
                "empty_count": 0, "entry_count": 0,
                "uninspected_portal_count": 0,
            },
            "network_list_coverage": {
                "present_count": 0, "missing_count": 0, "invalid_count": 0,
                "empty_count": 0, "entry_count": 0,
                "uninspected_portal_count": 0,
            },
            "unreadable_portal_count": 0,
            "truncation_status": "not_reported_by_contract",
        })
        self.assertFalse(result["partial"])

    def test_reports_only_activation_and_list_coverage_counts(self):
        result = summarize_site_portal_inventory([
            {"id": "PORTAL-ID-PRIVATE", "name": "PORTAL-NAME-PRIVATE",
             "enable": True, "ssidList": ["SSID-ID-PRIVATE"], "networkList": [],
             "authType": 17, "radius": "RADIUS-PRIVATE", "url": "URL-PRIVATE"},
            {"enable": False, "networkList": ["NETWORK-ID-PRIVATE"]},
            {"ssidList": []},
            {"enable": 1, "ssidList": ["SSID-ID-PRIVATE", 3], "networkList": None},
            "unreadable-row",
        ])
        data = result["data"]
        self.assertEqual(data["portal_count"], 5)
        self.assertFalse(data["empty"])
        self.assertEqual(data["activation_coverage"], {
            "true_count": 1, "false_count": 1, "missing_count": 1,
            "invalid_count": 1, "uninspected_portal_count": 1,
        })
        self.assertEqual(data["ssid_list_coverage"], {
            "present_count": 2, "missing_count": 1, "invalid_count": 1,
            "empty_count": 1, "entry_count": 1,
            "uninspected_portal_count": 1,
        })
        self.assertEqual(data["network_list_coverage"], {
            "present_count": 2, "missing_count": 1, "invalid_count": 1,
            "empty_count": 1, "entry_count": 1,
            "uninspected_portal_count": 1,
        })
        self.assertEqual(data["unreadable_portal_count"], 1)
        self.assertTrue(result["partial"])
        for private in ("PORTAL-ID-PRIVATE", "PORTAL-NAME-PRIVATE", "SSID-ID-PRIVATE",
                        "NETWORK-ID-PRIVATE", "RADIUS-PRIVATE", "URL-PRIVATE"):
            self.assertNotIn(private, repr(result))

    def test_malformed_and_over_bound_results_fail_closed(self):
        for value in (None, {}, "[]", [None] * 257):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(SitePortalInventoryError):
                    summarize_site_portal_inventory(value)
        with self.assertRaises(SitePortalInventoryError):
            summarize_site_portal_inventory([{"field_%d" % i: True for i in range(65)}])
        with self.assertRaises(SitePortalInventoryError):
            summarize_site_portal_inventory([{"ssidList": ["x"] * 257}])


if __name__ == "__main__":
    unittest.main()
