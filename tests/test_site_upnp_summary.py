import unittest

from app.site_upnp_summary import SiteUpnpSummaryError, summarize_site_upnp


class SiteUpnpSummaryTests(unittest.TestCase):
    def test_projects_only_flags_and_counts(self):
        source = {"enable": True, "wanPortIds": ["wan-secret"],
                  "networkIds": ["network-secret", "another-secret"],
                  "supportByDsLiteAndMapE": False}
        result = summarize_site_upnp(source)
        self.assertEqual(result["data"], {"enabled": True, "wan_port_count": 1,
                         "network_count": 2, "supports_ds_lite_or_map_e": False})
        self.assertFalse(result["partial"])
        rendered = repr(result)
        self.assertNotIn("wan-secret", rendered)
        self.assertNotIn("network-secret", rendered)

    def test_partial_for_missing_invalid_and_unknown(self):
        result = summarize_site_upnp({"enable": "yes", "wanPortIds": ["id"],
                                      "extra": "private"})
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["enabled"], None)
        self.assertEqual(result["data"]["network_count"], None)
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertGreater(result["missing_field_count"], 0)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_rejects_non_object_and_marks_malformed_collections_partial(self):
        for raw in (None, []):
            with self.subTest(raw=raw), self.assertRaises(SiteUpnpSummaryError):
                summarize_site_upnp(raw)
        for raw in ({"enable": True, "wanPortIds": [""]},
                    {"enable": True, "networkIds": ["x"] * 257}):
            with self.subTest(raw=raw):
                result = summarize_site_upnp(raw)
                self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
