from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_incident_influences import (
    SiteIncidentInfluencesError, project_site_incident_influences,
)


class SiteIncidentInfluencesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.site_ref = "a" * 24
        self.target_ref = "b" * 24
        self.client_ref = "c" * 24
        self.target_mac = "00:11:22:33:44:55"
        self.client_mac = "66:77:88:99:AA:BB"
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._inventory_macs_by_site_ref[self.site_ref] = {
            self.target_ref: self.target_mac}
        self.client._client_macs_by_site_ref[self.site_ref] = {
            self.client_ref: self.client_mac}

    def test_projects_opaque_refs_and_diagnostic_flags_without_identity(self) -> None:
        result = project_site_incident_influences({
            "totalRows": 1, "currentPage": 1, "currentSize": 100,
            "data": [{"mac": self.client_mac, "clientName": "private name",
                      "ip": "192.0.2.4", "active": True, "authStatus": 2,
                      "health": 88}],
        }, "clients", {self.client_mac.lower(): self.client_ref})
        self.assertEqual(result["data"]["items"], [{
            "client_ref": self.client_ref, "active": True,
            "auth_status_code": 2, "health_score": 88,
        }])
        for secret in (self.client_mac, "private name", "192.0.2.4"):
            self.assertNotIn(secret, repr(result))
        self.assertFalse(result["partial"])

    def test_counts_unmapped_or_unknown_rows_without_echoing_values(self) -> None:
        result = project_site_incident_influences({"totalRows": 1, "data": [{
            "mac": self.client_mac, "active": False, "privateField": "secret",
        }]}, "clients", {})
        self.assertEqual(result["data"]["unmapped_identity_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("secret", repr(result))
        self.assertNotIn(self.client_mac, repr(result))
        self.assertTrue(result["partial"])

    def test_rejects_invalid_kind_and_oversized_pages(self) -> None:
        with self.assertRaises(SiteIncidentInfluencesError):
            project_site_incident_influences({}, "other", {})
        with self.assertRaises(SiteIncidentInfluencesError):
            project_site_incident_influences({"data": [{}] * 101}, "devices", {})

    def test_uses_context_from_opaque_incident_ref_and_fixed_query(self) -> None:
        responses = [
            {"result": [{"incidentId": "incident-1", "anomalyCode": "01001001"}]},
            {"result": {"totalRows": 1, "currentPage": 1, "currentSize": 100,
                         "data": [{"mac": self.client_mac, "active": True,
                                   "health": 90, "clientName": "must-not-appear"}]}},
        ]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=responses) as request:
            incidents = self.client.read_device_health_incidents(self.site_ref, self.target_ref)
            incident_ref = incidents["items"][0]["incident_ref"]
            result = self.client.read_site_incident_influencing_clients(self.site_ref, incident_ref)
        self.assertEqual(request.call_args_list[0].args[:2], (
            "GET", f"/openapi/v1/ctrl/sites/site_1/health/incident/{self.target_mac}"))
        self.assertEqual(request.call_args_list[1].args[:2], (
            "GET", f"/openapi/v1/ctrl/sites/site_1/anomaly/{self.target_mac}/"
            "influencing-clients?anomalyCode=01001001&page=1&pageSize=100"))
        self.assertEqual(result["resource"], "site_incident_influencing_clients")
        self.assertEqual(result["data"]["items"][0]["client_ref"], self.client_ref)
        self.assertNotIn("must-not-appear", repr(result))

    def test_context_is_required_and_query_shape_is_fixed(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "incident_ref_unknown"):
            self.client.read_site_incident_influencing_devices(self.site_ref, "d" * 24)
        with self.assertRaisesRegex(OpenApiError, "incident_ref_invalid"):
            self.client.read_site_incident_influencing_clients(self.site_ref, "bad")
        valid = ("/openapi/v1/ctrl/sites/site_1/anomaly/00:11:22:33:44:55/"
                 "influencing-clients?anomalyCode=01001001&page=1&pageSize=100")
        with patch.object(self.client, "_connection",
                          side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", valid, token="token")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", valid + "&searchKey=name")


if __name__ == "__main__":
    unittest.main()
