from __future__ import annotations

import unittest
from unittest.mock import patch

from app.olt_onu_inventory_summary import (
    OltOnuInventoryError,
    project_olt_onu_reboot_status_summary,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class OltOnuRebootStatusProjectionTests(unittest.TestCase):
    def test_counts_documented_statuses_and_redacts_onu_identifier(self) -> None:
        result = project_olt_onu_reboot_status_summary([
            {"key": "private-onu-1", "onlineStatus": "ONLINE"},
            {"key": "private-onu-2", "onlineStatus": "UPGRADING"},
            {"key": "private-onu-3", "onlineStatus": "FAILED"},
        ])
        self.assertEqual(result["data"], {
            "onu_count": 3,
            "online_status_counts": {"ONLINE": 1, "UPGRADING": 1, "FAILED": 1},
        })
        self.assertFalse(result["partial"])
        for value in ("private-onu-1", "private-onu-2", "private-onu-3"):
            self.assertNotIn(value, repr(result))

    def test_unknown_and_missing_fields_are_reported_without_echoing_values(self) -> None:
        result = project_olt_onu_reboot_status_summary([
            {"key": "private-onu", "onlineStatus": "ONLINE", "privateField": "secret"},
            {"onlineStatus": None},
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["missing_count"], 1)
        self.assertNotIn("secret", repr(result))
        self.assertNotIn("private-onu", repr(result))

    def test_rejects_unbounded_or_malformed_response(self) -> None:
        for payload in (None, {}, [{} for _ in range(1001)]):
            with self.subTest(payload=type(payload).__name__), self.assertRaises(OltOnuInventoryError):
                project_olt_onu_reboot_status_summary(payload)


class OltOnuRebootStatusAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.device_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._inventory_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00-11-22-33-44-55"}
        self.client._olt_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00:11:22:33:44:55"}

    def test_fixed_site_and_olt_bound_get(self) -> None:
        payload = {"result": [{"key": "private-onu", "onlineStatus": "ONLINE"}]}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_olt_onu_reboot_status_summary(self.site_ref, self.device_ref)
        request.assert_called_once_with(
            "GET",
            "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
            "pon/onu-management/informations/reboot-status/list",
            token="token",
        )
        self.assertEqual(result["resource"], "olt_onu_reboot_status_summary")
        self.assertNotIn("private-onu", repr(result))

    def test_allowlist_and_site_inventory_binding(self) -> None:
        path = ("/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
                "pon/onu-management/informations/reboot-status/list")
        self.assertTrue(self.client._olt_onu_reboot_status_request_valid(path))
        self.assertFalse(self.client._olt_onu_reboot_status_request_valid(path.replace("ctrl", "other")))
        self.client._olt_macs_by_site_ref[self.site_ref] = {}
        with patch.object(self.client, "_request_json") as request, \
                self.assertRaisesRegex(OpenApiError, "device_type_unsupported"):
            self.client.read_olt_onu_reboot_status_summary(self.site_ref, self.device_ref)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
