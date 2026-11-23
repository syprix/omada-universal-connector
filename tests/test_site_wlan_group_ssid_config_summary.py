import unittest

from app.site_wlan_group_ssid_config_summary import (
    SiteWlanGroupSsidConfigError, project_site_wlan_group_ssid_config,
)


class SiteWlanGroupSsidConfigSummaryTests(unittest.TestCase):
    def test_projects_documented_status_band_and_device_type_without_names(self):
        result = project_site_wlan_group_ssid_config({
            "ssidEnable": True, "band": 5, "deviceType": 3,
            "name": "private SSID", "pskSetting": {"securityKey": "secret"},
        })
        self.assertEqual(result["ssid_enabled"], True)
        self.assertEqual(result["band_enabled"],
                         {"2.4ghz": True, "5ghz": False, "6ghz": True})
        self.assertEqual(result["device_type_enabled"], {"eap": True, "gateway": True})
        self.assertNotIn("private SSID", repr(result))
        self.assertNotIn("secret", repr(result))

    def test_missing_fields_are_unknown_and_unusual_device_bits_mark_partial(self):
        partial = project_site_wlan_group_ssid_config({"deviceType": 9})
        self.assertTrue(partial["partial"])
        self.assertEqual(partial["missing_field_count"], 2)
        self.assertTrue(partial["device_type_unknown_bits_present"])

    def test_invalid_documented_values_are_rejected(self):
        for item in ({"ssidEnable": 1}, {"band": 8}, {"deviceType": -1}):
            with self.subTest(item=item), self.assertRaises(SiteWlanGroupSsidConfigError):
                project_site_wlan_group_ssid_config(item)


if __name__ == "__main__":
    unittest.main()
