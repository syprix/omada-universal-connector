import unittest

from app.site_gre_tunnel_summary import SiteGreTunnelSummaryError, summarize_site_gre_tunnel


class SiteGreTunnelSummaryTests(unittest.TestCase):
    def test_projects_values_but_discards_endpoint_addresses(self):
        raw = {"greEnable": True, "tunnelMtu": 1400, "interval": 30, "maxCount": 5,
               "primaryAddress": "198.51.100.1", "secondaryAddress": "2001:db8::1"}
        result = summarize_site_gre_tunnel(raw)
        self.assertEqual(result["data"], {"enabled": True, "tunnel_mtu": 1400,
                         "keepalive_interval_seconds": 30, "keepalive_miss_limit": 5,
                         "primary_endpoint_configured": True,
                         "secondary_endpoint_configured": True})
        self.assertFalse(result["partial"])
        self.assertNotIn("198.51.100.1", repr(result))
        self.assertNotIn("2001:db8::1", repr(result))

    def test_invalid_ranges_missing_fields_and_unknowns_mark_partial(self):
        result = summarize_site_gre_tunnel({"greEnable": 1, "tunnelMtu": 800,
                                             "interval": 700, "maxCount": 11,
                                             "primaryAddress": None, "future": "private"})
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 5)
        self.assertEqual(result["missing_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_non_object_response_rejected(self):
        with self.assertRaises(SiteGreTunnelSummaryError):
            summarize_site_gre_tunnel([])


if __name__ == "__main__":
    unittest.main()
