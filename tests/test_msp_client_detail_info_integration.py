import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class MspClientDetailInfoIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_msp_route_and_only_documented_flags_are_returned(self):
        raw = {"clientHealthEnable": True, "clientHistoryEnable": False,
               "clientDataTrendEnable": True, "private": "secret"}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_msp_client_detail_info("msp-1")
        request.assert_called_once_with(
            "GET", "/openapi/v1/msp/msp-1/client-detail-information", token="token")
        self.assertEqual(result["resource"], "msp_client_detail_info")
        self.assertEqual(result["data"]["present_count"], 3)
        self.assertNotIn("secret", str(result))
        self.assertTrue(result["partial"])

    def test_bad_msp_reference_and_result_are_rejected(self):
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client.read_msp_client_detail_info("../msp")
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_msp_client_detail_info("msp-1")


if __name__ == "__main__":
    unittest.main()
