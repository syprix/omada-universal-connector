from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_vlan_device_usage_summary import (
    VlanDeviceUsageError, project_site_vlan_device_usage_summary,
)

SITE_REF = "a" * 24
NETWORK_REF = "b" * 24


class VlanDeviceUsageProjectionTests(unittest.TestCase):
    def test_counts_documented_types_modes_and_stack_memberships(self) -> None:
        result = project_site_vlan_device_usage_summary([
            {"name": "private-switch", "mac": "private-mac", "type": 2,
             "stackId": "private-stack", "dhcpMode": 1},
            {"name": "private-ap", "type": 3},
            {"type": 1, "dhcpMode": 0},
        ])
        self.assertEqual(result["device_count"], 3)
        self.assertEqual(result["device_type_counts"], {"gateway": 1, "switch": 1, "ap": 1})
        self.assertEqual(result["stack_membership_count"], 1)
        self.assertEqual(result["dhcp_mode_counts"], {"0": 1, "1": 1})
        self.assertFalse(result["partial"])
        for secret in ("private-switch", "private-mac", "private-stack", "private-ap"):
            self.assertNotIn(secret, repr(result))

    def test_unknown_invalid_and_redacted_fields_are_reported(self) -> None:
        result = project_site_vlan_device_usage_summary([
            {"name": "secret", "mac": "hidden", "type": 7, "unknown": "private"},
            {"dhcpMode": True, "stackId": 5},
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["redacted_field_count"], 3)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["invalid_field_count"], 3)
        self.assertNotIn("private", repr(result))

    def test_malformed_and_oversized_lists_fail_closed(self) -> None:
        for raw in (None, {}, [None], [{}] * 10_001):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(VlanDeviceUsageError):
                project_site_vlan_device_usage_summary(raw)


class VlanDeviceUsageClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site-1"
        self.client._network_ids_by_site_ref[SITE_REF] = {NETWORK_REF: "network-1"}

    def test_reads_fixed_site_bound_route_and_redacts_values(self) -> None:
        raw = {"result": [{"name": "secret", "mac": "hidden", "type": 3}]}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=raw) as request:
            result = self.client.read_site_vlan_device_usage_summary(SITE_REF, NETWORK_REF, 24)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-1/networks/network-1/vlan/24/devices",
            token="token")
        self.assertEqual(result["device_count"], 1)
        self.assertNotIn("secret", repr(result))

    def test_invalid_vlan_and_unknown_network_stop_before_request(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            for vlan in (0, 4095, True, "24"):
                with self.assertRaisesRegex(OpenApiError, "vlan_id_invalid"):
                    self.client.read_site_vlan_device_usage_summary(SITE_REF, NETWORK_REF, vlan)
            with self.assertRaisesRegex(OpenApiError, "network_ref_unknown"):
                self.client.read_site_vlan_device_usage_summary(SITE_REF, "c" * 24, 24)
        request.assert_not_called()

    def test_route_allowlist_rejects_out_of_range_vlan(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json(
                "GET", "/openapi/v1/ctrl/sites/site-1/networks/network-1/vlan/4095/devices")
