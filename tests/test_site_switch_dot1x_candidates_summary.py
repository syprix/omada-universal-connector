from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_eap_dot1x_candidates_summary import (
    EapDot1xCandidatesError, summarize_site_switch_dot1x_candidates,
)


SITE_REF = "d" * 24


class SwitchDot1xCandidatesProjectionTests(unittest.TestCase):
    def test_counts_switch_and_port_capabilities_without_identities(self) -> None:
        result = summarize_site_switch_dot1x_candidates([
            {"name": "private-switch", "mac": "00:11:22:33:44:55", "model": "SG2008",
             "version": "1.2.3", "status": "Connected", "statusCategory": 1,
             "addedInAdvanced": False, "supportVrf": True,
             "accountVrfId": "account-id", "authVrfId": "auth-id",
             "supportSingleMabAuth": True, "portConfigured": True,
             "ports": [{"port": 2, "dot1xEnable": True, "mabEnable": False,
                        "authType": 1, "operation": "aggregating", "lag": True}]},
            {"statusCategory": 0, "addedInAdvanced": True, "supportVrf": False,
             "supportSingleMabAuth": False, "portConfigured": False,
             "ports": [{"port": 3, "dot1xEnable": False, "mabEnable": True,
                        "authType": 2, "operation": "switching", "lag": False}]},
        ])
        self.assertEqual(result["returned_switch_count"], 2)
        self.assertEqual(result["valid_port_count"], 2)
        self.assertEqual(result["status_category_counts"], {"0": 1, "1": 1})
        self.assertEqual(result["auth_type_counts"], {"1": 1, "2": 1})
        self.assertEqual(result["port_flag_counts"]["dot1x_enabled"],
                         {"true": 1, "false": 1})
        self.assertEqual(result["device_flag_counts"]["vrf_supported"],
                         {"true": 1, "false": 1})
        self.assertFalse(result["partial"])
        for hidden in ("private-switch", "00:11:22:33:44:55", "SG2008", "1.2.3",
                       "Connected", "account-id", "auth-id", "aggregating", "switching"):
            self.assertNotIn(hidden, repr(result))

    def test_unknown_codes_and_malformed_fields_are_partial_without_values(self) -> None:
        result = summarize_site_switch_dot1x_candidates([
            {"statusCategory": 9, "supportVrf": "yes", "future": "hidden",
             "ports": [{"port": 1, "dot1xEnable": True, "mabEnable": False,
                        "authType": 9, "lag": False, "futurePort": "hidden"}]},
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_status_category_count"], 1)
        self.assertEqual(result["unknown_auth_type_count"], 1)
        self.assertGreaterEqual(result["invalid_field_count"], 1)
        self.assertGreaterEqual(result["unknown_field_count"], 2)
        self.assertNotIn("hidden", repr(result))
        with self.assertRaises(EapDot1xCandidatesError):
            summarize_site_switch_dot1x_candidates({"rows": []})


class SwitchDot1xCandidatesClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"

    def test_reads_fixed_site_route_and_returns_summary(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": [
                    {"mac": "00:11:22:33:44:55", "statusCategory": 1, "ports": []}
                ]}) as request:
            result = self.client.read_site_switch_dot1x_candidates_summary(SITE_REF)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/dot1x/candidates", token="token")
        self.assertEqual(result["resource"], "site_switch_dot1x_candidates_summary")
        self.assertNotIn("00:11:22:33:44:55", repr(result))

    def test_rejects_bad_payload_unknown_site_and_wrong_controller_path(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": None}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_switch_dot1x_candidates_summary(SITE_REF)
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_site_switch_dot1x_candidates_summary("a" * 24)
        request.assert_not_called()
        self.assertTrue(self.client._site_switch_dot1x_candidates_request_valid(
            "/openapi/v1/ctrl/sites/site_1/dot1x/candidates"))
        self.assertFalse(self.client._site_switch_dot1x_candidates_request_valid(
            "/openapi/v1/other/sites/site_1/dot1x/candidates"))


if __name__ == "__main__":
    unittest.main()
