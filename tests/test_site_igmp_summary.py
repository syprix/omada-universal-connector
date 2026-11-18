import unittest

from app.site_igmp_summary import SiteIgmpSummaryError, summarize_site_igmp


class SiteIgmpSummaryTests(unittest.TestCase):
    def test_projects_version_and_wan_presence_without_identifiers(self):
        result = summarize_site_igmp({
            "enable": True, "version": 3, "wanPortId": "private-wan",
            "virtualWanId": "private-virtual-wan",
            "featureDescription": [{"feature": "private-feature",
                                    "description": "private text", "support": True}],
        })
        self.assertEqual(result["data"], {"enabled": True, "version": 3,
                         "wan_port_configured": True, "virtual_wan_configured": True,
                         "feature_description_count": 1})
        self.assertFalse(result["partial"])
        for value in ("private-wan", "private-virtual-wan", "private-feature", "private text"):
            self.assertNotIn(value, repr(result))

    def test_optional_fields_may_be_absent(self):
        result = summarize_site_igmp({"enable": False, "version": 2})
        self.assertFalse(result["partial"])
        self.assertIsNone(result["data"]["wan_port_configured"])
        self.assertIsNone(result["data"]["feature_description_count"])

    def test_invalid_required_and_unknown_fields_mark_partial(self):
        result = summarize_site_igmp({"enable": 1, "version": 4, "future": "discard"})
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("discard", repr(result))

    def test_non_object_response_rejected(self):
        with self.assertRaises(SiteIgmpSummaryError):
            summarize_site_igmp([])


if __name__ == "__main__":
    unittest.main()
