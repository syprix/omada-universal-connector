from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_attack_defense_summary import (
    SiteAttackDefenseSummaryError,
    project_site_attack_defense_summary,
)


def complete_result() -> dict[str, object]:
    result: dict[str, object] = {key: True for key in (
        "existIcmpTimestampRequestReject", "existLargePingThreshold",
        "existTcpScanReject", "icmpConnEnable", "icmpSrcEnable",
        "icmpTimestampRequestReject", "largePingEnable", "pingDeathEnable",
        "pingWanEnable", "specifiedOptionEnable", "supportIcmpTimestampRequestReject",
        "supportLargePingThreshold", "supportTcpScanReject", "tcpConnEnable",
        "tcpFinNoAckEnable", "tcpScanEnable", "tcpScanReject", "tcpSrcEnable",
        "tcpSynFinEnable", "udpConnEnable", "udpSrcEnable", "winNukeAttackEnable",
    )}
    result.update({
        "icmpConnLimit": 100, "icmpSrcLimit": 99_999,
        "largePingThreshold": 28, "tcpConnLimit": 1_000,
        "tcpSrcLimit": 500, "udpConnLimit": 2_000, "udpSrcLimit": 300,
    })
    return result


class SiteAttackDefenseProjectionTests(unittest.TestCase):
    def test_projects_every_common_boolean_and_bounded_int32_field(self) -> None:
        source = complete_result()
        projected = project_site_attack_defense_summary(source)
        self.assertEqual(projected["data"], source)
        self.assertEqual(projected["missing_field_count"], 0)
        self.assertEqual(projected["invalid_field_count"], 0)
        self.assertFalse(projected["partial"])

    def test_counts_missing_and_invalid_fields(self) -> None:
        result = project_site_attack_defense_summary({
            "icmpConnEnable": "yes", "tcpConnLimit": 99,
        })
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["missing_field_count"], 27)
        self.assertTrue(result["partial"])
        self.assertNotIn("yes", repr(result))

    def test_omits_source_specific_fields_and_counts_them(self) -> None:
        result = project_site_attack_defense_summary({
            "tcpConnEnable": True,
            "specifiedOption": {"private": "not returned"},
            "featureDescription": ["source-specific"],
        })
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertNotIn("private", repr(result))
        self.assertNotIn("source-specific", repr(result))

    def test_rejects_invalid_outer_shapes(self) -> None:
        for value in (None, [], {str(i): i for i in range(65)}):
            with self.subTest(shape=type(value).__name__), self.assertRaises(
                    SiteAttackDefenseSummaryError):
                project_site_attack_defense_summary(value)


class SiteAttackDefenseClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.site_ref = "3" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_path(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "tcpConnEnable": True, "tcpConnLimit": 1000}}) as request:
            result = self.client.read_site_attack_defense_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/attack-defense",
            token="test-token")
        self.assertEqual(result["data"], {
            "tcpConnEnable": True, "tcpConnLimit": 1000})
        self.assertTrue(result["partial"])

    def test_rejects_invalid_response_and_unknown_site(self) -> None:
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value={"result": []}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_attack_defense_summary(self.site_ref)
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_attack_defense_summary("2" * 24)

    def test_path_guard_binds_controller(self) -> None:
        self.assertTrue(self.client._site_attack_defense_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/attack-defense"))
        self.assertFalse(self.client._site_attack_defense_request_valid(
            "/openapi/v1/other/sites/site_internal/attack-defense"))


if __name__ == "__main__":
    unittest.main()
