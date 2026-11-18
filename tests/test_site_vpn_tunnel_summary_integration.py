import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteVpnTunnelSummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_reads_selected_vpn_type_and_aggregates_bytes(self):
        site_ref = "a" * 24
        payload = [{"site": "private-site", "name": "private-vpn", "status": True,
                    "tunnels": 3, "txData": 400, "rxData": 800}]
        with patch.object(self.client, "_resolve_site_ref", return_value="site_1"), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": payload}) as req:
            result = self.client.read_site_vpn_tunnel_summary(site_ref, 0)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/dashboard/vpn-tunnel-stats?type=0",
            token="token")
        self.assertEqual(result["data"]["total_tx_bytes"], 400)
        self.assertNotIn("private-vpn", repr(result))

    def test_path_guard_binds_controller_and_vpn_type(self):
        good = "/openapi/v1/ctrl/sites/site/dashboard/vpn-tunnel-stats?type=1"
        self.assertTrue(self.client._site_vpn_tunnel_request_valid(good))
        self.assertFalse(self.client._site_vpn_tunnel_request_valid(
            good.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_vpn_tunnel_request_valid(
            good.replace("type=1", "type=2")))


if __name__ == "__main__":
    unittest.main()
