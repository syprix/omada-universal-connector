import unittest
from app.site_upnp_template_comparison import compare_site_and_template_upnp


class SiteUpnpTemplateComparisonTests(unittest.TestCase):
    def test_compares_only_common_projected_fields(self):
        site = {"data": {"enabled": True, "wan_port_count": 2, "network_count": 1,
                         "supports_ds_lite_or_map_e": False}, "partial": False}
        template = {"data": {"enabled": True, "wan_port_count": 1, "network_count": 1,
                             "supports_ds_lite_or_map_e": None}, "partial": True}
        result = compare_site_and_template_upnp(site, template)
        self.assertEqual(result["by_field"], {"enabled": "same", "wan_port_count": "different",
                                              "network_count": "same",
                                              "supports_ds_lite_or_map_e": "unknown"})
        self.assertEqual((result["same_count"], result["different_count"], result["unknown_count"]),
                         (2, 1, 1))
        self.assertTrue(result["partial"])
        self.assertIn("assignment is not inferred", result["selection"])

    def test_invalid_projection_is_rejected(self):
        with self.assertRaises(ValueError):
            compare_site_and_template_upnp({}, {"data": {}})


if __name__ == "__main__":
    unittest.main()
