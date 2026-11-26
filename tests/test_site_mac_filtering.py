"""Synthetic projection tests for site_mac_filtering_general_state."""

import unittest

from app.site_mac_filtering import (
    SiteMacFilteringError, project_site_mac_filtering_general_state,
)


class SiteMacFilteringProjectionTests(unittest.TestCase):
    def test_site_mac_filtering_general_state_projects_fields_without_selector_values(self):
        result = project_site_mac_filtering_general_state({
            "enable": False,
            "filterMode": 0,
            "direction": {
                "lanToWan": True,
                "lanToLan": False,
                "wanInIds": ["wan-private"],
                "vpnInIds": [],
            },
        })
        self.assertEqual(result, {
            "data": {
                "direction_present": True,
                "enabled": False,
                "filter_mode": "allow",
                "direction": {
                    "lan_to_wan": True,
                    "lan_to_lan": False,
                    "wan_selector_count": 1,
                    "vpn_selector_count": 0,
                },
            },
            "missing_field_count": 0,
            "invalid_field_count": 0,
            "unknown_field_count": 0,
            "direction_invalid_field_count": 0,
            "direction_unknown_field_count": 0,
            "partial": False,
        })
        self.assertNotIn("wan-private", repr(result))

    def test_site_mac_filtering_general_state_preserves_absent_optional_fields(self):
        result = project_site_mac_filtering_general_state({"enable": True})
        self.assertEqual(result["data"], {
            "direction_present": False, "enabled": True,
        })
        self.assertEqual(result["missing_field_count"], 0)
        self.assertFalse(result["partial"])

    def test_site_mac_filtering_general_state_marks_missing_and_invalid_values(self):
        missing = project_site_mac_filtering_general_state({})
        self.assertEqual(missing["missing_field_count"], 1)
        self.assertTrue(missing["partial"])
        invalid = project_site_mac_filtering_general_state({
            "enable": 1, "filterMode": True,
            "direction": {"lanToWan": 0, "wanInIds": [1]},
        })
        self.assertEqual(invalid["invalid_field_count"], 4)
        self.assertEqual(invalid["direction_invalid_field_count"], 2)
        self.assertTrue(invalid["partial"])
        self.assertNotIn("1", repr(invalid["data"].get("direction", {})))

    def test_site_mac_filtering_general_state_counts_unknown_fields_redacted(self):
        result = project_site_mac_filtering_general_state({
            "enable": False,
            "privateFuture": "secret-value",
            "direction": {"lanToLan": True, "privateSelector": "secret-id"},
        })
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertEqual(result["direction_unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("secret-value", repr(result))
        self.assertNotIn("secret-id", repr(result))

    def test_site_mac_filtering_general_state_rejects_invalid_or_oversized_data(self):
        with self.assertRaises(SiteMacFilteringError):
            project_site_mac_filtering_general_state([])
        with self.assertRaises(SiteMacFilteringError):
            project_site_mac_filtering_general_state({str(i): True for i in range(17)})
        with self.assertRaises(SiteMacFilteringError):
            project_site_mac_filtering_general_state({
                "enable": True, "direction": {"wanInIds": ["x"] * 257},
            })


if __name__ == "__main__":
    unittest.main()
