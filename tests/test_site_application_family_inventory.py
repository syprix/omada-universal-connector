import unittest
from unittest.mock import patch

from app.operation_registry import REGISTRY, RegistryError
from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient
from app.site_application_family_inventory import (
    SiteApplicationFamilyInventoryError,
    project_site_application_family_inventory,
)


class SiteApplicationFamilyInventoryTests(unittest.TestCase):
    def client(self):
        return OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))

    def test_empty_valid_zero_and_int32_boundary(self):
        empty = project_site_application_family_inventory([])
        self.assertEqual(empty["data"]["family_refs"], [])
        self.assertFalse(empty["partial"])
        projected = project_site_application_family_inventory([
            {"familyId": 0, "familyName": "omitted", "description": "omitted"},
            {"familyId": (1 << 31) - 1},
        ])
        self.assertEqual(projected["data"]["family_refs"], ["0", str((1 << 31) - 1)])
        self.assertNotIn("omitted", repr(projected))
        for family_ref in projected["data"]["family_refs"]:
            for suffix, expected_operation in (
                    ("applications", "site_category_application_summary"),
                    ("clients", "site_category_client_summary")):
                route, bindings = REGISTRY.match(
                    "GET", f"/v1/sites/{'a' * 24}/application-category-summary/"
                    f"{family_ref}/{suffix}")
                self.assertEqual(route.operation_id, expected_operation)
                self.assertEqual(dict(bindings)["family_id"], family_ref)

    def test_invalid_negative_overrange_duplicate_and_extra_fields_are_partial(self):
        projected = project_site_application_family_inventory([
            {"familyId": -1}, {"familyId": 1 << 31}, {"familyId": True},
            {"familyId": 9}, {"familyId": 9},
            {"familyId": 10, "privateExtra": "must-not-appear"},
            {"familyName": "no id"},
        ])
        self.assertEqual(projected["data"]["family_refs"], ["10"])
        self.assertEqual(projected["data"]["invalid_row_count"], 4)
        self.assertEqual(projected["data"]["duplicate_family_id_count"], 1)
        self.assertEqual(projected["data"]["unknown_field_count"], 1)
        self.assertTrue(projected["partial"])
        self.assertNotIn("privateExtra", repr(projected))
        self.assertNotIn("must-not-appear", repr(projected))

    def test_malformed_rows_and_oversized_lists(self):
        malformed = project_site_application_family_inventory([None, [], {"familyId": "1"}])
        self.assertTrue(malformed["partial"])
        self.assertEqual(malformed["data"]["invalid_row_count"], 3)
        with self.assertRaisesRegex(SiteApplicationFamilyInventoryError, "family_rows_invalid"):
            project_site_application_family_inventory([{"familyId": n} for n in range(101)])
        with self.assertRaises(SiteApplicationFamilyInventoryError):
            project_site_application_family_inventory({"data": []})

    def test_exact_site_bound_get_and_redacted_projection(self):
        client = self.client()
        site_ref = "a" * 24
        client._site_ids_by_ref = {site_ref: "site-safe"}
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={"result": [
                    {"familyId": 7, "familyName": "private-name",
                     "description": "private-description", "extra": "secret-value"}]}) as request:
            result = client.read_site_application_family_inventory(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-safe/applicationControl/families",
            token="test-token")
        self.assertEqual(result["data"]["family_refs"], ["7"])
        self.assertTrue(result["partial"])
        for private_value in ("private-name", "private-description", "secret-value"):
            self.assertNotIn(private_value, repr(result))

    def test_invalid_site_and_controller_errors_do_not_fallback_or_leak_rows(self):
        client = self.client()
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_application_family_inventory("a" * 24)
            request.assert_not_called()
        site_ref = "b" * 24
        client._site_ids_by_ref = {site_ref: "site-safe"}
        for error in ("openapi_error_-35113", "openapi_error_generic"):
            with patch.object(client, "_access_token", return_value="test-token"), \
                    patch.object(client, "_request_json", side_effect=OpenApiError(error)) as request:
                with self.assertRaisesRegex(OpenApiError, error):
                    client.read_site_application_family_inventory(site_ref)
                request.assert_called_once()

    def test_registry_maps_only_fixed_read_path(self):
        op = REGISTRY.get("site_application_family_inventory")
        self.assertEqual(op.public_template, "/v1/sites/{site_ref}/application-families")
        self.assertEqual(op.upstream_template,
                         "/openapi/v1/{controller_id}/sites/{site_id}/applicationControl/families")
        route, bindings = REGISTRY.match("GET", f"/v1/sites/{'a' * 24}/application-families")
        self.assertEqual(route.operation_id, "site_application_family_inventory")
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24})
        with self.assertRaises(RegistryError):
            REGISTRY.match("POST", f"/v1/sites/{'a' * 24}/application-families")
        with self.assertRaises(RegistryError):
            REGISTRY.match("GET", f"/v1/sites/{'a' * 24}/application-families-shadow")
        self.assertTrue(self.client()._site_application_families_request_valid(
            "/openapi/v1/ctrl/sites/site-safe/applicationControl/families"))
        self.assertFalse(self.client()._site_application_families_request_valid(
            "/openapi/v1/other/sites/site-safe/applicationControl/families"))
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client()._request_json(
                "GET", "/openapi/v1/ctrl/sites/site-safe/applicationControl/families?x=1")


if __name__ == "__main__":
    unittest.main()
