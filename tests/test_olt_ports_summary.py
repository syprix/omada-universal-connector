from __future__ import annotations

import unittest
from unittest.mock import patch

from app.olt_ports_summary import OltPortsSummaryError, project_olt_ports_summary
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class OltPortsSummaryProjectionTests(unittest.TestCase):
    def test_ports_are_aggregated_and_identifiers_are_redacted(self) -> None:
        result = project_olt_ports_summary({
            "ethUnit1PortDTOList": [
                {"port": "eth-1/0/1", "status": "ENABLE", "linkStatus": "LINK_UP",
                 "mediaType": "FIBER", "duplex": "FULL", "speedLink": 1000,
                 "type": "SFP", "description": "private port"},
                {"port": "eth-1/0/2", "status": "DISABLE", "linkStatus": "LINK_DOWN",
                 "mediaType": "COPPER", "duplex": "AUTO", "speedLink": 0,
                 "type": "COPPER", "lag": "private-lag"},
            ],
            "ponPortDTOList": [{
                "portId": "private-pon-id", "status": "ENABLE",
                "linkStatus": "ACTIVE_WORKING", "onuNum": 2,
                "downlinkList": [{"mac": "private-onu-mac", "name": "private-onu"},
                                 {"ip": "192.0.2.55"}],
            }],
        })
        data = result["data"]
        self.assertEqual(data["ethernet_port_count"], 2)
        self.assertEqual(data["ethernet_admin_state_counts"], {"ENABLE": 1, "DISABLE": 1})
        self.assertEqual(data["ethernet_link_state_counts"], {"LINK_UP": 1, "LINK_DOWN": 1})
        self.assertEqual(data["ethernet_media_type_counts"], {"FIBER": 1, "COPPER": 1})
        self.assertEqual(data["ethernet_duplex_counts"], {"FULL": 1, "AUTO": 1})
        self.assertEqual(data["ethernet_port_type_counts"], {"SFP": 1, "COPPER": 1})
        self.assertEqual(data["ethernet_negotiated_speed_counts"], [
            {"mbps": 0, "count": 1}, {"mbps": 1000, "count": 1}])
        self.assertEqual(data["pon_port_count"], 1)
        self.assertEqual(data["pon_link_state_counts"], {"ACTIVE_WORKING": 1})
        self.assertEqual(data["onu_count"], 2)
        self.assertEqual(data["onu_rows_counted"], 2)
        self.assertEqual(data["onu_count_mismatch_count"], 0)
        self.assertFalse(result["partial"])
        for private in ("eth-1/0/1", "private port", "private-lag", "private-pon-id",
                        "private-onu-mac", "private-onu", "192.0.2.55"):
            self.assertNotIn(private, repr(result))

    def test_malformed_states_and_onu_count_mismatch_are_partial(self) -> None:
        result = project_olt_ports_summary({
            "ethUnit1PortDTOList": [{"port": "p1", "status": "MAYBE",
                                     "linkStatus": "LINK_UP", "mediaType": "FIBER",
                                     "duplex": "FULL", "speedLink": 100, "type": "SFP"}],
            "ponPortDTOList": [{"portId": "id", "status": "ENABLE",
                                "linkStatus": "ACTIVE_WORKING", "onuNum": 3,
                                "downlinkList": [{"mac": "a"}]}],
            "newField": "private",
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["data"]["onu_count_mismatch_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_port_and_onu_lists_are_bounded(self) -> None:
        with self.assertRaises(OltPortsSummaryError):
            project_olt_ports_summary({"ethUnit1PortDTOList": [{}] * 65})
        excessive_nested = project_olt_ports_summary(
            {"ponPortDTOList": [{"downlinkList": [{}] * 257}]})
        self.assertTrue(excessive_nested["partial"])
        self.assertEqual(excessive_nested["invalid_count"], 1)
        with self.assertRaises(OltPortsSummaryError):
            project_olt_ports_summary([])


class OltPortsSummaryAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.device_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._inventory_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00-11-22-33-44-55"}
        self.client._olt_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00:11:22:33:44:55"}

    def test_fixed_inventory_bound_request(self) -> None:
        response = {"ethUnit1PortDTOList": [], "ponPortDTOList": []}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": response}) as request:
            result = self.client.read_olt_ports_summary(self.site_ref, self.device_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/eth-port/and/pon-port/list",
            token="token")
        self.assertEqual(result["resource"], "olt_ports_summary")
        self.assertEqual(result["site_ref"], self.site_ref)
        self.assertEqual(result["device_ref"], self.device_ref)
        self.assertFalse(result["partial"])

    def test_path_allowlist_and_olt_inventory_binding(self) -> None:
        path = "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/eth-port/and/pon-port/list"
        self.assertTrue(self.client._olt_eth_pon_list_request_valid(path))
        self.assertFalse(self.client._olt_eth_pon_list_request_valid(path.replace("ctrl", "other")))
        self.assertFalse(self.client._olt_eth_pon_list_request_valid(path + "?path=/private"))
        self.client._olt_macs_by_site_ref[self.site_ref] = {}
        with patch.object(self.client, "_request_json") as request, \
                self.assertRaisesRegex(OpenApiError, "device_type_unsupported"):
            self.client.read_olt_ports_summary(self.site_ref, self.device_ref)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
