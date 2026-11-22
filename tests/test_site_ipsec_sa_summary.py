import unittest
from app.site_ipsec_sa_summary import SiteIpsecSaSummaryError, summarize_site_ipsec_associations


class SiteIpsecSaSummaryTests(unittest.TestCase):
    def test_counts_and_redacts_all_sa_details(self):
        result = summarize_site_ipsec_associations([
            {"vpnId": 1, "spi": 55, "direction": "in", "localPeerIp": "192.0.2.1",
             "remotePeerIp": "198.51.100.2", "localSa": "10.0.0.0/24",
             "remoteSa": "10.1.0.0/24", "protocol": "ESP", "name": "secret"},
            {"direction": "out", "espEncryption": "AES"},
        ])
        self.assertEqual(result["security_association_count"], 2)
        self.assertEqual(result["by_direction"], {"in": 1, "out": 1})
        for value in ("192.0.2.1", "198.51.100.2", "10.0.0.0/24", "secret", "AES"):
            self.assertNotIn(value, str(result))
        self.assertIn("tunnel state is unknown", result["connection_status"])

    def test_bad_fields_and_unknown_direction_are_partial(self):
        result = summarize_site_ipsec_associations([
            {"direction": {"bad": True}, "spi": True, "future": "hidden"},
        ])
        self.assertEqual(result["by_direction"], {"unknown": 1})
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])

    def test_row_limit(self):
        with self.assertRaises(SiteIpsecSaSummaryError):
            summarize_site_ipsec_associations([{}] * 10001)


if __name__ == "__main__":
    unittest.main()
