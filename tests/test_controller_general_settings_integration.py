import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerGeneralSettingsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_route_and_projected_settings(self):
        raw = {"name": "Home Controller", "timeZone": "Europe/Berlin", "region": "DE",
               "dst": {"enable": False}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_controller_general_settings()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/global/controller/setting/general", token="token")
        self.assertEqual(result["resource"], "controller_general_settings")
        self.assertEqual(result["data"]["settings"]["region"], "DE")
        self.assertFalse(result["partial"])
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_general_settings()
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/other/global/controller/setting/general")


if __name__ == "__main__":
    unittest.main()
