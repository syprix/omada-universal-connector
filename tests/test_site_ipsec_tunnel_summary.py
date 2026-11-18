import unittest

from app.site_ipsec_tunnel_summary import (
    SiteIpsecTunnelSummaryError, project_site_ipsec_tunnel_summary,
)


class SiteIpsecTunnelSummaryTests(unittest.TestCase):
    def test_aggregates_status_and_direction_without_names_or_addresses(self):
        result = project_site_ipsec_tunnel_summary([
            {"site": "Private site", "name": "Office tunnel", "id": 1,
             "status": True, "direction": "in", "localPeerIp": "192.0.2.10",
             "remotePeerIp": "198.51.100.20", "localSa": "10.0.0.0/24",
             "remoteSa": "10.1.0.0/24"},
            {"name": "Backup", "status": False, "direction": "out"},
        ])
        self.assertEqual(result["data"], {
            "tunnel_count": 2, "enabled_tunnel_count": 1,
            "disabled_tunnel_count": 1, "status_present_count": 2,
            "inbound_sa_count": 1, "outbound_sa_count": 1,
            "direction_present_count": 2,
        })
        self.assertFalse(result["partial"])
        for private in ("Private site", "Office tunnel", "192.0.2.10", "10.0.0.0/24"):
            self.assertNotIn(private, repr(result))

    def test_counts_invalid_missing_and_unknown_fields(self):
        result = project_site_ipsec_tunnel_summary([
            {"status": "yes", "direction": "sideways", "extra": "hidden"},
        ])
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("hidden", repr(result))
        with self.assertRaises(SiteIpsecTunnelSummaryError):
            project_site_ipsec_tunnel_summary([{}] * 501)


if __name__ == "__main__":
    unittest.main()
