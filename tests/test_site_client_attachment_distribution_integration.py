import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteClientAttachmentDistributionIntegrationTests(unittest.TestCase):
    def test_fixed_route_and_aggregate_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        payload = {"eapDistribution": {"totalEapClients": 8, "eaps": [{"name": "hidden"}]},
                   "switchDistribution": {"totalSwitchClients": 3, "switches": []}}
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            result = client.read_site_client_attachment_distribution_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/client-distribution", token="token")
        self.assertEqual(result["data"]["access_point_attached_client_count"], 8)
        self.assertNotIn("hidden", repr(result))


if __name__ == "__main__":
    unittest.main()
