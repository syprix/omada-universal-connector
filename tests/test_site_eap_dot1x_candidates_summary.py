from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_eap_dot1x_candidates_summary import (
    EapDot1xCandidatesError, summarize_site_eap_dot1x_candidates,
)


SITE_REF = "e" * 24


class EapDot1xCandidatesProjectionTests(unittest.TestCase):
    def test_counts_devices_ports_and_supported_flags_without_identity(self) -> None:
        result = summarize_site_eap_dot1x_candidates([
            {"name": "private AP", "mac": "00:11:22:33:44:55", "model": "EAP650",
             "version": "1.2.3", "status": "Connected", "statusCategory": 1,
             "ports": [{"port": "1", "dot1xEnable": True, "mabEnable": False,
                        "supportDot1x": True}]},
            {"name": "another AP", "statusCategory": 0,
             "ports": [{"port": "2", "dot1xEnable": False, "mabEnable": True,
                        "supportDot1x": False}]},
        ])
        self.assertEqual(result["returned_device_count"], 2)
        self.assertEqual(result["valid_port_count"], 2)
        self.assertEqual(result["status_category_counts"], {"0": 1, "1": 1})
        self.assertEqual(result["port_feature_counts"]["dot1x_enabled"],
                         {"true": 1, "false": 1})
        self.assertFalse(result["partial"])
        for secret in ("private AP", "00:11:22:33:44:55", "EAP650", "Connected", "1.2.3"):
            self.assertNotIn(secret, repr(result))

    def test_missing_unknown_and_invalid_fields_remain_explicit(self) -> None:
        result = summarize_site_eap_dot1x_candidates([
            {"statusCategory": 99, "future": "secret", "ports": [
                {"port": "x", "dot1xEnable": "yes", "futurePort": "secret"}]},
            {"ports": []},
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_status_category_count"], 2)
        self.assertEqual(result["unknown_field_count"], 2)
        self.assertGreaterEqual(result["invalid_field_count"], 1)
        self.assertNotIn("secret", repr(result))

    def test_malformed_list_and_device_shape_fail_closed_and_limits_are_visible(self) -> None:
        for raw in (None, {}):
            with self.subTest(raw=type(raw).__name__), self.assertRaises(EapDot1xCandidatesError):
                summarize_site_eap_dot1x_candidates(raw)
        malformed = summarize_site_eap_dot1x_candidates([None, {"ports": "invalid"}])
        self.assertTrue(malformed["partial"])
        self.assertGreaterEqual(malformed["invalid_field_count"], 2)
        too_many_devices = summarize_site_eap_dot1x_candidates(
            [{} for _ in range(5_001)])
        self.assertTrue(too_many_devices["partial"])
        self.assertEqual(too_many_devices["processed_device_count"], 5_000)
        self.assertTrue(too_many_devices["truncated_device_rows"])
        at_device_limit = summarize_site_eap_dot1x_candidates(
            [{"statusCategory": 0, "ports": []} for _ in range(5_000)])
        self.assertTrue(at_device_limit["coverage_unknown"])
        self.assertFalse(at_device_limit["truncated"])
        self.assertTrue(at_device_limit["partial"])
        too_many_ports = summarize_site_eap_dot1x_candidates(
            [{"ports": [{} for _ in range(257)]}])
        self.assertTrue(too_many_ports["partial"])
        self.assertEqual(too_many_ports["returned_port_count"], 257)
        self.assertEqual(too_many_ports["processed_port_count"], 256)
        self.assertEqual(too_many_ports["truncated_port_rows"], 1)
        at_port_limit = summarize_site_eap_dot1x_candidates([{
            "statusCategory": 0,
            "ports": [{"dot1xEnable": False, "mabEnable": False,
                       "supportDot1x": True} for _ in range(256)],
        }])
        self.assertEqual(at_port_limit["truncated_port_rows"], 0)
        self.assertEqual(at_port_limit["port_coverage_unknown_devices"], 1)
        self.assertTrue(at_port_limit["partial"])


class EapDot1xCandidatesClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"

    def test_uses_fixed_site_route_and_returns_summary(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": [
                    {"name": "hidden", "statusCategory": 1, "ports": []}
                ]}) as request:
            result = self.client.read_site_eap_dot1x_candidates_summary(SITE_REF)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/dot1x/eap/candidates", token="token")
        self.assertEqual(result["resource"], "site_eap_dot1x_candidates_summary")
        self.assertNotIn("hidden", repr(result))

    def test_rejects_bad_payload_and_wrong_site_or_controller_path(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_eap_dot1x_candidates_summary(SITE_REF)
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_site_eap_dot1x_candidates_summary("f" * 24)
        request.assert_not_called()
        self.assertTrue(self.client._site_eap_dot1x_candidates_request_valid(
            "/openapi/v1/ctrl/sites/site_1/dot1x/eap/candidates"))
        self.assertFalse(self.client._site_eap_dot1x_candidates_request_valid(
            "/openapi/v1/other/sites/site_1/dot1x/eap/candidates"))


if __name__ == "__main__":
    unittest.main()
