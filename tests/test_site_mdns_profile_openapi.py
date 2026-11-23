import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class MdnsProfileOpenApiTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-internal"

    def test_client_reads_one_site_bound_profile_list(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": {"data": [{"id": "secret-id", "name": "secret-name",
                                         "serviceIds": ["_private._tcp.local"],
                                         "defaultProfile": True}]},
                }) as request:
            result = self.client.read_site_mdns_profile_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-internal/profiles/bonjour-service",
            token="token")
        self.assertEqual(result["profile_count"], 1)
        self.assertNotIn("secret-id", repr(result))
        self.assertNotIn("secret-name", repr(result))
        self.assertNotIn("_private._tcp.local", repr(result))

    def test_profile_path_guard_is_fixed_and_site_scoped(self):
        path = "/openapi/v1/ctrl/sites/site-internal/profiles/bonjour-service"
        self.assertTrue(self.client._site_mdns_profiles_request_valid(path))
        self.assertFalse(self.client._site_mdns_profiles_request_valid(
            path + "?page=1&pageSize=100"))
        self.assertFalse(self.client._site_mdns_profiles_request_valid(
            path.replace("/ctrl/", "/other/")))

    def test_nonzero_upstream_error_is_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 1, "result": {"data": []},
                }):
            with self.assertRaises(OpenApiError):
                self.client.read_site_mdns_profile_summary(self.site_ref)


if __name__ == "__main__":
    unittest.main()
