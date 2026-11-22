import unittest

from app.site_vpn_client_status_summary import (
    SiteVpnClientStatusSummaryError, summarize_vpn_client_status,
)


class SiteVpnClientStatusSummaryTests(unittest.TestCase):
    def test_counts_unmapped_status_codes_and_redacts_sensitive_fields(self):
        result = summarize_vpn_client_status([
            {"vpnType": 4, "status": 8, "userName": "private", "remotePeerIp": "192.0.2.1"},
            {"vpnType": 4, "status": 8, "virtualIp": "198.51.100.1"},
        ], 4)
        self.assertEqual(result["protocol"], "wireguard")
        self.assertEqual(result["by_source_status_code"], {"8": 2})
        self.assertNotIn("private", str(result))
        self.assertNotIn("192.0.2.1", str(result))
        self.assertIn("without a code mapping", result["status_semantics"])

    def test_missing_invalid_and_unknown_fields_are_explicit(self):
        result = summarize_vpn_client_status([{"status": True, "extra": "hidden"}, {}], 0)
        self.assertEqual(result["missing_status_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["invalid_row_count"], 1)
        self.assertTrue(result["partial"])

    def test_rejects_undocumented_protocol_and_excess_rows(self):
        for vpn_type in (2, 5, True):
            with self.assertRaises(SiteVpnClientStatusSummaryError):
                summarize_vpn_client_status([], vpn_type)
        with self.assertRaises(SiteVpnClientStatusSummaryError):
            summarize_vpn_client_status([{}] * 10001, 0)


if __name__ == "__main__":
    unittest.main()
