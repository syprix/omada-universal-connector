from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_attack_defense_defaults import (
    SiteAttackDefenseDefaultsError, project_site_attack_defense_defaults,
)


def required_result() -> dict[str, object]:
    return {key: True for key in (
        "tcpConnEnable", "udpConnEnable", "icmpConnEnable", "tcpSrcEnable",
        "udpSrcEnable", "icmpSrcEnable", "tcpScanEnable", "pingDeathEnable",
        "largePingEnable", "pingWanEnable", "winNukeAttackEnable",
        "tcpSynFinEnable", "tcpFinNoAckEnable", "specifiedOptionEnable",
    )}


class SiteAttackDefenseDefaultsProjectionTests(unittest.TestCase):
    def test_projects_common_source_fields_and_nested_options(self) -> None:
        source = required_result()
        source.update({"tcpConnLimit": 100, "largePingThreshold": 65_535,
                       "icmpTimestampRequestReject": False,
                       "specifiedOption": {"timestampEnable": True}})
        result = project_site_attack_defense_defaults(source)
        self.assertEqual(result["data"], source)
        self.assertEqual(result["missing_field_count"], 0)
        self.assertEqual(result["invalid_field_count"], 0)
        self.assertFalse(result["partial"])

    def test_tracks_missing_required_invalid_ranges_and_unknown_fields(self) -> None:
        result = project_site_attack_defense_defaults({
            "tcpConnEnable": "yes", "tcpConnLimit": 99,
            "largePingThreshold": 65_536,
            "specifiedOption": {"timestampEnable": 1, "future": True},
            "futureField": "private",
        })
        self.assertEqual(result["missing_field_count"], 13)
        self.assertEqual(result["invalid_field_count"], 4)
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertTrue(result["partial"])
        self.assertNotIn("private", repr(result))

    def test_rejects_unbounded_or_non_object_responses(self) -> None:
        for value in (None, [], {str(i): i for i in range(33)}):
            with self.subTest(shape=type(value).__name__), self.assertRaises(
                    SiteAttackDefenseDefaultsError):
                project_site_attack_defense_defaults(value)


class SiteAttackDefenseDefaultsClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "4" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_path_and_projects_response(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": required_result()}) as request:
            result = self.client.read_site_attack_defense_defaults_summary(
                self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/attack-defense/default",
            token="token")
        self.assertEqual(result["resource"],
                         "site_attack_defense_defaults_summary")
        self.assertFalse(result["partial"])

    def test_rejects_invalid_response_and_binds_controller(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_attack_defense_defaults_summary(self.site_ref)
        self.assertTrue(self.client._site_attack_defense_defaults_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/attack-defense/default"))
        self.assertFalse(self.client._site_attack_defense_defaults_request_valid(
            "/openapi/v1/other/sites/site_internal/attack-defense/default"))


if __name__ == "__main__":
    unittest.main()
