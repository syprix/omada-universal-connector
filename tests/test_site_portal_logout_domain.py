import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_portal_logout_domain import (
    SitePortalLogoutDomainError,
    project_site_portal_logout_domain,
)


class SitePortalLogoutDomainTests(unittest.TestCase):
    def test_projects_documented_domain(self):
        self.assertEqual(project_site_portal_logout_domain({"domain": "example.net"}),
                         {"domain": "example.net"})

    def test_preserves_source_documented_empty_domain(self):
        self.assertEqual(project_site_portal_logout_domain({"domain": ""}),
                         {"domain": ""})

    def test_rejects_missing_or_non_string_domain(self):
        for value in ({}, {"domain": None}, {"domain": 4}, None):
            with self.subTest(value=value), self.assertRaises(SitePortalLogoutDomainError):
                project_site_portal_logout_domain(value)


class SitePortalLogoutDomainClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "f" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_path_and_returns_only_the_domain(self):
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "domain": "example.net", "private": "do-not-return"}}) as request:
            result = self.client.read_site_portal_logout_domain(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/portal-logout",
            token="test-token")
        self.assertEqual(result["data"], {"domain": "example.net"})
        self.assertNotIn("do-not-return", repr(result))

    def test_rejects_missing_domain_and_unknown_site(self):
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": {}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_portal_logout_domain(self.site_ref)
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_portal_logout_domain("e" * 24)

    def test_path_guard_binds_controller_and_fixed_resource(self):
        self.assertTrue(self.client._site_portal_logout_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/portal-logout"))
        self.assertFalse(self.client._site_portal_logout_request_valid(
            "/openapi/v1/other/sites/site_internal/portal-logout"))


if __name__ == "__main__":
    unittest.main()
