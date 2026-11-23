import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_stack_vlan_interface_summary import summarize_stack_vlan_interfaces


class SiteStackVlanInterfaceSummaryTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-internal"

    def test_counts_rows_ids_and_optional_field_coverage_without_values(self):
        rows = [
            {"vlanInterfaceId": "id-1", "vlanInterfaceName": "private-name", "vlanId": 100},
            {"vlanInterfaceId": "id-2", "vlanInterfaceName": "other-name", "vlanId": 200},
            {"vlanInterfaceId": "id-2", "vlanInterfaceName": None, "vlanId": 300},
            {"vlanInterfaceId": "", "vlanId": "invalid"},
            {"vlanInterfaceId": "id-5"},
            {"vlanInterfaceName": "name-only"},
        ]
        result = summarize_stack_vlan_interfaces(rows)
        self.assertEqual(result["reported_interface_count"], 6)
        self.assertEqual(result["interface_id_coverage"], {
            "unique": 3, "duplicate": 1, "missing": 1, "invalid": 1})
        self.assertEqual(result["interface_name_coverage"], {
            "present": 3, "missing": 3, "invalid": 0})
        self.assertEqual(result["vlan_id_coverage"], {
            "present": 3, "missing": 2, "invalid": 1})
        self.assertTrue(result["partial"])
        for secret in ("id-1", "id-2", "private-name", "other-name", "100", "300"):
            self.assertNotIn(secret, repr(result))

    def test_fresh_unique_site_stack_binding_and_exact_read_path(self):
        stack_ref = self.client._opaque_ref("stack", "site-internal:stack-1")
        stack_rows = [{"id": "stack-1"}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_bounded_grid_rows",
                             return_value=(stack_rows, 0)) as inventory, \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": [{"vlanInterfaceId": "hidden-id", "vlanId": 50}],
                }) as request:
            result = self.client.read_site_stack_vlan_interface_summary(
                self.site_ref, stack_ref)
        inventory.assert_called_once_with(
            "/openapi/v1/ctrl/sites/site-internal/stacks", "token", 32,
            require_success_code=True)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-internal/vlan-interface/stack/stack-1",
            token="token")
        self.assertEqual(result["site_ref"], self.site_ref)
        self.assertEqual(result["reported_interface_count"], 1)
        self.assertNotIn("hidden-id", repr(result))

    def test_rejects_unknown_duplicate_or_incomplete_stack_binding(self):
        stack_ref = self.client._opaque_ref("stack", "site-internal:stack-1")
        for rows, omitted, expected in (
                ([{"id": "other"}], 0, "stack_ref_unknown"),
                ([{"id": "stack-1"}, {"id": "stack-1"}], 0,
                 "stack_inventory_ambiguous"),
                ([{"id": "stack-1"}], 1, "stack_inventory_incomplete")):
            with self.subTest(expected=expected), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_read_bounded_grid_rows",
                                 return_value=(rows, omitted)), \
                    patch.object(self.client, "_request_json") as request:
                with self.assertRaises(OpenApiError) as error:
                    self.client.read_site_stack_vlan_interface_summary(
                        self.site_ref, stack_ref)
                self.assertEqual(error.exception.code, expected)
                request.assert_not_called()

    def test_rejects_generic_response_and_oversized_list(self):
        stack_ref = self.client._opaque_ref("stack", "site-internal:stack-1")
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_bounded_grid_rows",
                             return_value=([{"id": "stack-1"}], 0)), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0, "result": {"data": []},
                }):
            with self.assertRaises(OpenApiError):
                self.client.read_site_stack_vlan_interface_summary(self.site_ref, stack_ref)
        with self.assertRaises(ValueError):
            summarize_stack_vlan_interfaces([{}] * 1001)

    def test_upstream_request_guard_is_site_path_and_controller_bound(self):
        self.assertTrue(self.client._site_stack_vlan_interfaces_request_valid(
            "/openapi/v1/ctrl/sites/site-id/vlan-interface/stack/stack-1"))
        self.assertFalse(self.client._site_stack_vlan_interfaces_request_valid(
            "/openapi/v1/other/sites/site-id/vlan-interface/stack/stack-1"))
        self.assertFalse(self.client._site_stack_vlan_interfaces_request_valid(
            "/openapi/v1/ctrl/sites/site-id/vlan-interface/stack/stack-1?page=1"))


if __name__ == "__main__":
    unittest.main()
