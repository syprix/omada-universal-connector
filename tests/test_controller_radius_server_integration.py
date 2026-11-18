import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerRadiusServerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_read_route_and_redacted_projection(self):
        raw = {
            "enable": True, "authServerPort": 1812, "secret": "private-secret",
            "tunnelReplyEnable": True, "status": False, "failReason": "private-failure",
            "serverAddressType": 1, "customAddress": "private-address",
            "radiusServerCertificate": {"cerId": "private-cert-id",
                                         "keyPassword": "private-key-password"},
        }
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_controller_radius_server()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/global/controller/setting/network/radius-server",
            token="token")
        self.assertTrue(result["data"]["redacted_presence"]["secret"])
        for value in ("private-secret", "private-failure", "private-address",
                      "private-cert-id", "private-key-password"):
            self.assertNotIn(value, str(result))

    def test_invalid_projection_and_other_controller_id_are_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_radius_server()
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/other/global/controller/setting/network/radius-server")


if __name__ == "__main__":
    unittest.main()
