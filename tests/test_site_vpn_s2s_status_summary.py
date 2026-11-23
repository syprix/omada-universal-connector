import unittest

from app.site_vpn_s2s_status_summary import (
    SiteVpnS2SStatusError, project_site_vpn_s2s_status,
)


class SiteVpnS2SStatusSummaryTests(unittest.TestCase):
    def test_counts_raw_status_codes_and_drops_sensitive_fields(self):
        result = project_site_vpn_s2s_status(
            [{"status": 0, "remotePeerIp": "192.0.2.4", "name": "private"},
             {"status": 7, "id": "secret"}], 2, 2, 1, 10, True)
        self.assertEqual(result["status_code_counts"], {"0": 1, "7": 1})
        self.assertEqual(result["vpn_type_name"], "ipsec")
        self.assertNotIn("remotePeerIp", result)
        self.assertNotIn("name", result)
        self.assertTrue(result["support_wireguard_status"])
        self.assertFalse(result["partial"])

    def test_unknown_status_and_incomplete_page_are_partial(self):
        result = project_site_vpn_s2s_status([{}], 4, 2, 1, 1)
        self.assertEqual(result["status_unknown_count"], 1)
        self.assertTrue(result["partial"])

    def test_rejects_invalid_protocol_integer_range_and_support_flag(self):
        for kwargs in (
            ([{"status": 1 << 31}], 2, 1, 1, 1, None),
            ([{"status": True}], 2, 1, 1, 1, None),
            ([], 0, 0, 1, 1, None),
            ([], 2, 0, 1, 1, "yes"),
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(SiteVpnS2SStatusError):
                project_site_vpn_s2s_status(*kwargs[:5], kwargs[5])


if __name__ == "__main__":
    unittest.main()
