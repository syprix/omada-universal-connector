import unittest

from app.site_ids_ips_config_summary import summarize_site_ids_ips_config


class SiteIdsIpsConfigSummaryTests(unittest.TestCase):
    def test_projects_documented_configuration_and_omits_raw_values(self):
        result = summarize_site_ids_ips_config({
            "enable": True, "ipsMode": 1, "geoEnable": False,
            "dpLevel": 3, "customCategories": [1, 8, 24],
            "timeRangeId": "private-schedule",
        })
        self.assertIs(result["enable"], True)
        self.assertEqual(result["ips_mode"], 1)
        self.assertEqual(result["dp_level"], 3)
        self.assertIs(result["geo_enable"], False)
        self.assertEqual(result["custom_category_count"], 3)
        self.assertTrue(result["configuration_only"])
        self.assertNotIn("private-schedule", repr(result))
        self.assertNotIn("1, 8, 24", repr(result))

    def test_unknown_values_and_missing_fields_are_distinct(self):
        result = summarize_site_ids_ips_config({
            "enable": "true", "ipsMode": 8, "geoEnable": None,
            "dpLevel": 0, "customCategories": "1,2",
        })
        self.assertIsNone(result["enable"])
        self.assertIsNone(result["ips_mode"])
        self.assertIn("enable", result["unknown_fields"])
        self.assertIn("ipsMode", result["unknown_fields"])
        self.assertIn("geoEnable", result["unknown_fields"])
        self.assertIn("customCategories", result["unknown_fields"])
        self.assertEqual(result["dp_level"], 0)

    def test_absent_fields_are_reported_separately(self):
        result = summarize_site_ids_ips_config({})
        self.assertEqual(result["missing_fields"], [
            "enable", "ipsMode", "dpLevel", "geoEnable", "customCategories",
        ])
        self.assertIsNone(result["custom_category_count"])

    def test_invalid_container_is_rejected(self):
        with self.assertRaises(ValueError):
            summarize_site_ids_ips_config([{"enable": True}])

    def test_undocumented_category_code_is_unknown(self):
        result = summarize_site_ids_ips_config({"customCategories": [99]})
        self.assertIsNone(result["custom_category_count"])
        self.assertEqual(result["unknown_fields"], ["customCategories"])


if __name__ == "__main__":
    unittest.main()
