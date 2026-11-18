import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class MspDeviceTagsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_cbc_msp_path_and_redacted_summary(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": [
                    {"name": "private-tag", "tagId": "secret-id"}]}) as request:
            result = self.client.read_msp_device_tags("msp-1")
        request.assert_called_once_with(
            "GET", "/openapi/v1/msp/msp-1/devices/tag", token="token")
        self.assertEqual(result["resource"], "msp_device_tags")
        self.assertEqual(result["data"]["tag_count"], 1)
        self.assertNotIn("private-tag", str(result))
        self.assertNotIn("secret-id", str(result))

    def test_bad_reference_and_payload_are_rejected(self):
        with self.assertRaisesRegex(OpenApiError, "msp_reference_invalid"):
            self.client.read_msp_device_tags("../msp")
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_msp_device_tags("msp-1")


if __name__ == "__main__":
    unittest.main()
