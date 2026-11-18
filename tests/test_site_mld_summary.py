import unittest

from app.site_mld_summary import SiteMldSummaryError, summarize_site_mld


class SiteMldSummaryTests(unittest.TestCase):
    def test_projects_mld_without_wan_id_or_feature_text(self):
        result = summarize_site_mld({"enable": True, "version": 2,
                                     "wanPortId": "private-wan-id",
                                     "featureDescription": [{"feature": "secret-feature",
                                                            "description": "private text",
                                                            "support": True}]})
        self.assertEqual(result["data"], {"enabled": True, "version": 2,
                         "wan_port_configured": True, "feature_description_count": 1})
        self.assertFalse(result["partial"])
        for value in ("private-wan-id", "secret-feature", "private text"):
            self.assertNotIn(value, repr(result))

    def test_invalid_version_and_unknown_data_mark_partial(self):
        result = summarize_site_mld({"enable": False, "version": 3, "wanPortId": "",
                                     "featureDescription": [], "future": "discard"})
        self.assertTrue(result["partial"])
        self.assertIsNone(result["data"]["version"])
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("discard", repr(result))

    def test_non_object_response_rejected(self):
        with self.assertRaises(SiteMldSummaryError):
            summarize_site_mld([])


if __name__ == "__main__":
    unittest.main()
