from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_health_incidents import (
    SiteHealthIncidentError, extract_incidents, project_incident_detail,
)


SITE = "a" * 24
OTHER_SITE = "b" * 24
DEVICE = "c" * 24
MAC = "02:11:22:33:44:55"
INCIDENT_ID = "incident-opaque-upstream-17"


class SiteHealthIncidentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client", "secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref.update({SITE: "site-id", OTHER_SITE: "other-site"})
        self.client._inventory_macs_by_site_ref[SITE] = {DEVICE: MAC}
        self.client._client_macs_by_site_ref[SITE] = {"d" * 24: MAC}

    def test_list_mints_opaque_snapshot_refs_and_detail_redacts_dynamic_fields(self) -> None:
        list_response = {"errorCode": 0, "result": {"data": [{
            "incidentId": INCIDENT_ID, "anomalyCode": "01001001", "category": 11,
            "level": 2, "status": 0, "time": 1_800_000_000_000,
            "objectType": "CLIENT", "object": ["private client"],
            "titleParams": {"name": "private name"},
        }]}}
        detail_response = {"errorCode": 0, "result": {
            "anomalyCode": "01001001", "category": 11, "level": 2, "status": 0,
            "time": 1_800_000_000_000, "objectType": "CLIENT",
            "detail": "private diagnostic text", "clients": {"mac": MAC},
        }}
        with patch.object(self.client, "_access_token", return_value="fixture"), \
                patch.object(self.client, "_request_json",
                             side_effect=[list_response, detail_response]) as request:
            listed = self.client.read_device_health_incidents(SITE, DEVICE)
            incident_ref = listed["items"][0]["incident_ref"]
            detail = self.client.read_site_incident_detail(SITE, incident_ref)

        self.assertRegex(incident_ref, r"^[0-9a-f]{24}$")
        self.assertNotIn(INCIDENT_ID, repr(listed))
        self.assertNotIn(MAC, repr(listed))
        self.assertNotIn("private", repr(listed))
        self.assertNotIn("private", repr(detail))
        self.assertNotIn(MAC, repr(detail))
        self.assertEqual(detail["data"]["anomaly_code"], "01001001")
        self.assertEqual(detail["data"]["object_type"], "CLIENT")
        self.assertEqual(request.call_args_list[0].args,
                         ("GET", f"/openapi/v1/ctrl/sites/site-id/health/incident/{MAC}"))
        self.assertEqual(request.call_args_list[1].args,
                         ("GET", f"/openapi/v1/ctrl/sites/site-id/anomaly/incident/{INCIDENT_ID}"))

    def test_refs_are_bound_to_site_and_latest_list_snapshot(self) -> None:
        with patch.object(self.client, "_access_token", return_value="fixture"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0, "result": {"data": [{"incidentId": INCIDENT_ID}]}}):
            old_ref = self.client.read_device_health_incidents(SITE, DEVICE)["items"][0]["incident_ref"]
            with self.assertRaisesRegex(OpenApiError, "incident_ref_unknown"):
                self.client.read_site_incident_detail(OTHER_SITE, old_ref)
            self.client.read_device_health_incidents(SITE, DEVICE)

        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "incident_ref_unknown"):
                self.client.read_site_incident_detail(SITE, old_ref)
        request.assert_not_called()

    def test_rejects_unknown_target_and_malformed_ref_before_controller_call(self) -> None:
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
                self.client.read_device_health_incidents(SITE, "d" * 24)
            with self.assertRaisesRegex(OpenApiError, "incident_ref_invalid"):
                self.client.read_site_incident_detail(SITE, "raw-upstream-id")
        request.assert_not_called()

    def test_client_incident_source_uses_current_client_inventory_ref(self) -> None:
        with patch.object(self.client, "_access_token", return_value="fixture"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0, "result": {"incidentId": INCIDENT_ID}}) as request:
            result = self.client.read_client_health_incidents(SITE, "d" * 24)
        self.assertEqual(result["resource"], "client_health_incidents")
        self.assertEqual(result["count"], 1)
        self.assertEqual(request.call_args.args[1],
                         f"/openapi/v1/ctrl/sites/site-id/health/incident/{MAC}")
        self.assertNotIn(INCIDENT_ID, repr(result))

    def test_projection_rejects_malformed_ids_and_keeps_no_free_text(self) -> None:
        with self.assertRaises(SiteHealthIncidentError):
            extract_incidents({"data": [{"incidentId": "bad/id"}]})
        with self.assertRaises(SiteHealthIncidentError):
            project_incident_detail({"detail": "must not become the whole response"})
        projected = project_incident_detail({"anomalyCode": "A1", "detail": "private"})
        self.assertNotIn("private", repr(projected))

    def test_fixed_paths_require_configured_controller_and_documented_shapes(self) -> None:
        good_list = f"/openapi/v1/ctrl/sites/site-id/health/incident/{MAC}"
        good_detail = f"/openapi/v1/ctrl/sites/site-id/anomaly/incident/{INCIDENT_ID}"
        self.assertTrue(self.client._device_health_incidents_request_valid(good_list))
        self.assertTrue(self.client._site_incident_detail_request_valid(good_detail))
        self.assertFalse(self.client._device_health_incidents_request_valid(good_list.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_incident_detail_request_valid(good_detail + "?x=1"))


if __name__ == "__main__":
    unittest.main()
