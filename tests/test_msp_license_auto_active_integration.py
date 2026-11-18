import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class MspLicenseAutoActiveIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_cbc_path_and_status_projection(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"autoActive": True}}) as request:
            result = self.client.read_msp_license_auto_active("msp-1")
        request.assert_called_once_with(
            "GET", "/openapi/v1/msp/msp-1/license/auto-active", token="token")
        self.assertEqual(result["resource"], "msp_license_auto_active")
        self.assertTrue(result["data"]["enabled"])
        with self.assertRaisesRegex(OpenApiError, "msp_reference_invalid"):
            self.client.read_msp_license_auto_active("../msp")

    def test_invalid_result_is_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_msp_license_auto_active("msp-1")


if __name__ == "__main__":
    unittest.main()
