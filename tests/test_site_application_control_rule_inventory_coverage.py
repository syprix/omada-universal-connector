import json
import unittest
from unittest.mock import patch

from app.operation_registry import REGISTRY, RegistryError
from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient
from app.site_application_control_rule_inventory_coverage import (
    MISSING_RULE_INVENTORY_RESULT,
    SiteApplicationControlRuleInventoryError,
    project_site_application_control_rule_inventory_coverage,
)


class OpaqueRules(list):
    def __iter__(self):
        raise AssertionError("rule objects must remain opaque")


class SiteApplicationControlRuleInventoryCoverageTests(unittest.TestCase):
    def client(self, page_size=100):
        return OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=page_size))

    def test_missing_total_stays_null_and_explicit_zero_stays_zero(self):
        missing = project_site_application_control_rule_inventory_coverage({
            "currentPage": 1, "currentSize": 0, "data": []})
        zero = project_site_application_control_rule_inventory_coverage({
            "totalRows": 0, "currentPage": 1, "currentSize": 0, "data": []})
        self.assertIsNone(missing["reported_total_row_count"])
        self.assertTrue(missing["partial"])
        self.assertEqual(missing["pagination_field_coverage"]["totalRows"]["missing"], 1)
        self.assertEqual(zero["reported_total_row_count"], 0)
        self.assertFalse(zero["partial"])
        for value in (missing, zero):
            json.dumps(value, allow_nan=False)
        with self.assertRaises(SiteApplicationControlRuleInventoryError):
            project_site_application_control_rule_inventory_coverage({
                "totalRows": None, "currentPage": 1, "currentSize": 0, "data": []})

    def test_documented_fields_are_counted_but_rule_fields_are_counted_and_applications_remain_opaque(self):
        projected = project_site_application_control_rule_inventory_coverage({
            "totalRows": 2, "currentPage": 1, "currentSize": 2,
            "data": [
                {"ruleId": 4, "ruleName": "private-name", "schedule": "private-schedule", "qos": True, "qosClass": 2,
                 "applications": OpaqueRules([{"applicationId": 99}])},
                {"ruleId": True, "ruleName": 17, "qos": 1, "qosClass": True, "applications": "invalid-shape", "extension": "ignored"},
            ]})
        self.assertEqual(projected["page_state"], "first_page_complete")
        self.assertEqual(projected["rule_field_coverage"], {
            "ruleId": {"present": 2, "type_valid": 1, "missing": 0, "invalid": 1},
            "ruleName": {"present": 2, "type_valid": 1, "missing": 0, "invalid": 1},
            "schedule": {"present": 1, "type_valid": 1, "missing": 1, "invalid": 0},
            "qos": {"present": 2, "type_valid": 1, "missing": 0, "invalid": 1},
            "qosClass": {"present": 2, "type_valid": 1, "missing": 0, "invalid": 1},
            "applications": {"present": 2, "type_valid": 1, "missing": 0, "invalid": 1},
        })
        self.assertEqual(projected["unknown_field_count"], 1)
        self.assertTrue(projected["partial"])
        self.assertFalse(projected["applications_and_rule_values_returned"])
        for secret in ("private-name", "private-description", "private-rule", '"ruleId": 4', '"applications":'):
            self.assertNotIn(secret, repr(projected))

    def test_empty_result_missing_result_invalid_and_partial_page(self):
        missing = project_site_application_control_rule_inventory_coverage(
            MISSING_RULE_INVENTORY_RESULT)
        self.assertEqual(missing["source_state"], "result_missing")
        partial = project_site_application_control_rule_inventory_coverage({
            "totalRows": 3, "currentPage": 1, "currentSize": 1,
            "data": [{"ruleId": 3, "ruleName": "x", "description": "d", "applications": []}]})
        self.assertEqual(partial["page_state"], "first_page_partial")
        self.assertEqual(partial["reported_remaining_row_count"], 2)
        self.assertTrue(partial["partial"])
        for total in (True, -1, 1 << 63):
            with self.subTest(total=total), self.assertRaises(SiteApplicationControlRuleInventoryError):
                project_site_application_control_rule_inventory_coverage({
                    "totalRows": total, "currentPage": 1, "currentSize": 0, "data": []})
        with self.assertRaises(SiteApplicationControlRuleInventoryError):
            project_site_application_control_rule_inventory_coverage({
                "totalRows": 101, "currentPage": 1, "currentSize": 101,
                "data": [{"ruleId": n} for n in range(101)]})
        with self.assertRaises(SiteApplicationControlRuleInventoryError):
            project_site_application_control_rule_inventory_coverage({
                "totalRows": 2, "currentPage": 2, "currentSize": 1,
                "data": [{"ruleId": 1}]})

    def test_exact_fixed_first_page_and_no_search_or_detail_request(self):
        client = self.client(page_size=200)
        site_ref = "a" * 24
        client._site_ids_by_ref = {site_ref: "site-safe"}
        response = {"errorCode": 0, "result": {
            "totalRows": 0, "currentPage": 1, "currentSize": 0, "data": []}}
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value=response) as request:
            result = client.read_site_application_control_rule_inventory_coverage(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-safe/applicationControl/rules?page=1&pageSize=100",
            token="test-token")
        self.assertEqual(result["reported_total_row_count"], 0)
        self.assertEqual(result["returned_row_count"], 0)

    def test_site_validation_and_fixed_rules_path_allowlist(self):
        client = self.client()
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_application_control_rule_inventory_coverage("a" * 24)
            request.assert_not_called()
        valid = "/openapi/v1/ctrl/sites/site-safe/applicationControl/rules?page=1&pageSize=100"
        self.assertTrue(client._site_application_control_rules_request_valid(valid))
        for rejected in (valid + "&searchKey=x", valid.replace("page=1", "page=2"),
                         valid.replace("pageSize=100", "pageSize=101"),
                         valid.replace("/ctrl/", "/other/")):
            self.assertFalse(client._site_application_control_rules_request_valid(rejected))
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET", rejected)

    def test_registry_is_one_fixed_site_get(self):
        operation = REGISTRY.get("site_application_control_rule_inventory_coverage")
        self.assertEqual(operation.public_template,
                         "/v1/sites/{site_ref}/application-control/rule-inventory/coverage")
        self.assertEqual(operation.upstream_template,
                         "/openapi/v1/{controller_id}/sites/{site_id}/applicationControl/rules")
        route, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{'a' * 24}/application-control/rule-inventory/coverage")
        self.assertEqual(route.operation_id, "site_application_control_rule_inventory_coverage")
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24})
        with self.assertRaises(RegistryError):
            REGISTRY.match("POST", f"/v1/sites/{'a' * 24}/application-control/rule-inventory/coverage")


if __name__ == "__main__":
    unittest.main()
