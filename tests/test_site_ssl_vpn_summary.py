import unittest

from app.site_ssl_vpn_summary import SiteSslVpnSummaryError, summarize_site_ssl_vpn


class SiteSslVpnSummaryTests(unittest.TestCase):
    def test_projects_configuration_without_returning_network_or_auth_details(self):
        raw = {"id": "server-secret", "status": True, "wanPort": "port-secret",
               "wanIp": "198.51.100.4", "ipPoolStart": "10.0.0.2",
               "ipPoolEnd": "10.0.0.20", "primaryDns": "192.0.2.53",
               "secondaryDns": "192.0.2.54", "servicePort": 443, "authType": 1,
               "radiusSetting": {"radiusProfile": "secret-profile", "nasIp": "192.0.2.8"},
               "LDAPSetting": {"LDAPProfile": "ldap-secret"},
               "nameLockSetting": {"status": True, "times": 4, "duration": 20},
               "ipLockSetting": {"status": False, "times": 3, "duration": 30},
               "exitAtIdle": True, "exitTime": 300, "totalTraffic": True,
               "supportRadius": True, "existRadius": True, "supportLDAP": False,
               "existLdap": False, "supportByDsLiteAndMapE": True}
        result = summarize_site_ssl_vpn(raw)
        self.assertEqual(result["data"]["authentication_mode"], "radius")
        self.assertEqual(result["data"]["service_port"], 443)
        self.assertTrue(result["data"]["name_lock_enabled"])
        self.assertFalse(result["data"]["ip_lock_enabled"])
        self.assertFalse(result["partial"])
        for secret in ("server-secret", "port-secret", "198.51.100.4", "10.0.0.2",
                       "192.0.2.53", "secret-profile", "192.0.2.8", "ldap-secret"):
            self.assertNotIn(secret, repr(result))

    def test_invalid_enum_ranges_and_unknown_fields_mark_partial(self):
        result = summarize_site_ssl_vpn({"status": 1, "servicePort": 70000,
                                         "authType": 3, "exitAtIdle": True,
                                         "exitTime": 4, "future": "discard"})
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 4)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("discard", repr(result))

    def test_non_object_response_rejected(self):
        with self.assertRaises(SiteSslVpnSummaryError):
            summarize_site_ssl_vpn([])


if __name__ == "__main__":
    unittest.main()
