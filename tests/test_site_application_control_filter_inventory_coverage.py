import json
import unittest
from unittest.mock import patch

from app.operation_registry import REGISTRY, RegistryError
from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient
from app.site_application_control_filter_inventory_coverage import (
    MISSING_FILTER_INVENTORY_RESULT,
    SiteApplicationControlFilterInventoryError,
    project_site_application_control_filter_inventory_coverage,
)


class OpaqueRules(list):
    def __iter__(self):
        raise AssertionError("rule objects must remain opaque")


class SiteApplicationControlFilterInventoryCoverageTests(unittest.TestCase):
    def client(self, page_size=100):
        return OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=page_size))

    def test_missing_total_stays_null_and_explicit_zero_stays_zero(self):
        missing = project_site_application_control_filter_inventory_coverage({
            "currentPage": 1, "currentSize": 0, "data": []})
        zero = project_site_application_control_filter_inventory_coverage({
            "totalRows": 0, "currentPage": 1, "currentSize": 0, "data": []})
        self.assertIsNone(missing["reported_total_row_count"])
        self.assertTrue(missing["partial"])
        self.assertEqual(missing["pagination_field_coverage"]["totalRows"]["missing"], 1)
        self.assertEqual(zero["reported_total_row_count"], 0)
        self.assertFalse(zero["partial"])
        for value in (missing, zero):
            json.dumps(value, allow_nan=False)
        with self.assertRaises(SiteApplicationControlFilterInventoryError):
            project_site_application_control_filter_inventory_coverage({
                "totalRows": None, "currentPage": 1, "currentSize": 0, "data": []})

    def test_documented_fields_are_counted_but_filter_values_and_rule_items_are_not_read(self):
        projected = project_site_application_control_filter_inventory_coverage({
            "totalRows": 2, "currentPage": 1, "currentSize": 2,
            "data": [
                {"filterId": 4, "filterName": "private-name", "description": "private-description",
                 "rules": OpaqueRules([{"ruleName": "private-rule", "ruleId": 99}])},
                {"filterId": True, "filterName": 17, "rules": "invalid-shape", "extension": "ignored"},
            ]})
        self.assertEqual(projected["page_state"], "first_page_complete")
        self.assertEqual(projected["filter_field_coverage"], {
            "filterId": {"present": 2, "type_valid": 1, "missing": 0, "invalid": 1},
            "filterName": {"present": 2, "type_valid": 1, "missing": 0, "invalid": 1},
            "description": {"present": 1, "type_valid": 1, "missing": 1, "invalid": 0},
            "rules": {"present": 2, "type_valid": 1, "missing": 0, "invalid": 1},
        })
        self.assertEqual(projected["unknown_field_count"], 1)
        self.assertTrue(projected["partial"])
        self.assertFalse(projected["filter_values_and_rule_objects_returned"])
        for secret in ("private-name", "private-description", "private-rule", '"filterId": 4', '"rules":'):
            self.assertNotIn(secret, repr(projected))

    def test_empty_result_missing_result_invalid_and_partial_page(self):
        missing = project_site_application_control_filter_inventory_coverage(
            MISSING_FILTER_INVENTORY_RESULT)
        self.assertEqual(missing["source_state"], "result_missing")
        partial = project_site_application_control_filter_inventory_coverage({
            "totalRows": 3, "currentPage": 1, "currentSize": 1,
            "data": [{"filterId": 3, "filterName": "x", "description": "d", "rules": []}]})
        self.assertEqual(partial["page_state"], "first_page_partial")
        self.assertEqual(partial["reported_remaining_row_count"], 2)
        self.assertTrue(partial["partial"])
        for total in (True, -1, 1 << 63):
            with self.subTest(total=total), self.assertRaises(SiteApplicationControlFilterInventoryError):
                project_site_application_control_filter_inventory_coverage({
                    "totalRows": total, "currentPage": 1, "currentSize": 0, "data": []})
        with self.assertRaises(SiteApplicationControlFilterInventoryError):
            project_site_application_control_filter_inventory_coverage({
                "totalRows": 101, "currentPage": 1, "currentSize": 101,
                "data": [{"filterId": n} for n in range(101)]})
        with self.assertRaises(SiteApplicationControlFilterInventoryError):
            project_site_application_control_filter_inventory_coverage({
                "totalRows": 2, "currentPage": 2, "currentSize": 1,
                "data": [{"filterId": 1}]})

    def test_exact_fixed_first_page_and_no_search_or_detail_request(self):
        client = self.client(page_size=200)
        site_ref = "a" * 24
        client._site_ids_by_ref = {site_ref: "site-safe"}
        response = {"errorCode": 0, "result": {
            "totalRows": 0, "currentPage": 1, "currentSize": 0, "data": []}}
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value=response) as request:
            result = client.read_site_application_control_filter_inventory_coverage(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-safe/applicationControl/filters?page=1&pageSize=100",
            token="test-token")
        self.assertEqual(result["reported_total_row_count"], 0)
        self.assertEqual(result["returned_row_count"], 0)

    def test_site_validation_and_fixed_path_allowlist(self):
        client = self.client()
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_application_control_filter_inventory_coverage("a" * 24)
            request.assert_not_called()
        valid = "/openapi/v1/ctrl/sites/site-safe/applicationControl/filters?page=1&pageSize=100"
        for rejected in (valid + "&searchKey=x", valid.replace("page=1", "page=2"),
                         valid.replace("pageSize=100", "pageSize=101"),
                         valid.replace("/ctrl/", "/other/")):
            self.assertFalse(client._site_application_control_filters_request_valid(rejected))
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET", rejected)

    def test_registry_is_one_fixed_site_get(self):
        operation = REGISTRY.get("site_application_control_filter_inventory_coverage")
        self.assertEqual(operation.public_template,
                         "/v1/sites/{site_ref}/application-control/filter-inventory/coverage")
        self.assertEqual(operation.upstream_template,
                         "/openapi/v1/{controller_id}/sites/{site_id}/applicationControl/filters")
        route, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{'a' * 24}/application-control/filter-inventory/coverage")
        self.assertEqual(route.operation_id, "site_application_control_filter_inventory_coverage")
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24})
        with self.assertRaises(RegistryError):
            REGISTRY.match("POST", f"/v1/sites/{'a' * 24}/application-control/filter-inventory/coverage")


if __name__ == "__main__":
    unittest.main()
