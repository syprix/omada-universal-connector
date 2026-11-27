import json
import unittest
from unittest.mock import patch

from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient
from app.operation_registry import REGISTRY, RegistryError
from app.site_hotspot_voucher_group_options_coverage import (
    MISSING_VOUCHER_GROUP_OPTIONS_RESULT,
    SiteHotspotVoucherGroupOptionsCoverageError,
    project_site_hotspot_voucher_group_options_coverage,
)


class SiteHotspotVoucherGroupOptionsCoverageTests(unittest.TestCase):
    def client(self, page_size=100):
        return OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=page_size))

    def test_missing_total_is_null_and_explicit_zero_is_complete(self):
        missing = project_site_hotspot_voucher_group_options_coverage({
            "currentPage": 1, "currentSize": 0, "data": []})
        zero = project_site_hotspot_voucher_group_options_coverage({
            "totalRows": 0, "currentPage": 1, "currentSize": 0, "data": []})
        self.assertIsNone(missing["reported_total_row_count"])
        self.assertEqual(missing["page_state"], "empty_total_unknown")
        self.assertTrue(missing["partial"])
        self.assertEqual(missing["pagination_field_coverage"]["totalRows"],
                         {"present": 0, "type_valid": 0, "missing": 1, "invalid": 0})
        self.assertEqual(zero["reported_total_row_count"], 0)
        self.assertEqual(zero["page_state"], "empty")
        self.assertFalse(zero["partial"])
        self.assertEqual(zero["group_field_coverage"], {
            "groupId": {"present": 0, "type_valid": 0, "missing": 0, "invalid": 0},
            "name": {"present": 0, "type_valid": 0, "missing": 0, "invalid": 0},
        })
        for value in (missing, zero):
            json.dumps(value, allow_nan=False)

    def test_only_documented_group_field_presence_and_types_are_returned(self):
        projected = project_site_hotspot_voucher_group_options_coverage({
            "totalRows": 2, "currentPage": 1, "currentSize": 2,
            "data": [
                {"groupId": "private-group-id", "name": "private-group-name"},
                {"groupId": 17, "name": None, "voucherCode": "private-voucher-code"},
            ]})
        self.assertEqual(projected["page_state"], "first_page_complete")
        self.assertEqual(projected["group_field_coverage"], {
            "groupId": {"present": 2, "type_valid": 1, "missing": 0, "invalid": 1},
            "name": {"present": 2, "type_valid": 1, "missing": 0, "invalid": 1},
        })
        self.assertEqual(projected["unknown_field_count"], 1)
        self.assertTrue(projected["partial"])
        self.assertFalse(projected["voucher_group_values_returned"])
        for private_value in ("private-group-id", "private-group-name", "private-voucher-code"):
            self.assertNotIn(private_value, repr(projected))

    def test_missing_result_partial_page_and_strict_page_bounds(self):
        missing = project_site_hotspot_voucher_group_options_coverage(
            MISSING_VOUCHER_GROUP_OPTIONS_RESULT)
        self.assertEqual(missing["source_state"], "result_missing")
        partial = project_site_hotspot_voucher_group_options_coverage({
            "totalRows": 2, "currentPage": 1, "currentSize": 1,
            "data": [{"groupId": "x", "name": "y"}]})
        self.assertEqual(partial["page_state"], "first_page_partial")
        self.assertEqual(partial["reported_remaining_row_count"], 1)
        self.assertTrue(partial["partial"])
        for total in (True, -1, 1 << 63):
            with self.subTest(total=total), self.assertRaises(SiteHotspotVoucherGroupOptionsCoverageError):
                project_site_hotspot_voucher_group_options_coverage({
                    "totalRows": total, "currentPage": 1, "currentSize": 0, "data": []})
        with self.assertRaises(SiteHotspotVoucherGroupOptionsCoverageError):
            project_site_hotspot_voucher_group_options_coverage({
                "totalRows": 2, "currentPage": 2, "currentSize": 1,
                "data": [{"groupId": "x", "name": "y"}]})
        with self.assertRaises(SiteHotspotVoucherGroupOptionsCoverageError):
            project_site_hotspot_voucher_group_options_coverage({
                "totalRows": 101, "currentPage": 1, "currentSize": 101,
                "data": [{"groupId": "x", "name": "y"}] * 101})

    def test_client_caps_first_page_and_never_adds_other_query_or_detail(self):
        client = self.client(page_size=200)
        site_ref = "a" * 24
        client._site_ids_by_ref = {site_ref: "site-safe"}
        response = {"errorCode": 0, "result": {
            "totalRows": 0, "currentPage": 1, "currentSize": 0, "data": []}}
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value=response) as request:
            result = client.read_site_hotspot_voucher_group_options_coverage(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-safe/hotspot/voucher-group-options?page=1&pageSize=100",
            token="test-token")
        self.assertEqual(result["reported_total_row_count"], 0)
        self.assertEqual(result["returned_row_count"], 0)

    def test_site_binding_route_allowlist_and_registry_are_fixed(self):
        client = self.client()
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_hotspot_voucher_group_options_coverage("a" * 24)
            request.assert_not_called()
        valid = ("/openapi/v1/ctrl/sites/site-safe/hotspot/voucher-group-options"
                 "?page=1&pageSize=100")
        for rejected in (valid + "&voucherCode=x", valid.replace("page=1", "page=2"),
                         valid.replace("pageSize=100", "pageSize=101"),
                         valid.replace("/ctrl/", "/other/")):
            self.assertFalse(client._site_hotspot_voucher_group_options_request_valid(rejected))
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET", rejected)
        operation = REGISTRY.get("site_hotspot_voucher_group_options_coverage")
        self.assertEqual(operation.public_template,
                         "/v1/sites/{site_ref}/hotspot/voucher-group-options/coverage")
        route, bindings = REGISTRY.match(
            "GET", f"/v1/sites/{'a' * 24}/hotspot/voucher-group-options/coverage")
        self.assertEqual(route.operation_id, "site_hotspot_voucher_group_options_coverage")
        self.assertEqual(route.max_items, 100)
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24})
        with self.assertRaises(RegistryError):
            REGISTRY.match("POST", f"/v1/sites/{'a' * 24}/hotspot/voucher-group-options/coverage")


if __name__ == "__main__":
    unittest.main()
