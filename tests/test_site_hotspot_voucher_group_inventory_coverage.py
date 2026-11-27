import json
import unittest
from unittest.mock import patch

from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient
from app.operation_registry import REGISTRY, RegistryError
from app.site_hotspot_voucher_group_inventory_coverage import (
    SiteVoucherGroupInventoryCoverageError,
    project_site_voucher_group_inventory_coverage,
)


def row(**overrides):
    result = {"id": "private-group-id", "name": "private-group-name",
              "unusedCount": 101, "usedCount": 202, "inUseCount": 303,
              "expiredCount": 404, "totalCount": 505,
              "unitPrice": "private-price", "currency": "private-currency",
              "portalNames": ["private-portal"]}
    result.update(overrides)
    return result


class SiteVoucherGroupInventoryCoverageTests(unittest.TestCase):
    def client(self, page_size=200):
        return OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=page_size))

    def test_redacts_values_and_reports_only_documented_count_field_shapes(self):
        projected = project_site_voucher_group_inventory_coverage({
            "totalRows": 1, "currentPage": 1, "currentSize": 1, "data": [row()]},
            page_size=100)
        self.assertEqual(projected["page_state"], "first_page_complete")
        self.assertFalse(projected["partial"])
        self.assertEqual(projected["voucher_count_field_coverage"], {
            key: {"present": 1, "type_valid": 1, "missing": 0, "invalid": 0}
            for key in ("unusedCount", "usedCount", "inUseCount", "expiredCount", "totalCount")})
        serialized = json.dumps(projected, allow_nan=False)
        for marker in ("private-group-id", "private-group-name", "private-price",
                       "private-currency", "private-portal", "101", "202", "303", "404", "505"):
            self.assertNotIn(marker, serialized)
        self.assertFalse(projected["voucher_group_values_returned"])

    def test_missing_total_is_null_and_partial_but_explicit_empty_zero_is_complete(self):
        missing = project_site_voucher_group_inventory_coverage({
            "currentPage": 1, "currentSize": 0, "data": []})
        zero = project_site_voucher_group_inventory_coverage({
            "totalRows": 0, "currentPage": 1, "currentSize": 0, "data": []})
        self.assertIsNone(missing["reported_total_row_count"])
        self.assertTrue(missing["partial"])
        self.assertEqual(zero["page_state"], "empty")
        self.assertFalse(zero["partial"])
        self.assertEqual(zero["reported_remaining_row_count"], 0)
        json.dumps(missing, allow_nan=False)
        json.dumps(zero, allow_nan=False)

    def test_first_page_and_missing_or_invalid_counter_fields_are_partial(self):
        sparse_row = row(unusedCount="redacted", usedCount=True)
        del sparse_row["inUseCount"]
        partial = project_site_voucher_group_inventory_coverage({
            "totalRows": 3, "currentPage": 1, "currentSize": 1,
            "data": [sparse_row]}, page_size=100)
        self.assertEqual(partial["page_state"], "first_page_partial")
        self.assertEqual(partial["reported_remaining_row_count"], 2)
        self.assertTrue(partial["partial"])
        coverage = partial["voucher_count_field_coverage"]
        self.assertEqual(coverage["unusedCount"]["invalid"], 1)
        self.assertEqual(coverage["usedCount"]["invalid"], 1)
        self.assertEqual(coverage["inUseCount"]["missing"], 1)

    def test_unknown_keys_are_counted_without_reading_their_values(self):
        projected = project_site_voucher_group_inventory_coverage({
            "totalRows": 1, "currentPage": 1, "currentSize": 1,
            "data": [row(unreviewedField="do-not-read-this-value")]})
        self.assertEqual(projected["unknown_field_count"], 1)
        self.assertTrue(projected["partial"])
        self.assertNotIn("do-not-read-this-value", json.dumps(projected))

    def test_inconsistent_page_metadata_is_rejected_without_options_reader_exception(self):
        bad = (
            {"totalRows": 0, "currentPage": 1, "currentSize": 1, "data": [row()]},
            {"totalRows": 2, "currentPage": 1, "currentSize": 0, "data": []},
            {"totalRows": 0, "currentPage": 0, "currentSize": 0, "data": []},
            {"totalRows": 2, "currentPage": 2, "currentSize": 1, "data": [row()]},
        )
        for response in bad:
            with self.subTest(response=response), self.assertRaises(
                    SiteVoucherGroupInventoryCoverageError):
                project_site_voucher_group_inventory_coverage(response)

    def test_page_size_is_strict_and_counter_types_are_counted(self):
        for size in (0, 101, True, 1.0):
            with self.subTest(size=size), self.assertRaises(
                    SiteVoucherGroupInventoryCoverageError):
                project_site_voucher_group_inventory_coverage({}, page_size=size)
        for value in (True, -1, (1 << 31), "5", 1.0):
            with self.subTest(value_type=type(value).__name__):
                projected = project_site_voucher_group_inventory_coverage({
                    "totalRows": 1, "currentPage": 1, "currentSize": 1,
                    "data": [row(unusedCount=value)]})
                self.assertEqual(projected["voucher_count_field_coverage"][
                    "unusedCount"]["invalid"], 1)
                self.assertTrue(projected["partial"])

    def test_client_caps_page_and_uses_only_the_fixed_site_get(self):
        client = self.client(page_size=200)
        site_ref = "a" * 24
        client._site_ids_by_ref = {site_ref: "site-safe"}
        payload = {"errorCode": 0, "result": {
            "totalRows": 0, "currentPage": 1, "currentSize": 0, "data": []}}
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value=payload) as request:
            result = client.read_site_hotspot_voucher_group_inventory_coverage(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-safe/hotspot/voucher-groups?page=1&pageSize=100",
            token="test-token")
        self.assertEqual(result["reported_total_row_count"], 0)

    def test_site_binding_fixed_query_and_registry_route(self):
        client = self.client()
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_hotspot_voucher_group_inventory_coverage("a" * 24)
            request.assert_not_called()
        valid = "/openapi/v1/ctrl/sites/site-safe/hotspot/voucher-groups?page=1&pageSize=100"
        for rejected in (valid + "&searchKey=x", valid + "&sorts.name=asc",
                         valid.replace("page=1", "page=2"),
                         valid.replace("pageSize=100", "pageSize=101"),
                         valid.replace("/ctrl/", "/other/")):
            self.assertFalse(client._site_hotspot_voucher_group_inventory_request_valid(rejected))
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET", rejected)
        operation = REGISTRY.get("site_hotspot_voucher_group_inventory_coverage")
        self.assertEqual(operation.public_template,
                         "/v1/sites/{site_ref}/hotspot/voucher-groups/coverage")
        route, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{'a' * 24}/hotspot/voucher-groups/coverage")
        self.assertEqual(route.operation_id, "site_hotspot_voucher_group_inventory_coverage")
        self.assertEqual(route.upstream_template,
                         "/openapi/v1/{controller_id}/sites/{site_id}/hotspot/voucher-groups")
        self.assertEqual(route.max_items, 100)
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24})
        with self.assertRaises(RegistryError):
            REGISTRY.match("POST", f"/v1/sites/{'a' * 24}/hotspot/voucher-groups/coverage")


if __name__ == "__main__":
    unittest.main()
