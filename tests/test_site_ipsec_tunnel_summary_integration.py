import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteIpsecTunnelSummaryIntegrationTests(unittest.TestCase):
    def test_fixed_read_route_and_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": [{
                    "status": True, "direction": "in", "localPeerIp": "192.0.2.10"}]}) as req:
            result = client.read_site_ipsec_tunnel_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref + "/dashboard/lpset-tunnel-stats",
            token="token")
        self.assertTrue(result["data"]["enabled_tunnel_count"])
        self.assertNotIn("192.0.2.10", repr(result))


if __name__ == "__main__":
    unittest.main()
