import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerClientHistoryRetentionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_route_and_projection(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "clientsDataEnable": True, "clientStatEnable": False,
                }}) as request:
            result = self.client.read_controller_client_history_retention()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/controller/client/history-enable", token="token")
        self.assertEqual(result["resource"], "controller_client_history_retention")
        self.assertTrue(result["data"]["client_history_enabled"])
        self.assertFalse(result["partial"])

    def test_invalid_result_and_controller_mismatch_are_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_client_history_retention()
        good = "/openapi/v1/ctrl/controller/client/history-enable"
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"))


if __name__ == "__main__":
    unittest.main()
