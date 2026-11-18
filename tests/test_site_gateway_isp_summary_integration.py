import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteGatewayIspSummaryIntegrationTests(unittest.TestCase):
    def test_fixed_route_and_redacted_gateway_isp_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        payload = {"data": [{"name": "private", "status": 1,
                             "ispInfo": {"ispArr": [{"ip": "hidden", "status": 0,
                             "onLineStatus": 0, "uploadPercent": 0,
                             "downloadPercent": 0}]}}]}
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            result = client.read_site_gateway_isp_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/gateway/isp/load", token="token")
        self.assertEqual(result["data"]["offline_isp_count"], 1)
        self.assertNotIn("hidden", repr(result))


if __name__ == "__main__":
    unittest.main()
