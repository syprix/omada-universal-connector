import unittest
from unittest.mock import patch

from app.operation_registry import REGISTRY, RegistryError
from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient
from app.site_portal_domain_setting_state import (
    MAX_URL_FIELD_LENGTH,
    SitePortalDomainSettingStateError,
    project_site_portal_domain_setting_state,
)


class SitePortalDomainSettingStateTests(unittest.TestCase):
    def client(self):
        return OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))

    def test_explicit_true_ignores_url_and_does_not_emit_any_value(self):
        raw_url = "https://private.example/private/path?secret=value"
        result = project_site_portal_domain_setting_state({"autoRefresh": True, "url": raw_url})
        self.assertTrue(result["data"]["auto_refresh_enabled"])
        self.assertEqual(result["data"]["auto_refresh_state"], "present")
        self.assertFalse(result["data"]["url_applicable"])
        self.assertEqual(result["data"]["url_state"], "not_applicable")
        self.assertIsNone(result["data"]["url_configured"])
        self.assertFalse(result["partial"])
        self.assertNotIn(raw_url, repr(result))
        self.assertNotIn("private.example", repr(result))

    def test_explicit_false_reports_only_nonempty_url_presence(self):
        configured = project_site_portal_domain_setting_state({
            "autoRefresh": False, "url": "https://private.example/path"})
        self.assertFalse(configured["data"]["auto_refresh_enabled"])
        self.assertTrue(configured["data"]["url_applicable"])
        self.assertEqual(configured["data"]["url_state"], "present")
        self.assertTrue(configured["data"]["url_configured"])
        self.assertNotIn("private.example", repr(configured))
        empty = project_site_portal_domain_setting_state({"autoRefresh": False, "url": ""})
        self.assertEqual(empty["data"]["url_state"], "present")
        self.assertFalse(empty["data"]["url_configured"])
        self.assertFalse(empty["partial"])

    def test_missing_or_invalid_auto_refresh_leaves_url_uninspected(self):
        missing = project_site_portal_domain_setting_state({"url": "private-uninspected"})
        self.assertEqual(missing["data"]["auto_refresh_state"], "missing")
        self.assertIsNone(missing["data"]["auto_refresh_enabled"])
        self.assertIsNone(missing["data"]["url_applicable"])
        self.assertEqual(missing["data"]["url_state"], "not_evaluated")
        self.assertIsNone(missing["data"]["url_configured"])
        self.assertEqual(missing["data"]["missing_field_count"], 1)
        invalid = project_site_portal_domain_setting_state({
            "autoRefresh": 1, "url": "private-uninspected"})
        self.assertEqual(invalid["data"]["auto_refresh_state"], "invalid")
        self.assertEqual(invalid["data"]["url_state"], "not_evaluated")
        self.assertEqual(invalid["data"]["invalid_field_count"], 1)
        self.assertNotIn("private-uninspected", repr(missing))
        self.assertNotIn("private-uninspected", repr(invalid))

    def test_false_with_missing_or_invalid_url_is_distinct(self):
        missing = project_site_portal_domain_setting_state({"autoRefresh": False})
        self.assertEqual(missing["data"]["url_state"], "missing")
        self.assertIsNone(missing["data"]["url_configured"])
        self.assertEqual(missing["data"]["missing_field_count"], 1)
        invalid_values = (None, 5, "x" * (MAX_URL_FIELD_LENGTH + 1), "bad\nvalue")
        for value in invalid_values:
            with self.subTest(value_type=type(value).__name__):
                invalid = project_site_portal_domain_setting_state(
                    {"autoRefresh": False, "url": value})
                self.assertEqual(invalid["data"]["url_state"], "invalid")
                self.assertIsNone(invalid["data"]["url_configured"])
                self.assertEqual(invalid["data"]["invalid_field_count"], 1)
                self.assertTrue(invalid["partial"])

    def test_extra_fields_are_counted_and_values_redacted(self):
        result = project_site_portal_domain_setting_state({
            "autoRefresh": False, "url": "https://secret.example", "extra": "secret-extra"})
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("secret.example", repr(result))
        self.assertNotIn("secret-extra", repr(result))

    def test_malformed_root_fails_closed(self):
        for result in (None, [], {"autoRefresh": False, "url": "x", **{
                str(i): i for i in range(8)}}):
            with self.subTest(shape=type(result).__name__):
                with self.assertRaises(SitePortalDomainSettingStateError):
                    project_site_portal_domain_setting_state(result)

    def test_exact_site_get_errors_and_route_guard(self):
        client = self.client()
        site_ref = "a" * 24
        client._site_ids_by_ref = {site_ref: "site-safe"}
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "autoRefresh": False, "url": "https://hidden.example/path"}}) as request:
            result = client.read_site_portal_domain_setting_state(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-safe/portal/setting/domain",
            token="test-token")
        self.assertTrue(result["data"]["url_configured"])
        self.assertNotIn("hidden.example", repr(result))
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", side_effect=OpenApiError("transport_error")):
            with self.assertRaisesRegex(OpenApiError, "transport_error"):
                client.read_site_portal_domain_setting_state(site_ref)
        self.assertTrue(client._site_portal_domain_setting_state_request_valid(
            "/openapi/v1/ctrl/sites/site-safe/portal/setting/domain"))
        for path in ("/openapi/v1/other/sites/site-safe/portal/setting/domain",
                     "/openapi/v1/ctrl/sites/site-safe/portal/setting/domain?x=1"):
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET", path)

    def test_registry_maps_only_site_read(self):
        operation = REGISTRY.get("site_portal_domain_setting_state")
        self.assertEqual(operation.public_template,
                         "/v1/sites/{site_ref}/portal-domain-setting-summary")
        self.assertEqual(operation.upstream_template,
                         "/openapi/v1/{controller_id}/sites/{site_id}/portal/setting/domain")
        path = f"/v1/sites/{'a' * 24}/portal-domain-setting-summary"
        route, bindings = REGISTRY.match("GET", path)
        self.assertEqual(route.operation_id, "site_portal_domain_setting_state")
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24})
        for method, shadow in (("POST", path), ("GET", path + "-shadow")):
            with self.assertRaises(RegistryError):
                REGISTRY.match(method, shadow)

    def test_capability_is_registered_without_live_support_claim(self):
        item = next(row for row in self.client().capabilities()["items"]
                    if row["operation"] == "site_portal_domain_setting_state")
        self.assertEqual(item["support_state"], "unknown")
        self.assertEqual(item["runtime_evidence_count"], 0)


if __name__ == "__main__":
    unittest.main()
