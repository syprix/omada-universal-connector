import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteMulticastRateLimitIntegrationTests(unittest.TestCase):
    def test_fixed_multicast_rate_limit_route(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        payload = {"mcastRateLimit": {"enable": True, "igmpEnable": True,
                                      "igmpPps": 120}}
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            result = client.read_site_multicast_rate_limit_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref + "/multicast-rate-limit",
            token="token")
        self.assertEqual(result["data"]["igmp_packets_per_second"], 120)


if __name__ == "__main__":
    unittest.main()
