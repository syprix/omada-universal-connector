import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteIdsIpsConfigOpenApiTests(unittest.TestCase):
    def test_client_binds_site_and_reads_fixed_configuration_path(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        site_ref = "7" * 24
        client._site_ids_by_ref[site_ref] = "site-internal"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": {"enable": True, "ipsMode": 1, "dpLevel": 2,
                               "geoEnable": False, "customCategories": [1, 8]},
                }) as request:
            result = client.read_site_ids_ips_config_summary(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-internal/network-security/ips",
            token="token")
        self.assertEqual(result["custom_category_count"], 2)
        self.assertEqual(result["ips_mode"], 1)

    def test_fixed_path_guard_requires_matching_controller_and_exact_path(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.assertTrue(client._site_ids_ips_config_request_valid(
            "/openapi/v1/ctrl/sites/site-internal/network-security/ips"))
        self.assertFalse(client._site_ids_ips_config_request_valid(
            "/openapi/v1/other/sites/site-internal/network-security/ips"))
        self.assertFalse(client._site_ids_ips_config_request_valid(
            "/openapi/v1/ctrl/sites/site-internal/network-security/ips?x=1"))


if __name__ == "__main__":
    unittest.main()
