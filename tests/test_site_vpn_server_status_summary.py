import unittest
from app.site_vpn_server_status_summary import (
    SiteVpnServerStatusSummaryError, summarize_vpn_server_status,
)


class SiteVpnServerStatusSummaryTests(unittest.TestCase):
    def test_counts_unmapped_status_codes_and_redacts_identity_data(self):
        result = summarize_vpn_server_status([
            {"vpnType": 5, "status": 2, "userName": "secret", "loginIp": "192.0.2.1"},
            {"vpnType": 5, "status": 7, "virtualIp": "198.51.100.1"},
        ], 5)
        self.assertEqual(result["protocol"], "ssl_vpn")
        self.assertEqual(result["by_source_status_code"], {"2": 1, "7": 1})
        self.assertNotIn("secret", str(result))
        self.assertNotIn("192.0.2.1", str(result))
        self.assertIn("without a code mapping", result["status_semantics"])

    def test_missing_invalid_and_unknown_data_are_reported(self):
        result = summarize_vpn_server_status([{"status": True, "extra": "hidden"}, {}], 0)
        self.assertEqual(result["missing_status_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["invalid_row_count"], 1)
        self.assertTrue(result["partial"])

    def test_invalid_protocol_and_limit(self):
        with self.assertRaises(SiteVpnServerStatusSummaryError):
            summarize_vpn_server_status([], 6)
        with self.assertRaises(SiteVpnServerStatusSummaryError):
            summarize_vpn_server_status([], True)
        with self.assertRaises(SiteVpnServerStatusSummaryError):
            summarize_vpn_server_status([{}] * 10001, 0)


if __name__ == "__main__":
    unittest.main()
