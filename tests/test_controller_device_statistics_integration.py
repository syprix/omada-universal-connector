import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerDeviceStatisticsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_exact_controller_read_and_redacted_projection(self):
        raw = {"allDevices": 4, "good": 3, "poor": 1,
               "switchHealth": {"good": 1}, "private": "omit"}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": raw}) as request:
            result = self.client.read_controller_device_statistics()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/devices/stat?page=1&pageSize=1", token="token")
        self.assertEqual(result["resource"], "controller_device_statistics")
        self.assertEqual(result["data"]["counts"], {
            "total_devices": 4, "health_good": 3, "health_poor": 1})
        self.assertEqual(result["data"]["omitted_variant_field_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private", str(result))
        evidence = next(item for item in self.client.capabilities()["items"]
                        if item["operation"] == "controller_device_statistics")["runtime_evidence"][0]
        self.assertFalse(evidence["controller_response_observed"])
        self.assertEqual(evidence["permission_state"], "unknown")
        self.assertEqual(evidence["support_state"], "unknown")

    def test_invalid_response_and_controller_path_are_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_device_statistics()
        good = "/openapi/v1/ctrl/devices/stat?page=1&pageSize=1"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"))
        for bad in (
                "/openapi/v1/ctrl/devices/stat",
                "/openapi/v1/ctrl/devices/stat?page=2&pageSize=1",
                "/openapi/v1/ctrl/devices/stat?page=1&pageSize=1000",
                "/openapi/v1/ctrl/devices/stat?pageSize=1&page=1"):
            with self.subTest(path=bad), self.assertRaisesRegex(
                    OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", bad)


if __name__ == "__main__":
    unittest.main()
