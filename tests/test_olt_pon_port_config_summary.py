from __future__ import annotations

import unittest
from unittest.mock import patch

from app.olt_pon_port_config_summary import (
    OltPonPortConfigError,
    project_olt_pon_port_config_summary,
    project_olt_pon_port_config_page_summary,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class OltPonPortConfigProjectionTests(unittest.TestCase):
    def test_aggregates_states_and_numeric_ranges_without_port_identity(self) -> None:
        result = project_olt_pon_port_config_summary([{
            "portId": "private-pon-port", "status": "ENABLE", "downstreamFEC": "ENABLE",
            "keyExchangePeriod": 15, "dbaCalculateMode": "MIN_DELAY", "maxDistance": 40,
            "minDistance": 10, "portIsolate": "DISABLE", "onuIsolate": "ENABLE",
            "longLaserOnuAutoDetect": "ENABLE", "autoDetectInterval": 20,
            "type": "SFP", "linkStatus": "ACTIVE_WORKING", "duplexLink": "FULL",
            "speed": "XGS_PON", "upLinkSpeed": 1000, "downLinkSpeed": 10000,
            "longLaserOnuAutoIsolate": "DISABLE", "downlinkList": ["private-device"],
            "onuNum": 8,
        }])
        self.assertEqual(result["data"]["pon_port_count"], 1)
        self.assertEqual(result["data"]["enum_state_counts"]["status"], {"ENABLE": 1})
        self.assertEqual(result["data"]["enum_state_counts"]["speed"], {"XGS_PON": 1})
        self.assertEqual(result["data"]["numeric_setting_ranges"]["keyExchangePeriod"],
                         {"min": 15, "max": 15, "count": 1})
        self.assertEqual(result["data"]["onu_count"], 8)
        self.assertNotIn("private-pon-port", repr(result))
        self.assertNotIn("private-device", repr(result))

    def test_page_metadata_is_checked_and_identity_stays_redacted(self) -> None:
        result = project_olt_pon_port_config_page_summary({
            "content": [{"portId": "private-port", "status": "ENABLE"}],
            "totalElements": 9, "totalPages": 2, "number": 1, "size": 5,
            "numberOfElements": 1, "first": False, "last": False,
        }, requested_page=1, requested_size=5)
        self.assertEqual(result["page"]["total_elements"], 9)
        self.assertEqual(result["page"]["page_number"], 1)
        self.assertNotIn("private-port", repr(result))
        with self.assertRaises(OltPonPortConfigError):
            project_olt_pon_port_config_page_summary({
                "content": [], "totalElements": 0, "totalPages": 0,
                "number": 1, "size": 5, "numberOfElements": 0,
                "first": True, "last": True,
            }, requested_page=0, requested_size=5)

    def test_unknown_invalid_and_unbounded_values_are_explicit(self) -> None:
        result = project_olt_pon_port_config_summary([{
            "portId": "private", "status": "BAD", "onuNum": -1, "other": "secret"}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertGreaterEqual(result["invalid_count"], 2)
        self.assertNotIn("secret", repr(result))
        for payload in (None, {}, [{} for _ in range(65)]):
            with self.subTest(payload=type(payload).__name__), self.assertRaises(OltPonPortConfigError):
                project_olt_pon_port_config_summary(payload)


class OltPonPortConfigAdapterTests(unittest.TestCase):
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
            result = self.client.read_olt_pon_port_config_summary(self.site_ref, self.device_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
            "pon/pon-port/configs/list", token="token")
        self.assertEqual(result["resource"], "olt_pon_port_config_summary")

    def test_page_uses_validated_query_and_returns_page_summary(self) -> None:
        payload = {"result": {"content": [], "totalElements": 0, "totalPages": 0,
                              "number": 0, "size": 5, "numberOfElements": 0,
                              "first": True, "last": True}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_olt_pon_port_config_page_summary(
                self.site_ref, self.device_ref, 0, 5)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
            "pon/pon-port/configs/page?number=0&size=5", token="token")
        self.assertEqual(result["page"]["page_size"], 5)

    def test_allowlist_and_inventory_binding(self) -> None:
        path = ("/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
                "pon/pon-port/configs/list")
        self.assertTrue(self.client._olt_pon_port_config_request_valid(path))
        self.assertFalse(self.client._olt_pon_port_config_request_valid(path.replace("ctrl", "other")))
        self.client._olt_macs_by_site_ref[self.site_ref] = {}
        with patch.object(self.client, "_request_json") as request, \
                self.assertRaisesRegex(OpenApiError, "device_type_unsupported"):
            self.client.read_olt_pon_port_config_summary(self.site_ref, self.device_ref)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
