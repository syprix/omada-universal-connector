from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_vlan_port_support_summary import (
    VlanPortSupportError, project_site_vlan_port_support_summary,
)

SITE_REF = "a" * 24
NETWORK_REF = "b" * 24


class VlanPortSupportProjectionTests(unittest.TestCase):
    def test_counts_support_by_device_type_and_drops_port_and_device_identity(self) -> None:
        result = project_site_vlan_port_support_summary({"devicePortSupportVlan": {
            "private-mac-a": {"mac": "private-mac-a", "type": "switch", "stackId": "secret",
                              "portList": [{"port": "secret-port", "support": True},
                                           {"standardPort": "other-port", "support": False}]},
            "private-mac-b": {"type": "ap", "portList": [{"port": "ap-port", "support": True}]},
            "private-mac-c": {"type": "olt", "portList": [{"support": None}]},
        }})
        self.assertEqual(result["device_count"], 3)
        self.assertEqual(result["device_type_counts"],
                         {"ap": 1, "gateway": 0, "olt": 1, "switch": 1})
        self.assertEqual(result["reported_port_count"], 4)
        self.assertEqual(result["supported_port_count"], 2)
        self.assertEqual(result["unsupported_port_count"], 1)
        self.assertEqual(result["unknown_support_port_count"], 1)
        self.assertTrue(result["partial"])
        for secret in ("private-mac", "secret-port", "other-port", "ap-port", "stackId"):
            self.assertNotIn(secret, repr(result))

    def test_single_device_schema_shape_is_counted_but_marked_partial(self) -> None:
        result = project_site_vlan_port_support_summary({
            "devicePortSupportVlan": {"mac": "private", "type": "switch",
                                      "portList": [{"support": True}]}})
        self.assertEqual(result["device_count"], 1)
        self.assertEqual(result["supported_port_count"], 1)
        self.assertTrue(result["partial"])
        self.assertIn("single_device_object_shape", result["coverage"])

    def test_missing_fields_unknown_properties_and_invalid_rows_are_visible(self) -> None:
        result = project_site_vlan_port_support_summary({"devicePortSupportVlan": {
            "x": {"type": "switch", "portList": [{"support": "yes", "private": "secret"}],
                  "extra": 1},
            "y": {"type": "gateway"},
            "z": {"type": {}, "portList": []},
        }})
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertEqual(result["devices_without_port_list_count"], 1)
        self.assertEqual(result["unknown_support_port_count"], 1)
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertNotIn("secret", repr(result))

    def test_malformed_or_oversized_results_fail_closed(self) -> None:
        for raw in (None, [], {}, {"devicePortSupportVlan": []},
                    {"devicePortSupportVlan": {"x": None}},
                    {"devicePortSupportVlan": {str(i): {} for i in range(10_001)}}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(VlanPortSupportError):
                project_site_vlan_port_support_summary(raw)


class VlanPortSupportClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site-1"

    def test_reads_only_after_network_and_vlan_binding_matches(self) -> None:
        rows = [{"id": "network-1", "purpose": 0, "vlan": 24}]
        payload = {"devicePortSupportVlan": {"private-mac": {
            "mac": "private-mac", "type": "switch", "portList": [{"port": "secret", "support": True}]}}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows) as inventory, \
                patch.object(self.client, "_opaque_ref", return_value=NETWORK_REF), \
                patch.object(self.client, "_request_json", return_value={"result": payload}) as request:
            result = self.client.read_site_vlan_port_support_summary(SITE_REF, NETWORK_REF, 24)
        inventory.assert_called_once()
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-1/networks/network-1/vlan/24/device-support-ports",
            token="token")
        self.assertEqual(result["supported_port_count"], 1)
        self.assertNotIn("private-mac", repr(result))
        self.assertNotIn("secret", repr(result))

    def test_mismatched_vlan_and_invalid_inputs_stop_before_support_read(self) -> None:
        with patch.object(self.client, "_read_pages", return_value=[
                {"id": "network-1", "purpose": 0, "vlan": 23}]), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_opaque_ref", return_value=NETWORK_REF), \
                patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "network_vlan_mismatch"):
                self.client.read_site_vlan_port_support_summary(SITE_REF, NETWORK_REF, 24)
            for vlan in (0, 4095, True, "24"):
                with self.assertRaisesRegex(OpenApiError, "vlan_id_invalid"):
                    self.client.read_site_vlan_port_support_summary(SITE_REF, NETWORK_REF, vlan)
        request.assert_not_called()

    def test_unknown_network_and_non_vlan_network_do_not_read_ports(self) -> None:
        with patch.object(self.client, "_read_pages", return_value=[
                {"id": "network-1", "purpose": 1, "vlan": 24}]), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_opaque_ref", return_value=NETWORK_REF), \
                patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "network_vlan_mismatch"):
                self.client.read_site_vlan_port_support_summary(SITE_REF, NETWORK_REF, 24)
            with self.assertRaisesRegex(OpenApiError, "network_ref_unknown"):
                self.client.read_site_vlan_port_support_summary(SITE_REF, "c" * 24, 24)
        request.assert_not_called()

    def test_route_allowlist_rejects_vlan_outside_documented_range(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/ctrl/sites/site-1/networks/network-1/vlan/4095/device-support-ports",
                token="token")
