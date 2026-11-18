from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_incident_notification import (
    SiteIncidentNotificationError,
    project_site_incident_notification,
)


class SiteIncidentNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_reads_fixed_route_for_known_site_only(self) -> None:
        payload = {"email": {"eventLevel": {}, "eventObjectType": {},
                             "eventCategory": {}}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": payload}) as request:
            result = self.client.read_site_incident_notification(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/anomaly/notification", token="token")
        self.assertEqual(result["resource"], "site_incident_notification")
        self.assertFalse(result["partial"])
        with self.assertRaisesRegex(OpenApiError, "site_ref_invalid"):
            self.client.read_site_incident_notification("invalid")
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_incident_notification("b" * 24)

    def test_rejects_another_controller_route_and_invalid_upstream_payload(self) -> None:
        good = "/openapi/v1/ctrl/sites/site_1/anomaly/notification"
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"))
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_incident_notification(self.site_ref)

    def test_projects_hardware_and_cbc_schema_without_recipient_addresses(self) -> None:
        email = "private-recipient@example.invalid"
        result = project_site_incident_notification({
            "resource": 2,
            "alertEmailSetting": {"delayEnable": True, "delay": 15},
            "email": {
                "eventLevel": {"critical": True, "info": False},
                "eventObjectType": {"gateway": True, "ap": False},
                "eventCategory": {"networking": True, "security": False},
            },
            "recipients": [{"email": email}],
        })
        rendered = repr(result)
        self.assertNotIn(email, rendered)
        self.assertEqual(result["data"]["recipient_count"], 1)
        self.assertEqual(result["data"]["resource_code"], 2)
        self.assertEqual(result["data"]["event_notifications"]["category_mode"], "flags")
        self.assertFalse(result["partial"])

    def test_projects_er_email_alerts_and_documented_single_category_example(self) -> None:
        result = project_site_incident_notification({
            "resource": 1,
            "alertEmailSetting": {"alertEmailEnable": True, "delayEnable": False},
            "Email Alerts": {
                "eventLevel": {"warning": True},
                "eventObjectType": {"wirelessClient": True},
                "eventCategory": "networking",
            },
        })
        data = result["data"]
        self.assertTrue(data["alert_email_setting"]["enabled"])
        self.assertEqual(data["event_notifications"]["category_flags"], {"networking": True})
        self.assertEqual(data["event_notifications"]["category_mode"], "single_key")
        self.assertFalse(result["partial"])

    def test_counts_invalid_and_unknown_data_without_echoing_values(self) -> None:
        private_text = "do-not-return-this"
        result = project_site_incident_notification({
            "email": {"eventLevel": {"critical": 1, "privateFlag": private_text},
                      "eventObjectType": {}, "eventCategory": {"privateCategory": True}},
            "secretSetting": private_text,
            "recipients": [{"email": private_text}],
        })
        self.assertGreater(result["data"]["invalid_count"], 0)
        self.assertGreater(result["data"]["unknown_field_count"], 0)
        self.assertNotIn(private_text, repr(result))
        self.assertTrue(result["partial"])

    def test_rejects_wrong_or_oversized_payloads(self) -> None:
        for value in (None, [], {str(index): True for index in range(17)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(
                    SiteIncidentNotificationError):
                project_site_incident_notification(value)
        invalid = project_site_incident_notification({"recipients": [
            {"email": "x@example.invalid"} for _ in range(101)]})
        self.assertEqual(invalid["data"]["invalid_count"], 1)
        self.assertNotIn("recipient_count", invalid["data"])


if __name__ == "__main__":
    unittest.main()
