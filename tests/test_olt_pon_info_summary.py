from __future__ import annotations

import unittest
from unittest.mock import patch

from app.olt_pon_info_summary import (
    OltPonInfoError, project_olt_auto_refresh_summary,
    project_olt_pon_information_summary,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class OltPonInfoProjectionTests(unittest.TestCase):
    def test_auto_refresh_projects_bounded_configuration(self) -> None:
        result = project_olt_auto_refresh_summary({"autoRefresh": "ENABLE", "refreshInterval": 30})
        self.assertEqual(result["data"], {"auto_refresh_enabled": True, "refresh_interval": 30})
        self.assertFalse(result["partial"])

    def test_pon_information_aggregates_without_port_identity(self) -> None:
        result = project_olt_pon_information_summary([
            {"portId": "private-pon-id-a", "onuNum": 3, "status": "ENABLE",
             "maxBandwidth": 1000, "actualBandwidth": 700, "remainBandwidth": 300,
             "opticalVcc": "3.2", "opticalBias": "20", "opticalPower": "-20.5"},
            {"portId": "private-pon-id-b", "onuNum": 2, "status": "DISABLE",
             "maxBandwidth": 2000, "actualBandwidth": 800, "remainBandwidth": 1200,
             "opticalVcc": "3.3", "opticalBias": "22", "opticalPower": "-19.5"},
        ])
        data = result["data"]
        self.assertEqual(data["pon_port_count"], 2)
        self.assertEqual(data["onu_count"], 5)
        self.assertEqual(data["laser_state_counts"], {"ENABLE": 1, "DISABLE": 1})
        self.assertEqual(data["bandwidth_totals_kbps"], {
            "maxBandwidth": 3000, "actualBandwidth": 1500, "remainBandwidth": 1500})
        self.assertEqual(data["optical_measurement_ranges"]["power"], {
            "min": "-20.5", "max": "-19.5"})
        self.assertFalse(result["partial"])
        self.assertNotIn("private-pon-id", repr(result))

    def test_malformed_values_and_response_bounds_are_reported(self) -> None:
        result = project_olt_pon_information_summary([{
            "portId": "id", "onuNum": -1, "status": "UNKNOWN",
            "maxBandwidth": 2_000_000,
        }])
        self.assertTrue(result["partial"])
        self.assertGreaterEqual(result["invalid_count"], 2)
        with self.assertRaises(OltPonInfoError):
            project_olt_pon_information_summary([{}] * 65)
        with self.assertRaises(OltPonInfoError):
            project_olt_auto_refresh_summary([])


class OltPonInfoAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.device_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._inventory_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00-11-22-33-44-55"}
        self.client._olt_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00:11:22:33:44:55"}

    def test_fixed_inventory_bound_gets(self) -> None:
        cases = (
            ("read_olt_auto_refresh_summary", "pon/service-port/statistic/configs",
             {"autoRefresh": "ENABLE", "refreshInterval": 30}),
            ("read_olt_pon_information_summary", "pon/pon-port/informations/list", []),
        )
        for method, suffix, payload in cases:
            with self.subTest(method=method), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": payload}) as request:
                result = getattr(self.client, method)(self.site_ref, self.device_ref)
                self.assertEqual(result["site_ref"], self.site_ref)
                self.assertEqual(result["device_ref"], self.device_ref)
                self.assertFalse(result["partial"])
                self.assertEqual(request.call_args.args[0], "GET")
                self.assertTrue(request.call_args.args[1].endswith(suffix))

    def test_allowlist_and_inventory_binding(self) -> None:
        path = ("/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
                "pon/pon-port/informations/list")
        self.assertTrue(self.client._olt_pon_information_request_valid(path))
        self.assertFalse(self.client._olt_pon_information_request_valid(path.replace("ctrl", "other")))
        self.client._olt_macs_by_site_ref[self.site_ref] = {}
        with patch.object(self.client, "_request_json") as request, \
                self.assertRaisesRegex(OpenApiError, "device_type_unsupported"):
            self.client.read_olt_pon_information_summary(self.site_ref, self.device_ref)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
