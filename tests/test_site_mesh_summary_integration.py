import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteMeshSummaryIntegrationTests(unittest.TestCase):
    def test_fixed_mesh_route_and_gateway_redaction(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        payload = {"mesh": {"meshEnable": True, "gateway": "192.0.2.1"}}
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            result = client.read_site_mesh_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref + "/mesh", token="token")
        self.assertTrue(result["data"]["mesh_enabled"])
        self.assertNotIn("192.0.2.1", repr(result))


if __name__ == "__main__":
    unittest.main()
