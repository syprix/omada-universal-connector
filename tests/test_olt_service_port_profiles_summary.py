from __future__ import annotations

import unittest
from unittest.mock import patch

from app.olt_service_port_profiles_summary import (
    OltServicePortProfilesError,
    project_olt_service_port_profiles_summary,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class OltServicePortProfilesProjectionTests(unittest.TestCase):
    def test_aggregates_entries_and_redacts_names_ids_and_usage_values(self) -> None:
        result = project_olt_service_port_profiles_summary([
            {"servicePortProfileId": "secret-id-1", "servicePortProfileName": "private-name-1",
             "entriesNumber": 3, "inUse": "yes"},
            {"servicePortProfileId": "secret-id-2", "servicePortProfileName": "private-name-2",
             "entriesNumber": 5, "inUse": "no"},
        ])
        self.assertEqual(result["data"], {
            "profile_count": 2, "entries_total": 8,
            "entries_number_reported_profile_count": 2,
            "in_use_reported_profile_count": 2,
        })
        self.assertFalse(result["partial"])
        for value in ("secret-id-1", "private-name-1", "yes"):
            self.assertNotIn(value, repr(result))

    def test_unknown_invalid_and_unbounded_results_are_reported_or_rejected(self) -> None:
        result = project_olt_service_port_profiles_summary([{
            "servicePortProfileId": "id", "servicePortProfileName": "name",
            "entriesNumber": 128, "inUse": "yes", "secret": "private"}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["invalid_count"], 1)
        self.assertNotIn("private", repr(result))
        for payload in (None, {}, [{} for _ in range(513)]):
            with self.subTest(payload=type(payload).__name__), self.assertRaises(OltServicePortProfilesError):
                project_olt_service_port_profiles_summary(payload)


class OltServicePortProfilesAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.device_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._inventory_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00-11-22-33-44-55"}
        self.client._olt_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00:11:22:33:44:55"}

    def test_fixed_inventory_bound_get(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}) as request:
            result = self.client.read_olt_service_port_profiles_summary(self.site_ref, self.device_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
            "pon/profile/service-port/profiles/list", token="token")
        self.assertEqual(result["resource"], "olt_service_port_profiles_summary")

    def test_allowlist_and_inventory_binding(self) -> None:
        path = ("/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
                "pon/profile/service-port/profiles/list")
        self.assertTrue(self.client._olt_service_port_profiles_request_valid(path))
        self.assertFalse(self.client._olt_service_port_profiles_request_valid(path.replace("ctrl", "other")))
        self.client._olt_macs_by_site_ref[self.site_ref] = {}
        with patch.object(self.client, "_request_json") as request, \
                self.assertRaisesRegex(OpenApiError, "device_type_unsupported"):
            self.client.read_olt_service_port_profiles_summary(self.site_ref, self.device_ref)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
