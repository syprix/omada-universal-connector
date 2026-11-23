import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class GatewayWebfilterOpenApiTests(unittest.TestCase):
    def make_client(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        site_ref = "9" * 24
        client._site_ids_by_ref[site_ref] = "site-internal"
        return client, site_ref

    def test_client_binds_site_reads_fixed_pages_and_redacts_rule_data(self):
        client, site_ref = self.make_client()
        payload = {"errorCode": 0, "result": {
            "totalRows": 1, "currentPage": 1, "currentSize": 1,
            "supportKeyword": True, "supportCategory": True,
            "supportTimeSchedule": False,
            "data": [{"type": "gateway", "status": True,
                      "existKeyword": True, "existCategory": False,
                      "existTimeSchedule": False, "name": "private-name",
                      "urls": ["private-url"], "sourceIds": ["private-id"]}],
        }}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=payload) as request:
            result = client.read_site_gateway_webfilter_summary(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-internal/url-filters/gateway?page=1&pageSize=100",
            token="token")
        self.assertEqual(result["by_documented_rule_type"], {"ap": 0, "gateway": 1})
        self.assertEqual(result["enabled_status_count"], 1)
        self.assertNotIn("private-name", repr(result))
        self.assertNotIn("private-url", repr(result))
        self.assertNotIn("private-id", repr(result))

    def test_request_guard_binds_controller_page_and_fixed_page_size(self):
        client, _ = self.make_client()
        self.assertTrue(client._site_gateway_webfilter_request_valid(
            "/openapi/v1/ctrl/sites/site-internal/url-filters/gateway?page=1&pageSize=100"))
        self.assertFalse(client._site_gateway_webfilter_request_valid(
            "/openapi/v1/other/sites/site-internal/url-filters/gateway?page=1&pageSize=100"))
        self.assertFalse(client._site_gateway_webfilter_request_valid(
            "/openapi/v1/ctrl/sites/site-internal/url-filters/gateway?page=11&pageSize=100"))
        self.assertFalse(client._site_gateway_webfilter_request_valid(
            "/openapi/v1/ctrl/sites/site-internal/url-filters/gateway?page=1&pageSize=1000"))


if __name__ == "__main__":
    unittest.main()
