from __future__ import annotations

import unittest
from unittest.mock import patch

from app.olt_onu_inventory_summary import (
    OltOnuInventoryError,
    project_olt_onu_inventory_summary,
    validate_pon_port_selector,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class OltOnuInventoryProjectionTests(unittest.TestCase):
    def test_counts_statuses_and_redacts_identity_profiles_and_optical_values(self) -> None:
        result = project_olt_onu_inventory_summary([
            {"key": "private-onu", "ponPortStr": "GPON 1/1/1", "onuId": 1,
             "onuDescription": "private description", "serialNumber": "secret-serial",
             "macAddress": "00:11:22:33:44:55", "lineProfile": "secret-line",
             "serviceProfile": "secret-service", "servicePortProfile": "secret-port",
             "adminStatus": "ACTIVATE", "onlineStatus": "ONLINE", "configStatus": "SUCCESS",
             "matchStatus": "MATCH", "activeStatus": "ACTIVE", "equipmentId": "secret-equip",
             "softwareVersion": "secret-version", "hardwareVersion": "secret-hw",
             "receivedOpticalPower": "-20.2 dBm", "transmittedOpticalPower": "2.0 dBm"},
        ])
        data = result["data"]
        self.assertEqual(data["onu_count"], 1)
        self.assertEqual(data["online_status_counts"], {"ONLINE": 1})
        self.assertEqual(data["admin_status_counts"], {"ACTIVATE": 1})
        self.assertEqual(data["optical_power_reported_counts"], {"received": 1, "transmitted": 1})
        for value in ("private-onu", "private description", "secret-serial", "secret-line",
                      "secret-service", "secret-port", "secret-version", "-20.2 dBm"):
            self.assertNotIn(value, repr(result))

    def test_invalid_unknown_and_unbounded_results(self) -> None:
        result = project_olt_onu_inventory_summary([{
            "key": "private", "onlineStatus": "BAD", "unknown": "secret"}])
        self.assertTrue(result["partial"])
        self.assertGreater(result["invalid_count"], 0)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("secret", repr(result))
        for value in (None, {}, [{} for _ in range(1001)]):
            with self.subTest(value=type(value).__name__), self.assertRaises(OltOnuInventoryError):
                project_olt_onu_inventory_summary(value)

    def test_pon_selector_accepts_documented_lists_and_rejects_injection(self) -> None:
        value = "GPON 1/1/1-3,GPON 1/1/5,GPON 1/1/7-8"
        self.assertEqual(validate_pon_port_selector(value), value)
        for value in ("", "GPON 1/1/3-1", "GPON 1/1/129", "GPON 1/1/1&x=y",
                      "GPON 1/1/1/../../sites", "GPON 1/1/1, GPON 1/1/2"):
            with self.subTest(value=value), self.assertRaises(OltOnuInventoryError):
                validate_pon_port_selector(value)


class OltOnuInventoryAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.device_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._inventory_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00-11-22-33-44-55"}
        self.client._olt_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00:11:22:33:44:55"}

    def test_required_selector_is_serialized_to_fixed_source_query(self) -> None:
        payload = {"result": [{"onlineStatus": "ONLINE"}]}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_olt_onu_inventory_summary(
                self.site_ref, self.device_ref, "GPON 1/1/1")
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
            "pon/onu-management/informations/list?ponPort=GPON+1%2F1%2F1", token="token")
        self.assertEqual(result["resource"], "olt_onu_inventory_summary")

    def test_query_allowlist_and_site_inventory_binding(self) -> None:
        path = ("/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
                "pon/onu-management/informations/list?ponPort=GPON+1%2F1%2F1")
        self.assertTrue(self.client._olt_onu_inventory_request_valid(path))
        self.assertFalse(self.client._olt_onu_inventory_request_valid(path + "&other=value"))
        self.client._olt_macs_by_site_ref[self.site_ref] = {}
        with patch.object(self.client, "_request_json") as request, \
                self.assertRaisesRegex(OpenApiError, "device_type_unsupported"):
            self.client.read_olt_onu_inventory_summary(self.site_ref, self.device_ref, "GPON 1/1/1")
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
