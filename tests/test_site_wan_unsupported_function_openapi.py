import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class WanUnsupportedFunctionOpenApiTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "7" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-internal"

    def test_client_uses_only_the_documented_fixed_filter(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": {"functions": ["raw private function label"]},
                }) as request:
            result = self.client.read_site_wan_unsupported_function_summary(self.site_ref)
        request.assert_called_once_with(
            "GET",
            "/openapi/v1/ctrl/sites/site-internal/wan/networks/unsupportedFunction?filter=1",
            token="token")
        self.assertEqual(result["reported_limitation_entry_count"], 1)
        self.assertNotIn("raw private function label", repr(result))

    def test_fixed_path_guard_accepts_only_filter_one_for_configured_controller(self):
        base = "/openapi/v1/ctrl/sites/site-internal/wan/networks/unsupportedFunction"
        self.assertTrue(self.client._site_wan_unsupported_functions_request_valid(
            base + "?filter=1"))
        for path in (base, base + "?filter=0", base + "?filter=2",
                     base + "?filter=1&filter=1", base + "?filter=01",
                     base + "?filter=1&other=x",
                     base.replace("/ctrl/", "/other/") + "?filter=1"):
            self.assertFalse(self.client._site_wan_unsupported_functions_request_valid(path))

    def test_nonzero_upstream_error_is_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 1, "result": {"functions": []},
                }):
            with self.assertRaises(OpenApiError):
                self.client.read_site_wan_unsupported_function_summary(self.site_ref)


if __name__ == "__main__":
    unittest.main()
