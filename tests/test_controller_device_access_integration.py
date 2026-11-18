import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerDeviceAccessIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_read_route_and_boolean_projection(self):
        raw = {"webControlHttp": False, "webControlHttps": True, "appDiscovery": True}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_controller_device_access()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/controller/setting/services/device-access", token="token")
        self.assertEqual(result["resource"], "controller_device_access")
        self.assertEqual(result["data"]["settings"]["app_discovery"], True)
        self.assertFalse(result["partial"])

    def test_bad_upstream_shape_fails_closed(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"appDiscovery": "yes"}}):
            result = self.client.read_controller_device_access()
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertTrue(result["partial"])

    def test_fixed_path_rejects_other_controller_ids(self):
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/other/controller/setting/services/device-access")


if __name__ == "__main__":
    unittest.main()
