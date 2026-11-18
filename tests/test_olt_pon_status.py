from __future__ import annotations

import unittest
from unittest.mock import patch

from app.olt_pon_status import (
    OltPonStatusError, project_olt_onu_global_status,
    project_olt_onu_isolation_status,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class OltPonStatusProjectionTests(unittest.TestCase):
    def test_global_status_returns_only_documented_flags(self) -> None:
        result = project_olt_onu_global_status({
            "onuIsolation": "ENABLE", "supportOnuIsolation": "DISABLE",
            "secret": "must not escape",
        })
        self.assertEqual(result["data"], {
            "onu_isolation_enabled": True, "onu_isolation_supported": False})
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("must not escape", repr(result))

    def test_isolation_status_omits_vlan_identifiers(self) -> None:
        result = project_olt_onu_isolation_status({
            "onuIsolation": "ENABLE", "isolateAllVlan": "DISABLE",
            "vlanList": "1,3-5,7",
        })
        self.assertEqual(result["data"], {
            "onu_isolation_enabled": True, "all_vlan_scope_enabled": False,
            "vlan_list_configured": True,
        })
        self.assertFalse(result["partial"])
        self.assertNotIn("1,3-5,7", repr(result))

    def test_unknown_or_invalid_states_are_counted_and_bounds_are_enforced(self) -> None:
        result = project_olt_onu_global_status({"onuIsolation": "UNKNOWN"})
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_count"], 1)
        with self.assertRaises(OltPonStatusError):
            project_olt_onu_global_status({f"unknown{index}": index for index in range(9)})
        with self.assertRaises(OltPonStatusError):
            project_olt_onu_isolation_status([])


class OltPonStatusAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.device_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._inventory_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00-11-22-33-44-55"}
        self.client._olt_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00:11:22:33:44:55"}

    def test_fixed_inventory_bound_reads(self) -> None:
        paths = (
            ("read_olt_onu_global_status", "onu-management/global-config/get",
             {"onuIsolation": "ENABLE", "supportOnuIsolation": "ENABLE"}),
            ("read_olt_onu_isolation_status", "onu-management/global-config/isolation/get",
             {"onuIsolation": "ENABLE", "isolateAllVlan": "DISABLE", "vlanList": "1,3-5"}),
        )
        for method, suffix, payload in paths:
            with self.subTest(method=method), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": payload}) as request:
                result = getattr(self.client, method)(self.site_ref, self.device_ref)
                self.assertEqual(result["site_ref"], self.site_ref)
                self.assertEqual(result["device_ref"], self.device_ref)
                self.assertFalse(result["partial"])
                self.assertTrue(request.call_args.args[1].endswith(suffix))

    def test_path_allowlist_and_inventory_binding(self) -> None:
        path = ("/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
                "pon/onu-management/global-config/get")
        self.assertTrue(self.client._olt_onu_global_status_request_valid(path))
        self.assertFalse(self.client._olt_onu_global_status_request_valid(path.replace("ctrl", "else")))
        self.client._olt_macs_by_site_ref[self.site_ref] = {}
        with patch.object(self.client, "_request_json") as request, \
                self.assertRaisesRegex(OpenApiError, "device_type_unsupported"):
            self.client.read_olt_onu_global_status(self.site_ref, self.device_ref)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
