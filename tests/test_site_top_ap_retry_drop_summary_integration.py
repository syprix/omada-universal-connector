import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteTopApRetryDropSummaryIntegrationTests(unittest.TestCase):
    def test_upstream_guard_requires_bound_controller_and_exact_window(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.assertTrue(client._site_top_ap_request_valid(
            "/openapi/v1/ctrl/sites/site-1/dashboard/top-aps?start=100000&end=186400"))
        self.assertFalse(client._site_top_ap_request_valid(
            "/openapi/v1/other/sites/site-1/dashboard/top-aps?start=100000&end=186400"))
        self.assertFalse(client._site_top_ap_request_valid(
            "/openapi/v1/ctrl/sites/site-1/dashboard/top-aps?start=100000&end=186401"))

    def test_fixed_route_window_and_redacted_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        payload = {"topApByRt": [{"device": "private-device", "ratio": 53}],
                   "topApByDrop": []}
        fixed_now = datetime.fromtimestamp(2_000_000_000, timezone.utc)
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch("app.openapi.datetime") as datetime_mock, \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            datetime_mock.now.return_value = fixed_now
            result = client.read_site_top_ap_retry_drop_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/top-aps?start=1999913600&end=2000000000", token="token")
        self.assertEqual(result["data"]["maximum_ap_by_rt_ratio_percent"], 53)
        self.assertNotIn("private-device", repr(result))


if __name__ == "__main__":
    unittest.main()
