import unittest

from app.site_vpn_tunnel_summary import (
    SiteVpnTunnelSummaryError, project_site_vpn_tunnel_summary,
)


class SiteVpnTunnelSummaryTests(unittest.TestCase):
    def test_aggregates_vpn_counts_and_bytes_without_tunnel_identity(self):
        result = project_site_vpn_tunnel_summary([
            {"site": "private-site", "name": "private-vpn-a", "status": True,
             "tunnels": 3, "txData": 400, "rxData": 800},
            {"site": "private-site", "name": "private-vpn-b", "status": False,
             "tunnels": 2, "txData": 100, "rxData": 200},
        ], 0)
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["vpn_type"], "server")
        self.assertEqual(result["data"]["vpn_count"], 2)
        self.assertEqual(result["data"]["enabled_vpn_count"], 1)
        self.assertEqual(result["data"]["disabled_vpn_count"], 1)
        self.assertEqual(result["data"]["total_tunnel_count"], 5)
        self.assertEqual(result["data"]["total_tx_bytes"], 500)
        self.assertEqual(result["data"]["total_rx_bytes"], 1_000)
        self.assertNotIn("private-site", repr(result))
        self.assertNotIn("private-vpn", repr(result))

    def test_marks_missing_invalid_and_unknown_fields_partial(self):
        result = project_site_vpn_tunnel_summary([
            {"status": "yes", "tunnels": -1, "txData": 5,
             "rxData": 6, "future": "omitted"}
        ], 1)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["invalid_field_count"], 2)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertEqual(result["data"]["missing_field_count"], 0)
        self.assertIsNone(result["data"]["total_tunnel_count"])
        self.assertNotIn("omitted", repr(result))

    def test_rejects_invalid_type_and_oversized_list(self):
        with self.assertRaises(SiteVpnTunnelSummaryError):
            project_site_vpn_tunnel_summary([], 2)
        with self.assertRaises(SiteVpnTunnelSummaryError):
            project_site_vpn_tunnel_summary([{}] * 501, 1)


if __name__ == "__main__":
    unittest.main()
