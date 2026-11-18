import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerClientActiveTimeoutIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_controller_path_projection_and_unknown_live_evidence(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "clientActiveTimeoutMin": 5}}) as request:
            result = self.client.read_controller_client_active_timeout()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/controller/setting/active-timeout", token="token")
        self.assertEqual(result["resource"], "controller_client_active_timeout")
        self.assertEqual(result["data"]["active_timeout_minutes"], 5)
        self.assertFalse(result["partial"])
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["operation"] == "controller_client_active_timeout")["runtime_evidence"][0]
        self.assertFalse(evidence["controller_response_observed"])
        self.assertEqual(evidence["permission_state"], "unknown")
        self.assertEqual(evidence["support_state"], "unknown")

    def test_invalid_response_and_controller_mismatch_are_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_client_active_timeout()
        good = "/openapi/v1/ctrl/controller/setting/active-timeout"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"))


if __name__ == "__main__":
    unittest.main()
