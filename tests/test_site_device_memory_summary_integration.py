import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteDeviceMemorySummaryIntegrationTests(unittest.TestCase):
    def test_fixed_window_and_redacted_result(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        fixed_now = datetime.fromtimestamp(2_000_000_000, timezone.utc)
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch("app.openapi.datetime") as datetime_mock, \
                patch.object(client, "_request_json", return_value={"result": [
                    {"name": "private-device", "memUsage": 77}
                ]}) as req:
            datetime_mock.now.return_value = fixed_now
            result = client.read_site_device_memory_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/top-device-memory-usage?start=1999913600&end=2000000000",
            token="token")
        self.assertEqual(result["data"]["maximum_memory_usage_percent"], 77)
        self.assertNotIn("private-device", repr(result))

    def test_guard_requires_bound_controller_and_exact_window(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        valid = "/openapi/v1/ctrl/sites/site/dashboard/top-device-memory-usage?start=10&end=86410"
        self.assertTrue(client._site_device_memory_request_valid(valid))
        self.assertFalse(client._site_device_memory_request_valid(valid.replace("/ctrl/", "/other/")))
        self.assertFalse(client._site_device_memory_request_valid(valid.replace("end=86410", "end=86411")))


if __name__ == "__main__":
    unittest.main()
