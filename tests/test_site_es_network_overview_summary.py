from __future__ import annotations

import unittest
from unittest.mock import patch
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_es_network_overview_summary import (
    EsNetworkOverviewError, summarize_es_network_overview,
)


class EsNetworkOverviewSummaryTests(unittest.TestCase):
    def test_counts_assignments_without_network_or_port_values(self):
        result = summarize_es_network_overview([
            {"id": "private-id", "name": "private-name", "vlan": 20,
             "nativePorts": [1], "untaggedPorts": [2, 3], "taggedPorts": [4, 5]},
            {"id": "private-id-2", "name": "private-name-2", "vlan": 21,
             "nativePorts": [], "untaggedPorts": [], "taggedPorts": [6]},
        ])
        self.assertEqual(result["reported_network_count"], 2)
        self.assertEqual(result["network_rows_with_port_assignments"], 2)
        self.assertEqual(result["port_assignment_counts"],
                         {"native": 1, "untagged": 2, "tagged": 3})
        for secret in ("private-id", "private-name", "vlan", "nativePorts"):
            self.assertNotIn(secret, repr(result))
        self.assertFalse(result["partial"])

    def test_unknown_invalid_and_truncated_data_are_partial(self):
        result = summarize_es_network_overview([
            {"nativePorts": [True, 1], "future": "private"}, None, {},
        ], max_items=2)
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_record_count"], 1)
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["truncated"])
        with self.assertRaises(EsNetworkOverviewError):
            summarize_es_network_overview({"result": []})

    def test_switch_ref_is_refreshed_and_bound_to_es_read_path(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        site_ref, switch_ref = "8" * 24, "9" * 24
        client._site_ids_by_ref[site_ref] = "site_internal"

        def refresh(ref):
            client._switch_macs_by_site_ref[ref] = {switch_ref: "AA-BB-CC-DD-EE-FF"}
            return {"items": []}

        detail_path = (
            "/openapi/v1/ctrl/sites/site_internal/switches/ports/switch-detail")
        overview_path = (
            "/openapi/v1/ctrl/sites/site_internal/switches/es/AA-BB-CC-DD-EE-FF/"
            "network-overview")
        with patch.object(client, "list_devices", side_effect=refresh), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=[
                    {"result": [{"mac": "AA:BB:CC:DD:EE:FF", "es": True}]},
                    {"result": [{"name": "private", "vlan": 20,
                                  "taggedPorts": [1]}]},
                ]) as request:
            result = client.read_site_es_network_overview_summary(site_ref, switch_ref)
        self.assertEqual(request.call_args_list[0].args, ("GET", detail_path))
        self.assertEqual(request.call_args_list[1].args, ("GET", overview_path))
        self.assertEqual(result["reported_network_count"], 1)
        self.assertNotIn("private", repr(result))
        self.assertTrue(client._site_switch_port_detail_request_valid(detail_path))
        self.assertFalse(client._site_switch_port_detail_request_valid(
            "/openapi/v1/other/sites/site_internal/switches/ports/switch-detail"))
        self.assertTrue(client._site_es_network_overview_request_valid(
            overview_path))
        self.assertFalse(client._site_es_network_overview_request_valid(
            "/openapi/v1/other/sites/site_internal/switches/es/AA-BB-CC-DD-EE-FF/network-overview"))
        client._switch_macs_by_site_ref[site_ref] = {}
        with patch.object(client, "list_devices", return_value={"items": []}):
            with self.assertRaisesRegex(OpenApiError, "switch_ref_unknown"):
                client.read_site_es_network_overview_summary(site_ref, switch_ref)

    def test_rejects_non_agile_switch_before_network_overview_read(self):
        client, site_ref, switch_ref = self._client_with_selected_switch()
        with patch.object(client, "list_devices", return_value={"items": []}), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": [
                    {"mac": "AA:BB:CC:DD:EE:FF", "es": False}]}) as request:
            with self.assertRaisesRegex(OpenApiError, "switch_family_unsupported"):
                client.read_site_es_network_overview_summary(site_ref, switch_ref)
        request.assert_called_once()

    def test_rejects_missing_agile_inventory_match(self):
        client, site_ref, switch_ref = self._client_with_selected_switch()
        with patch.object(client, "list_devices", return_value={"items": []}), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": [
                    {"mac": "00:11:22:33:44:55", "es": True}]}):
            with self.assertRaisesRegex(OpenApiError, "switch_family_unknown"):
                client.read_site_es_network_overview_summary(site_ref, switch_ref)

    def test_rejects_duplicate_agile_inventory_matches(self):
        client, site_ref, switch_ref = self._client_with_selected_switch()
        with patch.object(client, "list_devices", return_value={"items": []}), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": [
                    {"mac": "AA:BB:CC:DD:EE:FF", "es": True},
                    {"mac": "aa-bb-cc-dd-ee-ff", "es": True}]}):
            with self.assertRaisesRegex(OpenApiError, "switch_family_ambiguous"):
                client.read_site_es_network_overview_summary(site_ref, switch_ref)

    @staticmethod
    def _client_with_selected_switch():
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        site_ref, switch_ref = "8" * 24, "9" * 24
        client._site_ids_by_ref[site_ref] = "site_internal"
        client._switch_macs_by_site_ref[site_ref] = {
            switch_ref: "AA-BB-CC-DD-EE-FF"}
        return client, site_ref, switch_ref


if __name__ == "__main__":
    unittest.main()
