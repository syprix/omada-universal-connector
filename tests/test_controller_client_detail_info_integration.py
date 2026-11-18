import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerClientDetailInfoIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_route_and_controller_binding(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"clientRecognitionEnable": True}}) as request:
            result = self.client.read_controller_client_detail_info()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/client-detail-information", token="token")
        self.assertEqual(result["resource"], "controller_client_detail_info")
        self.assertTrue(result["data"]["settings"]["client_recognition_enable"])
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_client_detail_info()
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/other/client-detail-information")


if __name__ == "__main__":
    unittest.main()
