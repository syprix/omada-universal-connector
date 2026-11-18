import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerRemoteLoggingIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_read_route_and_target_redaction(self):
        raw = {"enable": True, "host": "logs.example.com", "port": 6514}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_controller_remote_logging()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/global/controller/setting/syslog", token="token")
        self.assertTrue(result["data"]["settings"]["enabled"])
        self.assertTrue(result["data"]["settings"]["host_present"])
        self.assertNotIn("logs.example.com", str(result))
        self.assertNotIn("6514", str(result))
        self.assertFalse(result["partial"])

    def test_non_boolean_enable_is_marked_partial(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"enable": 1}}):
            result = self.client.read_controller_remote_logging()
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertTrue(result["partial"])

    def test_fixed_path_rejects_other_controller_ids(self):
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/other/global/controller/setting/syslog")

    def test_tip_uses_its_own_fixed_read_route(self):
        raw = {"enable": False, "host": "", "port": 0}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_controller_remote_logging_tip()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/global/controller/setting/syslog/tip", token="token")
        self.assertEqual(result["resource"], "controller_remote_logging_tip")
        self.assertFalse(result["data"]["settings"]["enabled"])
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
