import json
import unittest
from unittest.mock import patch

from app.operation_registry import REGISTRY, RegistryError
from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient
from app.site_application_control_application_catalog import (
    MISSING_APPLICATION_CATALOG_RESULT,
    SiteApplicationControlApplicationCatalogError,
    project_site_application_control_application_catalog,
)


class SiteApplicationControlApplicationCatalogTests(unittest.TestCase):
    def client(self, page_size=100):
        return OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=page_size))

    def test_empty_missing_total_and_missing_result_are_json_serializable(self):
        empty = project_site_application_control_application_catalog({
            "totalRows": 0, "currentPage": 0, "currentSize": 0, "data": []})
        self.assertEqual(empty["page_state"], "empty")
        self.assertFalse(empty["partial"])
        missing_total = project_site_application_control_application_catalog({
            "currentPage": 1, "currentSize": 0, "data": []})
        self.assertEqual(missing_total["source_state"], "empty_total_unknown")
        self.assertIsNone(missing_total["reported_total_row_count"])
        self.assertTrue(missing_total["partial"])
        missing_rows_total = project_site_application_control_application_catalog({
            "currentPage": 1, "currentSize": 1,
            "data": [{"applicationId": 4, "applicationName": "private-name"}]})
        self.assertEqual(missing_rows_total["returned_row_count"], 1)
        self.assertIsNone(missing_rows_total["reported_total_row_count"])
        missing_result = project_site_application_control_application_catalog(
            MISSING_APPLICATION_CATALOG_RESULT)
        for projected in (empty, missing_total, missing_rows_total, missing_result):
            json.dumps(projected, allow_nan=False)
        self.assertEqual(missing_result["source_state"], "result_missing")

    def test_id_schema_coverage_only_does_not_return_ids_or_labels(self):
        projected = project_site_application_control_application_catalog({
            "totalRows": 5, "currentPage": 1, "currentSize": 5,
            "data": [
                {"applicationId": 0, "applicationName": "secret label"},
                {"applicationId": (1 << 31) - 1, "description": "secret description"},
                {"applicationId": 8}, {"applicationId": 8},
                {"applicationId": True, "family": "secret family"},
            ]})
        self.assertEqual(projected["application_id_coverage"], {
            "present": 5, "type_valid": 4, "missing": 0, "invalid": 1})
        self.assertEqual(projected["unique_application_id_count"], 3)
        self.assertEqual(projected["duplicate_application_id_count"], 1)
        self.assertTrue(projected["partial"])
        self.assertFalse(projected["application_identifiers_and_labels_returned"])
        for secret in ("secret label", "secret description", "secret family", '"applicationId": 8'):
            self.assertNotIn(secret, repr(projected))

    def test_page_coverage_missing_invalid_and_overflow_metadata(self):
        partial = project_site_application_control_application_catalog({
            "totalRows": 140, "currentPage": 1, "currentSize": 100,
            "data": [{"applicationId": n} for n in range(100)]})
        self.assertEqual(partial["page_state"], "first_page_partial")
        self.assertEqual(partial["reported_remaining_row_count"], 40)
        self.assertTrue(partial["partial"])
        for value in (True, -1, 1 << 63):
            with self.subTest(total=value), self.assertRaises(
                    SiteApplicationControlApplicationCatalogError):
                project_site_application_control_application_catalog({
                    "totalRows": value, "currentPage": 1, "currentSize": 0, "data": []})
        with self.assertRaises(SiteApplicationControlApplicationCatalogError):
            project_site_application_control_application_catalog({
                "totalRows": 101, "currentPage": 1, "currentSize": 101,
                "data": [{"applicationId": n} for n in range(101)]})
        with self.assertRaises(SiteApplicationControlApplicationCatalogError):
            project_site_application_control_application_catalog({
                "totalRows": 1, "currentPage": 2, "currentSize": 1,
                "data": [{"applicationId": 1}]})

    def test_exact_fixed_first_page_site_bound_get_and_no_selector_values(self):
        client = self.client(page_size=200)
        site_ref = "a" * 24
        client._site_ids_by_ref = {site_ref: "site-safe"}
        response = {"errorCode": 0, "result": {"totalRows": 1, "currentPage": 1,
                    "currentSize": 1, "data": [{"applicationId": 24,
                    "applicationName": "private-label"}]}}
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value=response) as request:
            result = client.read_site_application_control_application_catalog(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-safe/applicationControl/applications?page=1&pageSize=100",
            token="test-token")
        self.assertEqual(result["application_id_coverage"]["type_valid"], 1)
        self.assertNotIn("private-label", repr(result))
        self.assertNotIn('"applicationId": 24', repr(result))

    def test_site_validation_error_code_and_fixed_path_allowlist(self):
        client = self.client()
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_application_control_application_catalog("a" * 24)
            request.assert_not_called()
        site_ref = "b" * 24
        client._site_ids_by_ref = {site_ref: "site-safe"}
        for error in ("openapi_error_-35113", "openapi_error_generic"):
            with patch.object(client, "_access_token", return_value="test-token"), \
                    patch.object(client, "_request_json", side_effect=OpenApiError(error)) as request:
                with self.assertRaisesRegex(OpenApiError, error):
                    client.read_site_application_control_application_catalog(site_ref)
                request.assert_called_once()
        valid = "/openapi/v1/ctrl/sites/site-safe/applicationControl/applications?page=1&pageSize=100"
        self.assertTrue(client._site_application_control_applications_request_valid(valid))
        for rejected in (valid + "&searchKey=x", valid + "&filtersFamilyId=1",
                         valid.replace("page=1", "page=2"), valid.replace("pageSize=100", "pageSize=101"),
                         valid.replace("/ctrl/", "/other/")):
            self.assertFalse(client._site_application_control_applications_request_valid(rejected))
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET", rejected)

    def test_registry_is_one_fixed_get(self):
        op = REGISTRY.get("site_application_control_application_catalog")
        self.assertEqual(op.public_template,
                         "/v1/sites/{site_ref}/application-control/application-catalog")
        self.assertEqual(op.upstream_template,
                         "/openapi/v1/{controller_id}/sites/{site_id}/applicationControl/applications")
        route, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{'a' * 24}/application-control/application-catalog")
        self.assertEqual(route.operation_id, "site_application_control_application_catalog")
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24})
        for method, path in (
                ("POST", f"/v1/sites/{'a' * 24}/application-control/application-catalog"),
                ("GET", f"/v1/sites/{'a' * 24}/application-control/application-catalog/extra")):
            with self.assertRaises(RegistryError):
                REGISTRY.match(method, path)


if __name__ == "__main__":
    unittest.main()
