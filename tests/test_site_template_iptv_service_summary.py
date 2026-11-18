import unittest

from app.site_template_iptv_service_summary import (
    SiteTemplateIptvServiceSummaryError, summarize_site_template_iptv_service,
)


class SiteTemplateIptvServiceSummaryTests(unittest.TestCase):
    def test_projects_both_service_settings_without_network_identifiers(self):
        result = summarize_site_template_iptv_service({
            "igmpSetting": {"enable": True, "version": 2,
                            "wanPortId": "secret-igmp-wan"},
            "iptvSetting": {"enable": True, "mode": 1,
                            "wanPortId": "secret-iptv-wan",
                            "portConfig": [{"portId": "secret-port", "type": 3}],
                            "customConfig": {"ipPhoneVlanId": 10,
                                             "ipPhoneVlanPriority": 1,
                                             "iptvVlanId": 20,
                                             "iptvVlanPriority": 2}},
        })
        self.assertFalse(result["partial"])
        self.assertTrue(result["data"]["igmp_settings_present"])
        self.assertTrue(result["data"]["iptv_settings_present"])
        self.assertEqual(result["data"]["igmp"]["version"], 2)
        self.assertEqual(result["data"]["iptv"]["port_type_counts"],
                         {"internet": 0, "iptv": 0, "ip_phone": 1})
        for secret in ("secret-igmp-wan", "secret-iptv-wan", "secret-port", "10", "20"):
            self.assertNotIn(secret, repr(result))

    def test_required_igmp_and_optional_iptv_are_distinguished(self):
        result = summarize_site_template_iptv_service({
            "igmpSetting": {"enable": False, "version": 3, "wanPortId": ""},
        })
        self.assertFalse(result["partial"])
        self.assertFalse(result["data"]["iptv_settings_present"])
        missing = summarize_site_template_iptv_service({"iptvSetting": {}})
        self.assertTrue(missing["partial"])
        self.assertGreater(missing["missing_field_count"], 0)

    def test_unknown_fields_are_counted_and_not_returned(self):
        result = summarize_site_template_iptv_service({
            "igmpSetting": {"enable": True, "version": 2, "wanPortId": "", "secret": "x"},
            "private": "omit",
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertNotIn("omit", repr(result))
        self.assertNotIn("secret", repr(result))

    def test_non_object_response_rejected(self):
        with self.assertRaises(SiteTemplateIptvServiceSummaryError):
            summarize_site_template_iptv_service([])


if __name__ == "__main__":
    unittest.main()
