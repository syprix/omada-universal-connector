import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerExperienceImprovementIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_route_and_controller_binding(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"expImprove": False}}) as request:
            result = self.client.read_controller_experience_improvement()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/global/controller/setting/exp-improve", token="token")
        self.assertEqual(result["resource"], "controller_experience_improvement")
        self.assertFalse(result["data"]["experience_improvement_enabled"])
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_experience_improvement()
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/other/global/controller/setting/exp-improve")


if __name__ == "__main__":
    unittest.main()
