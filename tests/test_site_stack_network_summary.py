import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_stack_network_summary import summarize_stack_networks


class SiteStackNetworkSummaryTests(unittest.TestCase):
    def test_counts_documented_types_and_states_without_exposing_values(self) -> None:
        result = summarize_stack_networks("a" * 24, [
            {"id": "private-id-1", "vlan": 123, "name": "private-name",
             "mode": 1, "mvlan": True, "status": True, "ipv6Enable": False},
            {"id": "private-id-2", "vlan": 456, "name": "other-name",
             "mode": 2, "mvlan": False, "status": False, "ipv6Enable": True},
            {"id": "private-id-3", "vlan": 789, "mode": 0, "mvlan": False},
        ], [True])
        self.assertEqual(result["reported_network_count"], 3)
        self.assertEqual(result["dhcp_mode_counts"], {
            "none": 1, "dhcp_server": 1, "dhcp_relay": 1, "unknown": 0})
        self.assertEqual(result["enabled_state_counts"], {
            "enabled": 1, "disabled": 1, "unreported": 1})
        self.assertEqual(result["management_network_counts"], {
            "yes": 1, "no": 2, "unreported": 0})
        self.assertEqual(result["ipv6_enabled_counts"], {
            "enabled": 1, "disabled": 1, "unreported": 1})
        self.assertTrue(result["ipv6_supported"])
        self.assertTrue(result["partial"])
        for secret in ("private-id-1", "private-name", "123", "456", "789"):
            self.assertNotIn(secret, repr(result))

    def test_unknown_values_and_truncation_are_reported(self) -> None:
        result = summarize_stack_networks("a" * 24, [
            {"id": "id", "vlan": 1, "mode": 8, "mvlan": "yes"}],
            [True, False], omitted_network_count=2)
        self.assertEqual(result["omitted_network_count"], 2)
        self.assertEqual(result["dhcp_mode_counts"]["unknown"], 1)
        self.assertIsNone(result["ipv6_supported"])
        self.assertTrue(result["partial"])

    def test_client_binds_stack_to_fresh_site_inventory_and_reads_v1_grid(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        site_ref, stack_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site-id"
        first = {"totalRows": 101, "currentPage": 1, "currentSize": 100,
                 "data": [{"id": f"network-{i}", "vlan": i, "mode": 1,
                           "mvlan": True, "status": True, "ipv6Enable": True}
                          for i in range(100)], "supportIpv6": True}
        second = {"totalRows": 101, "currentPage": 2, "currentSize": 1,
                  "data": [{"id": "network-last", "vlan": 200, "mode": 2,
                            "mvlan": False, "status": False, "ipv6Enable": False}],
                  "supportIpv6": True}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_read_bounded_grid_rows", return_value=(
                    [{"id": "stack-id"}], 0)) as inventory, \
                patch.object(client, "_opaque_ref", return_value=stack_ref), \
                patch.object(client, "_request_json", side_effect=[
                    {"errorCode": 0, "result": first},
                    {"errorCode": 0, "result": second},
                ]) as request:
            result = client.read_site_stack_network_summary(site_ref, stack_ref)
        inventory.assert_called_once()
        self.assertEqual(request.call_count, 2)
        self.assertIn("/openapi/v1/ctrl/sites/site-id/stacks/stack-id/networks?page=1&pageSize=100",
                      request.call_args_list[0].args[1])
        self.assertIn("?page=2&pageSize=100", request.call_args_list[1].args[1])
        self.assertEqual(result["reported_network_count"], 101)
        self.assertEqual(result["dhcp_mode_counts"]["dhcp_server"], 100)
        self.assertEqual(result["dhcp_mode_counts"]["dhcp_relay"], 1)
        self.assertNotIn("network-last", repr(result))

    def test_unknown_stack_reference_is_rejected_before_network_grid_read(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        site_ref = "a" * 24
        client._site_ids_by_ref[site_ref] = "site-id"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_read_bounded_grid_rows", return_value=(
                    [{"id": "different-stack"}], 0)), \
                patch.object(client, "_opaque_ref", return_value="c" * 24), \
                patch.object(client, "_request_json") as request:
            with self.assertRaises(OpenApiError) as error:
                client.read_site_stack_network_summary(site_ref, "b" * 24)
        self.assertEqual(error.exception.code, "stack_ref_unknown")
        request.assert_not_called()

    def test_duplicate_stack_inventory_matches_are_rejected(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        site_ref, stack_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site-id"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_read_bounded_grid_rows", return_value=(
                    [{"id": "duplicate"}, {"id": "duplicate"}], 0)), \
                patch.object(client, "_opaque_ref", return_value=stack_ref), \
                patch.object(client, "_request_json") as request:
            with self.assertRaises(OpenApiError) as error:
                client.read_site_stack_network_summary(site_ref, stack_ref)
        self.assertEqual(error.exception.code, "stack_ref_ambiguous")
        request.assert_not_called()

    def test_request_guard_is_bound_and_bounded(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=100, max_pages=10))
        self.assertTrue(client._site_stack_networks_request_valid(
            "/openapi/v1/ctrl/sites/site-1/stacks/stack_1/networks?page=10&pageSize=1000"))
        self.assertFalse(client._site_stack_networks_request_valid(
            "/openapi/v1/other/sites/site-1/stacks/stack_1/networks?page=1&pageSize=100"))
        self.assertFalse(client._site_stack_networks_request_valid(
            "/openapi/v1/ctrl/sites/site-1/stacks/stack_1/networks?page=11&pageSize=100"))
        self.assertFalse(client._site_stack_networks_request_valid(
            "/openapi/v1/ctrl/sites/site-1/stacks/stack_1/networks?page=1&pageSize=1001"))


if __name__ == "__main__":
    unittest.main()
