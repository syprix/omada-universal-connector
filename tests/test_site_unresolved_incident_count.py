from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_unresolved_incident_count import (
    MAX_INT32, SiteUnresolvedIncidentCountError,
    project_site_unresolved_incident_count,
)


SITE = "a" * 24


class SiteUnresolvedIncidentCountTests(unittest.TestCase):
    def test_projects_documented_int32_count_and_zero(self) -> None:
        for value in (0, 7, MAX_INT32):
            with self.subTest(value=value):
                result = project_site_unresolved_incident_count({"activeNum": value})
                self.assertEqual(result["data"], {
                    "unresolved_count": value,
                    "present": True,
                    "missing_count": 0,
                    "invalid_count": 0,
                    "unknown_field_count": 0,
                })
                self.assertFalse(result["partial"])

    def test_missing_invalid_and_unknown_fields_are_partial_without_echo(self) -> None:
        missing = project_site_unresolved_incident_count({})
        self.assertIsNone(missing["data"]["unresolved_count"])
        self.assertEqual(missing["data"]["missing_count"], 1)
        self.assertTrue(missing["partial"])

        for value in (True, -1, MAX_INT32 + 1, 1.0, "7"):
            with self.subTest(value=value):
                result = project_site_unresolved_incident_count({"activeNum": value})
                self.assertIsNone(result["data"]["unresolved_count"])
                self.assertFalse(result["data"]["present"])
                self.assertEqual(result["data"]["invalid_count"], 1)
                self.assertTrue(result["partial"])

        extra = project_site_unresolved_incident_count({"activeNum": 4, "incidentDetails": ["private"]})
        self.assertEqual(extra["data"]["unresolved_count"], 4)
        self.assertEqual(extra["data"]["unknown_field_count"], 1)
        self.assertNotIn("incidentDetails", repr(extra))
        self.assertNotIn("private", repr(extra))
        self.assertTrue(extra["partial"])

    def test_rejects_non_object_and_oversized_response(self) -> None:
        for value in (None, [], {str(i): i for i in range(33)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(
                    SiteUnresolvedIncidentCountError):
                project_site_unresolved_incident_count(value)

    def test_client_binds_site_and_uses_exact_documented_route(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client", "secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-id"
        with patch.object(client, "_access_token", return_value="fixture-token"), \
                patch.object(client, "_request_json", return_value={
                    "errorCode": 0, "result": {"activeNum": 3}}) as request:
            result = client.read_site_unresolved_incident_count(SITE)
        self.assertEqual(result["resource"], "site_unresolved_incident_count")
        self.assertEqual(result["site_ref"], SITE)
        self.assertEqual(result["data"]["unresolved_count"], 3)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-id/anomaly/unresolved-incidents",
            token="fixture-token")

    def test_client_rejects_unknown_site_and_wrong_controller_route_before_dispatch(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client", "secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_unresolved_incident_count(SITE)
            with self.assertRaisesRegex(OpenApiError, "site_ref_invalid"):
                client.read_site_unresolved_incident_count("A" * 24)
        request.assert_not_called()
        self.assertTrue(client._site_unresolved_incident_count_request_valid(
            "/openapi/v1/ctrl/sites/site-id/anomaly/unresolved-incidents"))
        self.assertFalse(client._site_unresolved_incident_count_request_valid(
            "/openapi/v1/other/sites/site-id/anomaly/unresolved-incidents"))
        self.assertFalse(client._site_unresolved_incident_count_request_valid(
            "/openapi/v1/ctrl/sites/site-id/anomaly/unresolved-incidents?debug=true"))


if __name__ == "__main__":
    unittest.main()
