from __future__ import annotations

import unittest
from unittest.mock import patch

from app.olt_eth_config_summary import (
    OltEthConfigError, project_olt_eth_config_summary,
    project_olt_lag_config_summary,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class OltEthConfigProjectionTests(unittest.TestCase):
    def test_lag_summary_redacts_lag_names_descriptions_and_ids(self) -> None:
        result = project_olt_lag_config_summary([{
            "lag": "private-lag-id", "description": "private description",
            "status": 1, "speed": 1000, "duplex": 2, "flowControl": 1,
        }])
        self.assertEqual(result["data"]["lag_count"], 1)
        self.assertEqual(result["data"]["admin_state_counts"], {"ENABLED": 1})
        self.assertEqual(result["data"]["speed_mode_counts"], [{"mbps": 1000, "count": 1}])
        self.assertFalse(result["partial"])
        self.assertNotIn("private-lag-id", repr(result))
        self.assertNotIn("private description", repr(result))

    def test_port_summary_returns_link_aggregates_only(self) -> None:
        result = project_olt_eth_config_summary([{
            "port": "private-physical-port", "mediaType": 1, "description": "private label",
            "status": 1, "speed": 1000, "duplex": 2, "flowControl": 0,
            "lag": "private-lag", "speedLink": 1000, "duplexLink": 1,
            "linkStatus": 1, "type": 2, "speedMax": 10000,
        }])
        self.assertEqual(result["data"]["item_count"], 1)
        self.assertEqual(result["data"]["link_state_counts"], {"LINK_UP": 1})
        self.assertEqual(result["data"]["port_type_counts"], {"SFP": 1})
        self.assertEqual(result["data"]["ports_in_lags"], 1)
        self.assertEqual(result["data"]["negotiated_speed_counts"], [{"mbps": 1000, "count": 1}])
        self.assertFalse(result["partial"])
        for private in ("private-physical-port", "private label", "private-lag"):
            self.assertNotIn(private, repr(result))

    def test_unknown_values_are_partial_and_lists_are_bounded(self) -> None:
        result = project_olt_lag_config_summary([{
            "lag": "id", "status": 7, "speed": -1, "duplex": 4,
            "flowControl": 2, "new": "private",
        }])
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        with self.assertRaises(OltEthConfigError):
            project_olt_eth_config_summary([{}] * 129)
        with self.assertRaises(OltEthConfigError):
            project_olt_lag_config_summary({"rows": []})


class OltEthConfigAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.device_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._inventory_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00-11-22-33-44-55"}
        self.client._olt_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00:11:22:33:44:55"}

    def test_fixed_inventory_bound_paths(self) -> None:
        cases = (
            ("read_olt_eth_config_summary", "l2-feature/eth-port/port/unit1/list", []),
            ("read_olt_lag_config_summary", "l2-feature/eth-port/port/lags/list", []),
        )
        for method, suffix, payload in cases:
            with self.subTest(method=method), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": payload}) as request:
                result = getattr(self.client, method)(self.site_ref, self.device_ref)
                self.assertEqual(result["site_ref"], self.site_ref)
                self.assertEqual(result["device_ref"], self.device_ref)
                self.assertEqual(request.call_args.args[0], "GET")
                self.assertTrue(request.call_args.args[1].endswith(suffix))

    def test_path_binding_rejects_other_controller(self) -> None:
        path = ("/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
                "l2-feature/eth-port/port/lags/list")
        self.assertTrue(self.client._olt_lag_config_list_request_valid(path))
        self.assertFalse(self.client._olt_lag_config_list_request_valid(path.replace("ctrl", "other")))
        self.client._olt_macs_by_site_ref[self.site_ref] = {}
        with patch.object(self.client, "_request_json") as request, \
                self.assertRaisesRegex(OpenApiError, "device_type_unsupported"):
            self.client.read_olt_lag_config_summary(self.site_ref, self.device_ref)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
