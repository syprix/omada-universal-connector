import unittest

from app.site_iptv_summary import SiteIptvSummaryError, summarize_site_iptv


class SiteIptvSummaryTests(unittest.TestCase):
    def test_counts_port_types_and_redacts_network_configuration(self):
        raw = {"enable": True, "wanPortId": "private-wan", "mode": 1,
               "customConfig": {"ipPhoneVlanId": 20, "ipPhoneVlanPriority": 3,
                                "iptvVlanId": 30, "iptvVlanPriority": 4},
               "portConfig": [{"portId": "port-secret", "name": "Living room", "type": 2},
                              {"portId": "port-two", "type": 3}],
               "dslConfig": {"modulationType": 1, "ipPhoneVpi": 2, "ipPhoneVci": 100},
               "featureDescription": [{"feature": "private-label", "description": "internal"}]}
        result = summarize_site_iptv(raw)
        self.assertEqual(result["data"]["mode"], "custom")
        self.assertEqual(result["data"]["port_type_counts"],
                         {"internet": 0, "iptv": 1, "ip_phone": 1})
        self.assertEqual(result["data"]["port_count"], 2)
        self.assertFalse(result["partial"])
        for secret in ("private-wan", "port-secret", "Living room", "20", "30",
                       "private-label", "internal", "100"):
            self.assertNotIn(secret, repr(result))

    def test_invalid_fields_and_unknown_types_mark_partial(self):
        result = summarize_site_iptv({"enable": True, "wanPortId": "", "mode": 9,
                                      "portConfig": [{"portId": "x", "type": 99}],
                                      "dslConfig": {"modulationType": 4}})
        self.assertTrue(result["partial"])
        self.assertIsNone(result["data"]["mode"])
        self.assertEqual(result["unknown_port_type_count"], 1)
        self.assertEqual(result["invalid_field_count"], 2)

    def test_required_custom_vlan_fields_are_checked_without_exposure(self):
        result = summarize_site_iptv({
            "enable": True, "mode": 1, "wanPortId": "secret-wan",
            "portConfig": [], "customConfig": {"iptvVlanId": 4000},
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["missing_field_count"], 3)
        self.assertTrue(result["data"]["custom_vlan_configured"])
        self.assertNotIn("4000", repr(result))
        self.assertNotIn("secret-wan", repr(result))

    def test_non_object_response_rejected(self):
        with self.assertRaises(SiteIptvSummaryError):
            summarize_site_iptv([])


if __name__ == "__main__":
    unittest.main()
