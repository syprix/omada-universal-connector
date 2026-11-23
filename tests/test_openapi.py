from __future__ import annotations

import json
import hashlib
import os
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class FakeResponse:
    def __init__(self, payload: object, status: int = 200,
                 content_type: str = "application/json") -> None:
        self.body = json.dumps(payload).encode()
        self.status = status
        self.content_type = content_type

    def read(self, _limit: int = -1) -> bytes:
        return self.body

    def getheader(self, _name: str, default: str = "") -> str:
        return self.content_type or default


class FakeConnection:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, str, bytes | None, dict[str, str]]] = []
        self.closed = False

    def request(self, method: str, path: str, body: bytes | None = None,
                headers: dict[str, str] | None = None) -> None:
        self.calls.append((method, path, body, headers or {}))

    def getresponse(self) -> FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


class OpenApiClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.client_id = self._secret("client-id", "client-id-value")
        self.client_secret = self._secret("client-secret", "client-secret-value")
        self.config = OpenApiConfig(
            "https://controller.example", "controller_1", self.client_id,
            self.client_secret, cert_sha256="a" * 64, page_size=2,
            max_pages=3,
        )
        self.client = OmadaOpenApiClient(self.config)
        self.connections: list[FakeConnection] = []

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_bridge_device_summary_reads_both_bounded_grids(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[
                    {"result": {"totalRows": 1, "currentPage": 1, "currentSize": 1,
                                "data": [{"mac": "00:11:22:33:44:55", "name": "secret",
                                          "type": "bridge", "status": 2, "detailStatus": 1}],
                                "stackData": [{"stackId": "secret-stack", "stackStatus": 2}]}},
                    {"result": {"totalRows": 1, "currentPage": 1, "currentSize": 1,
                                "data": [{"mac": "00:11:22:33:44:66", "type": "bridge",
                                          "status": 0, "detailStatus": 1}]}}
                ]) as request:
            result = self.client.read_site_bridge_device_summary(site_ref)
        self.assertEqual(result["adopted"]["by_source_status_code"], {"2": 1})
        self.assertEqual(result["pending"]["by_source_status_code"], {"0": 1})
        for secret in ("00:11:22:33:44:55", "00:11:22:33:44:66", "secret-stack"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertIn("bridge-devices/adopted?page=1&pageSize=2", request.call_args_list[0].args[1])
        self.assertIn("bridge-devices/pending?page=1&pageSize=2", request.call_args_list[1].args[1])

    def test_topology_snapshot_summary_uses_documented_v2_site_path(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": {"topologyNodes": [{"mac": "private"}],
                               "topologyEdges": [{"upLinkMac": "private",
                                                  "downLinkMac": "missing",
                                                  "blocked": True}]},
                }) as request:
            result = self.client.read_site_topology_snapshot_summary(site_ref)
        self.assertEqual(result["node_count"], 1)
        self.assertEqual(result["edge_count"], 1)
        self.assertEqual(result["blocked_edge_count"], 1)
        self.assertEqual(result["missing_endpoint_reference_count"], 1)
        self.assertNotIn("private", json.dumps(result))
        self.assertEqual(request.call_args.args[1],
                         "/openapi/v2/controller_1/sites/site-1/topology")

    def test_qos_service_profile_summary_bounds_pages_and_redacts_rows(self) -> None:
        site_ref = "b" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": {"totalRows": 1, "currentPage": 1, "currentSize": 1,
                               "data": [{"id": "private", "defaultProfile": True,
                                         "name": "private", "protocol": 2,
                                         "destStartPort": 443}]},
                }) as request:
            result = self.client.read_site_gateway_qos_service_profiles_summary(site_ref)
        self.assertEqual(result["profile_count"], 1)
        self.assertEqual(result["default_profile_count"], 1)
        self.assertEqual(result["protocol_profile_counts"]["tcp_udp"], 1)
        self.assertNotIn("private", json.dumps(result))
        self.assertEqual(request.call_args.args[1],
                         "/openapi/v1/controller_1/sites/site-1/profiles/service-type"
                         "?page=1&pageSize=1000")
        self.assertTrue(self.client._site_gateway_qos_service_types_request_valid(
            "/openapi/v1/controller_1/sites/site-1/profiles/service-type?page=10&pageSize=1000"))
        for invalid in (
            "/openapi/v1/other/sites/site-1/profiles/service-type?page=1&pageSize=1000",
            "/openapi/v1/controller_1/sites/site-1/profiles/service-type?page=11&pageSize=1000",
            "/openapi/v1/controller_1/sites/site-1/profiles/service-type?page=1&pageSize=1001",
        ):
            self.assertFalse(self.client._site_gateway_qos_service_types_request_valid(invalid))

    def test_qos_service_profile_summary_accepts_documented_empty_grid_example(self) -> None:
        site_ref = "c" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": {"totalRows": 0, "currentPage": 0, "currentSize": 0,
                               "data": []},
                }):
            result = self.client.read_site_gateway_qos_service_profiles_summary(site_ref)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["profile_count"], 0)

    def test_site_upnp_template_comparison_uses_selected_inventories(self) -> None:
        site_ref, template_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        self.client._site_template_ids_by_ref[template_ref] = "template-1"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[
                    {"result": {"enable": True, "wanPortIds": ["wan-a", "wan-b"],
                                "networkIds": ["network-a"], "supportByDsLiteAndMapE": True}},
                    {"result": {"enable": True, "wanPortIds": ["wan-a"],
                                "networkIds": ["network-a"], "supportByDsLiteAndMapE": False}},
                ]) as request:
            result = self.client.compare_site_upnp_with_template(site_ref, template_ref)
        self.assertEqual(result["by_field"], {"enabled": "same", "wan_port_count": "different",
                                              "network_count": "same",
                                              "supports_ds_lite_or_map_e": "different"})
        self.assertEqual(request.call_count, 2)
        self.assertIn("sites/site-1/upnp", request.call_args_list[0].args[1])
        self.assertIn("sitetemplates/template-1/upnp", request.call_args_list[1].args[1])

    def test_wan_qos_summary_reads_wans_and_paginated_rules(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[
                    {"result": {"data": [{"id": "wan-id", "name": "Private WAN",
                                            "configured": True}]}},
                    {"result": {"totalRows": 1, "currentPage": 1, "currentSize": 1,
                                "data": [{"id": "rule-id", "wan": "wan-id", "status": True,
                                          "direction": 2, "inBandwidth": 1000,
                                          "outBandwidth": 2000}]}}
                ]) as request:
            result = self.client.read_site_wan_qos_summary(site_ref)
        self.assertEqual(result["rules_with_exact_wan_match"], 1)
        for secret in ("wan-id", "rule-id", "Private WAN", "1000", "2000"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertIn("/qos/gateway/wans", request.call_args_list[0].args[1])
        self.assertIn("/qos/gateway/bwcs?page=1&pageSize=2", request.call_args_list[1].args[1])

    def test_vpn_server_status_read_binds_selected_protocol_and_redacts_rows(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 2, "currentPage": 1, "currentSize": 2,
                    "data": [{"vpnType": 5, "status": 2, "userName": "private",
                              "loginIp": "192.0.2.1"},
                             {"vpnType": 5, "status": 2, "virtualIp": "198.51.100.1"}]}}) as request:
            result = self.client.read_site_vpn_server_status_summary(site_ref, 5)
        self.assertEqual(result["by_source_status_code"], {"2": 2})
        for secret in ("private", "192.0.2.1", "198.51.100.1"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertIn("filters.vpnType=5", request.call_args.args[1])
        self.assertIn("page=1", request.call_args.args[1])
        self.assertIn("pageSize=2", request.call_args.args[1])

    def test_vpn_client_status_read_binds_documented_protocol_and_redacts_rows(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 2, "currentPage": 1, "currentSize": 2,
                    "data": [{"vpnType": 4, "status": 9, "userName": "private",
                              "remotePeerIp": "192.0.2.1"},
                             {"vpnType": 4, "status": 9, "virtualIp": "198.51.100.1"}]}}) as request:
            result = self.client.read_site_vpn_client_status_summary(site_ref, 4)
        self.assertEqual(result["by_source_status_code"], {"9": 2})
        for secret in ("private", "192.0.2.1", "198.51.100.1"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertIn("filters.vpnType=4", request.call_args.args[1])
        self.assertIn("page=1", request.call_args.args[1])
        self.assertIn("pageSize=2", request.call_args.args[1])
        with self.assertRaises(OpenApiError):
            self.client.read_site_vpn_client_status_summary(site_ref, 2)

    def test_s2s_status_read_counts_raw_codes_and_redacts_peers(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 1, "currentPage": 1, "currentSize": 1,
                    "supportWireguardStatus": True,
                    "data": [{"status": 8, "remotePeerIp": "192.0.2.1",
                              "name": "private", "vpnType": 2}]}}) as request:
            result = self.client.read_site_vpn_s2s_status_summary(site_ref, 2)
        self.assertEqual(result["status_code_counts"], {"8": 1})
        self.assertEqual(result["vpn_type_name"], "ipsec")
        for secret in ("192.0.2.1", "private"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertIn("filters.vpnType=2&page=1&pageSize=2", request.call_args.args[1])
        with self.assertRaises(OpenApiError):
            self.client.read_site_vpn_s2s_status_summary(site_ref, 0)

    def test_ssid_topology_read_joins_same_site_inventory_and_redacts_macs(self) -> None:
        site_ref, ssid_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        mac = "00:11:22:33:44:55"

        def refresh_ssids(ref: str) -> dict[str, object]:
            self.assertEqual(ref, site_ref)
            self.client._ssid_ids_by_site_ref[site_ref] = {ssid_ref: "ssid-1"}
            return {"status": "ok", "resource": "ssids", "items": []}

        def list_devices(ref: str) -> dict[str, object]:
            self.assertEqual(ref, site_ref)
            device_ref = "c" * 24
            self.client._inventory_macs_by_site_ref[site_ref] = {device_ref: mac}
            return {"items": [{"device_ref": device_ref, "device_type": "ap"}]}

        with patch.object(self.client, "list_ssids", side_effect=refresh_ssids) as ssids, \
                patch.object(self.client, "list_devices", side_effect=list_devices) as devices, \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"deviceMacs": [mac]}}) as request:
            result = self.client.read_site_ssid_topology_device_summary(site_ref, ssid_ref)
        self.assertEqual(result["device_class_counts"]["ap"], 1)
        self.assertNotIn(mac, json.dumps(result))
        self.assertEqual((ssids.call_count, devices.call_count), (1, 1))
        self.assertIn("/openapi/v3/controller_1/sites/site-1/topology/ssids/ssid-1/devices",
                      request.call_args.args[1])

    def test_v2_ssid_topology_counts_only_freshly_bound_opaque_strings(self):
        site_ref, ssid_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        def inventory(ref):
            self.assertEqual(ref, site_ref)
            self.client._ssid_ids_by_site_ref[site_ref] = {ssid_ref: "ssid-1"}
            return {"items": [{"ssid_ref": ssid_ref}]}
        with patch.object(self.client, "list_ssids", side_effect=inventory), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0, "msg": "", "result": ["raw-ref", "not-a-mac"]}) as request:
            result = self.client.read_site_ssid_topology_reference_count(site_ref, ssid_ref)
        self.assertEqual(result["reference_count"], 2)
        self.assertNotIn("raw-ref", json.dumps(result))
        self.assertIn("/openapi/v2/controller_1/sites/site-1/topology/ssids/ssid-1/devices",
                      request.call_args.args[1])

    def test_v2_ssid_topology_rejects_ambiguous_fresh_inventory_binding(self):
        site_ref, ssid_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        def inventory(_ref):
            self.client._ssid_ids_by_site_ref[site_ref] = {ssid_ref: "ssid-1"}
            return {"items": [{"ssid_ref": ssid_ref}, {"ssid_ref": ssid_ref}]}
        with patch.object(self.client, "list_ssids", side_effect=inventory), \
                patch.object(self.client, "_request_json") as request:
            with self.assertRaises(OpenApiError):
                self.client.read_site_ssid_topology_reference_count(site_ref, ssid_ref)
        request.assert_not_called()

    def test_ipsec_failover_summary_paginates_and_redacts_reference_values(self):
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        self.client.config = replace(self.config, page_size=2, max_pages=20)
        page1 = {"errorCode": 0, "msg": "", "result": {
            "totalRows": 3, "currentPage": 1, "currentSize": 2,
            "data": [
                {"id": "secret-rule", "name": "private-name",
                 "primary": {"id": "secret-primary", "name": "secret-ipsec", "status": 0},
                 "candidates": [{"id": "secret-candidate", "name": "secret-candidate-name", "status": 1}],
                 "failBack": True, "failBackTime": 17},
                {"primary": None, "candidates": [], "failBack": False},
            ]}}
        page2 = {"errorCode": 0, "msg": "", "result": {
            "totalRows": 3, "currentPage": 2, "currentSize": 1,
            "data": [{"candidates": None, "failBackTime": -2}]}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[page1, page2]) as request:
            result = self.client.read_site_ipsec_failover_summary(site_ref)
        self.assertEqual(result["rule_count"], 3)
        self.assertEqual(result["reported_rule_count"], 3)
        self.assertEqual(result["primary_reference_count"], 1)
        self.assertEqual(result["candidate_reference_count"], 1)
        self.assertEqual(result["failback_enabled_count"], 1)
        self.assertEqual(result["failback_disabled_count"], 1)
        self.assertEqual(result["failback_unknown_count"], 1)
        self.assertEqual(result["failback_time_field_present_count"], 2)
        self.assertEqual(result["failback_time_field_missing_count"], 1)
        self.assertTrue(result["partial"])
        self.assertFalse(result["tunnel_status_returned"])
        self.assertFalse(result["failback_time_values_returned"])
        self.assertNotIn("secret", json.dumps(result))
        self.assertEqual(request.call_count, 2)
        self.assertIn("pageSize=2", request.call_args_list[0].args[1])
        self.assertIn("pageSize=2", request.call_args_list[1].args[1])

    def test_gateway_sim_support_uses_fresh_site_inventory_and_redacts_dual_sim_code(self):
        site_ref, gateway_ref = "a" * 24, "b" * 24
        gateway_mac = "00:11:22:33:44:55"
        self.client._site_ids_by_ref[site_ref] = "site-1"
        def refresh(ref):
            self.assertEqual(ref, site_ref)
            self.client._gateway_macs_by_site_ref[site_ref] = {gateway_ref: gateway_mac}
            return {"items": [{"device_ref": gateway_ref, "device_type": "gateway"}]}
        with patch.object(self.client, "list_devices", side_effect=refresh) as inventory, \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0, "msg": "", "result": {
                        "supportSms": True, "supportLte": False,
                        "supportDualSms": 2, "supportDualSim": 0}}) as request:
            result = self.client.read_site_gateway_sim_sms_support_summary(site_ref, gateway_ref)
        self.assertEqual(inventory.call_count, 1)
        self.assertTrue(result["sim_sms_supported"])
        self.assertFalse(result["lte_supported"])
        self.assertEqual(result["dual_sms_supported_sim_count"], 1)
        self.assertEqual(result["dual_sim_capability"], "unknown")
        self.assertTrue(result["dual_sim_source_value_present"])
        self.assertNotIn(gateway_mac, json.dumps(result))
        self.assertIn("/gateways/00:11:22:33:44:55/sim/sms/support",
                      request.call_args.args[1])

    def test_gateway_sim_support_rejects_ambiguous_or_non_gateway_inventory(self):
        site_ref, gateway_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        inventories = (
            {"items": [{"device_ref": gateway_ref, "device_type": "gateway"},
                       {"device_ref": gateway_ref, "device_type": "gateway"}]},
            {"items": [{"device_ref": gateway_ref, "device_type": "ap"}]},
        )
        for inventory in inventories:
            with self.subTest(inventory=inventory):
                with patch.object(self.client, "list_devices", return_value=inventory), \
                        patch.object(self.client, "_request_json") as request:
                    with self.assertRaises(OpenApiError):
                        self.client.read_site_gateway_sim_sms_support_summary(site_ref, gateway_ref)
                request.assert_not_called()

    def test_v2_vlan_topology_counts_opaque_values_after_fresh_network_vlan_binding(self):
        site_ref, network_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        def networks(ref):
            self.assertEqual(ref, site_ref)
            self.client._network_ids_by_site_ref[site_ref] = {network_ref: "network-1"}
            return {"items": [{"network_ref": network_ref, "purpose": 0, "vlan": 42}]}
        with patch.object(self.client, "list_networks", side_effect=networks), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0, "msg": "", "result": ["opaque-device-ref"]}) as request:
            result = self.client.read_site_vlan_topology_reference_count(site_ref, network_ref, 42)
        self.assertEqual(result["reference_count"], 1)
        self.assertNotIn("opaque-device-ref", json.dumps(result))
        self.assertIn("/openapi/v2/controller_1/sites/site-1/topology/network-1/vlan/42/devices",
                      request.call_args.args[1])

    def test_v2_vlan_topology_rejects_vlan_mismatch_before_upstream_call(self):
        site_ref, network_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        def networks(_ref):
            self.client._network_ids_by_site_ref[site_ref] = {network_ref: "network-1"}
            return {"items": [{"network_ref": network_ref, "purpose": 0, "vlan": 43}]}
        with patch.object(self.client, "list_networks", side_effect=networks), \
                patch.object(self.client, "_request_json") as request:
            with self.assertRaises(OpenApiError):
                self.client.read_site_vlan_topology_reference_count(site_ref, network_ref, 42)
        request.assert_not_called()

    def test_lan_switch_profile_assignments_read_direct_grid_and_marks_missing_data(self):
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[
                    {"totalRows": 3, "currentPage": 1, "currentSize": 2,
                     "data": [{"name": "secret", "mac": "private-mac",
                               "profiles": {"port1": "secret-profile", "port2": "vlan"}},
                              {"name": "switch-2", "mac": "private-mac-2", "profiles": {}}]},
                    {"totalRows": 3, "currentPage": 2, "currentSize": 1,
                     "data": [{"name": "switch-3", "mac": "private-mac-3"}]},
                ]) as request:
            result = self.client.read_site_lan_switch_profile_assignments_summary(site_ref)
        self.assertEqual(result["device_rows"], 3)
        self.assertEqual(result["profile_assignment_count"], 2)
        self.assertEqual(result["rows_without_profile_data"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private-mac", json.dumps(result))
        self.assertIn("/lan-switch-setting?page=1&pageSize=2", request.call_args_list[0].args[1])
        self.assertIn("/lan-switch-setting?page=2&pageSize=2", request.call_args_list[1].args[1])

    def test_lan_switch_profile_assignments_caps_non_dividing_pages_at_1000(self):
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        page_size = 128
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[
                    *[{"totalRows": 1_100, "currentPage": page, "currentSize": page_size,
                       "data": [{"profiles": {f"profile-{(page - 1) * page_size + offset}": "v"}}
                                for offset in range(page_size - (1 if page == 8 else 0))] +
                               ([{"profiles": {f"extra-{n}": "v" for n in range(10)}}]
                                if page == 8 else [])} for page in range(1, 9)],
                ]) as request:
            self.client.config = replace(self.config, page_size=page_size, max_pages=20)
            result = self.client.read_site_lan_switch_profile_assignments_summary(site_ref)
        self.assertEqual(result["device_rows"], 1_000)
        self.assertEqual(result["reported_device_rows"], 1_100)
        self.assertEqual(result["profile_assignment_count"], 1_000)
        self.assertTrue(result["partial"])
        self.assertEqual(request.call_count, 8)
        self.assertTrue(all("pageSize=128" in call.args[1] for call in request.call_args_list))

    def test_ap_topology_clients_binds_inventory_ap_and_redacts_client_rows(self) -> None:
        site_ref, device_ref = "a" * 24, "b" * 24
        mac = "00:11:22:33:44:55"
        self.client._site_ids_by_ref[site_ref] = "site-1"

        def refresh_inventory(ref: str) -> dict[str, object]:
            self.assertEqual(ref, site_ref)
            self.client._device_macs_by_site_ref[site_ref] = {device_ref: mac}
            return {"items": [{"device_ref": device_ref, "device_type": "ap"}]}

        with patch.object(self.client, "list_devices", side_effect=refresh_inventory), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": [
                    {"mac": "02:00:00:00:00:01", "name": "private", "wireless": True,
                     "guest": False, "type": "phone"},
                    {"mac": "02:00:00:00:00:02", "wireless": False, "guest": True,
                     "type": "computer"}]}) as request:
            result = self.client.read_site_ap_topology_clients_summary(site_ref, device_ref)
        self.assertEqual(result["by_connection"],
                         {"wireless": 1, "wired": 1, "unknown": 0})
        for secret in (mac, "02:00:00:00:00:01", "private", "phone"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertIn("/openapi/v2/controller_1/sites/site-1/topology/devices/"
                      "00:11:22:33:44:55/clients", request.call_args.args[1])
        with self.assertRaises(OpenApiError):
            self.client.read_site_ap_topology_clients_summary(site_ref, "c" * 24)

    def test_ap_topology_client_path_guard_accepts_only_controller_inventory_mac(self):
        good = ("/openapi/v2/controller_1/sites/site-1/topology/devices/"
                "00:11:22:33:44:55/clients")
        self.assertTrue(self.client._site_ap_topology_clients_request_valid(good))
        self.assertFalse(self.client._site_ap_topology_clients_request_valid(
            good.replace("controller_1", "other")))
        self.assertFalse(self.client._site_ap_topology_clients_request_valid(
            good.replace("00:11:22:33:44:55", "not-a-mac")))

    def test_network_delivery_read_binds_selected_site_network_and_redacts_ids(self):
        site_ref, network_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"

        def refresh_networks(ref: str) -> dict[str, object]:
            self.assertEqual(ref, site_ref)
            self.client._network_ids_by_site_ref[site_ref] = {network_ref: "network-1"}
            return {"items": [{"network_ref": network_ref}]}

        with patch.object(self.client, "list_networks", side_effect=refresh_networks), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "successDevices": ["private-device"], "successStacks": [],
                    "failDevices": [], "failStacks": [],
                    "deliveringDevices": ["working-device"], "deliveringStacks": [],
                    "doneDevicesNum": 1, "totalDevicesNum": 2, "state": 1}}) as request:
            result = self.client.read_site_network_delivery_summary(site_ref, network_ref)
        self.assertEqual(result["state"], "delivering")
        self.assertNotIn("private-device", json.dumps(result))
        self.assertNotIn("network-1", json.dumps(result))
        self.assertIn("/networks/network-1/brief-process", request.call_args.args[1])
        with self.assertRaises(OpenApiError):
            self.client.read_site_network_delivery_summary(site_ref, "c" * 24)

    def test_site_lan_port_profiles_read_paginates_and_redacts_profile_values(self):
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        row = {"id": "private-id", "name": "Private Profile", "type": 2,
               "flag": 2, "networkTagsSetting": 1, "poe": 1, "dot1x": 2,
               "bandWidthCtrlType": 1, "vlanConfigEnable": True,
               "portIsolationEnable": False, "lldpMedEnable": True,
               "loopbackDetectEnable": True, "spanningTreeEnable": False,
               "nativeNetworkId": "private-network", "nativeBridgeVlan": 100}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 1, "currentPage": 1, "currentSize": 1,
                    "data": [row]}}) as request:
            result = self.client.read_site_lan_port_profiles_summary(site_ref)
        self.assertEqual(result["profile_enum_counts"]["type"], {"2": 1})
        for secret in ("private-id", "Private Profile", "private-network", "100"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertIn("/lan-profiles?page=1&pageSize=2", request.call_args.args[1])

    def test_controller_upgrade_plans_read_counts_and_redacts_plan(self):
        row = {"id": "secret-id", "modelTypeInfo": {"showModel": "Secret Model",
                                                       "compoundModel": "Private Model"},
               "siteNames": ["Secret Site"], "siteNum": 2,
               "currentVersion": ["1.0"], "targetVersion": "2.0",
               "scheduledUpgradeTime": "2026-01-01T00:00:00Z", "operator": "secret-user",
               "fromRollback": False}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 1, "currentPage": 1, "currentSize": 1,
                    "data": [row]}}) as request:
            result = self.client.read_controller_upgrade_plans_summary()
        self.assertEqual(result["site_association_count"], 2)
        for secret in ("secret-id", "Secret Model", "Private Model", "Secret Site",
                       "1.0", "2.0", "2026-01-01", "secret-user"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertIn("/upgrade/overview/plans?page=1&pageSize=2",
                      request.call_args.args[1])

    def test_controller_try_beta_settings_reads_two_sources_and_marks_missing_fields(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[
                    {"result": {"enable": True}}, {"result": {"channel": 1}}]) as request:
            result = self.client.read_controller_try_beta_settings_summary()
        self.assertTrue(result["preview_firmware_enabled"])
        self.assertEqual(result["preview_firmware_channel"], "release_candidate")
        self.assertFalse(result["partial"])
        self.assertEqual([call.args[1] for call in request.call_args_list], [
            "/openapi/v1/controller_1/upgrade/overview/try-beta",
            "/openapi/v1/controller_1/upgrade/overview/try-beta/channel",
        ])
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[
                    {"result": {}}, {"result": {"channel": 9}}]):
            incomplete = self.client.read_controller_try_beta_settings_summary()
        self.assertIsNone(incomplete["preview_firmware_enabled"])
        self.assertEqual(incomplete["preview_firmware_channel"], "unknown")
        self.assertTrue(incomplete["partial"])

    def test_controller_auto_check_upgrade_summary_bounds_pages_and_redacts_details(self):
        rows = [
            {"id": "private-plan", "modelTypeInfos": [{"showModel": "Private model"}],
             "siteNames": ["Private site"], "siteNum": 2, "autoCheckTime": "private-time",
             "channel": 2, "occurrence": {"hour": 2, "minute": 15}},
            {"siteNum": 1, "channel": 0},
            {"siteNum": 4, "channel": 8},
        ]
        pages = [
            {"result": {"totalRows": 3, "currentPage": 1, "currentSize": 2,
                        "data": rows[:2]}},
            {"result": {"totalRows": 3, "currentPage": 2, "currentSize": 1,
                        "data": rows[2:]}},
        ]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=pages) as request:
            result = self.client.read_controller_auto_check_upgrade_summary()
        self.assertEqual(result["channel_counts"], {
            "stable": 1, "release_candidate": 0, "beta": 1, "unknown": 1})
        self.assertEqual(result["site_association_count"], 7)
        self.assertEqual(result["pages_fetched"], 2)
        self.assertTrue(result["partial"])
        self.assertEqual([call.args[1] for call in request.call_args_list], [
            "/openapi/v1/controller_1/upgrade/autoCheck?page=1&pageSize=2",
            "/openapi/v1/controller_1/upgrade/autoCheck?page=2&pageSize=2",
        ])
        for secret in ("private-plan", "Private model", "Private site", "private-time"):
            self.assertNotIn(secret, json.dumps(result))

    def test_controller_auto_check_upgrade_marks_missing_fields_and_rejects_bad_page(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 1, "currentPage": 1, "currentSize": 1,
                    "data": [{}]}}):
            result = self.client.read_controller_auto_check_upgrade_summary()
        self.assertTrue(result["partial"])
        self.assertEqual(result["channel_counts"]["unknown"], 1)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 1, "currentPage": 2, "currentSize": 1,
                    "data": [{"siteNum": 1, "channel": 0}]}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_auto_check_upgrade_summary()

    def test_controller_auto_check_upgrade_accepts_zero_page_only_for_empty_first_page(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 0, "currentPage": 0, "currentSize": 0, "data": []}}):
            result = self.client.read_controller_auto_check_upgrade_summary()
        self.assertEqual(result["plan_count"], 0)
        self.assertTrue(result["coverage_complete"])
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 0, "currentPage": 0, "currentSize": 1, "data": [{}]}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_auto_check_upgrade_summary()

    def test_site_lan_multicast_read_paginates_and_redacts_configuration(self):
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        row = {"id": "private-id", "name": "Private Multicast",
               "networks": [{"networkId": "private-network", "networkName": "Private LAN"}],
               "protocol": 0, "unknownMulticastRule": 2,
               "unknownMulticastExceptDevice": {"enable": True, "deviceList": []},
               "floodKnownEnable": True, "querierEnable": False,
               "routerPortEnable": True,
               "snoopConfig": {"reportSuppressionEnable": True,
                               "reportSuppressionExceptDevice": {"enable": False,
                                                                  "deviceList": []}}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 1, "currentPage": 1, "currentSize": 1,
                    "data": [row]}}) as request:
            result = self.client.read_site_lan_multicast_summary(site_ref)
        self.assertEqual(result["protocol_counts"]["igmp"], 1)
        self.assertEqual(result["unknown_multicast_rule_counts"]["router_port_first"], 1)
        for secret in ("private-id", "Private Multicast", "private-network", "Private LAN"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertIn("/lan-multicasts?page=1&pageSize=2", request.call_args.args[1])

    def test_site_bandwidth_rules_read_paginates_and_redacts_policy_details(self):
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        row = {"id": "private-id", "name": "Private rule", "index": 9,
               "status": True, "sourceType": 0, "sourceIds": ["private-network"],
               "wanPortIds": ["private-wan"], "upstreamBandwidth": 1000,
               "upstreamBandwidthUnit": 1, "downstreamBandwidth": 2500,
               "downstreamBandwidthUnit": 2, "mode": 1}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 1, "currentPage": 1, "currentSize": 1,
                    "data": [row]}}) as request:
            result = self.client.read_site_bandwidth_rules_summary(site_ref)
        self.assertEqual(result["activation_counts"]["enabled"], 1)
        self.assertEqual(result["bandwidth_unit_counts"]["downstream"]["mbps"], 1)
        for secret in ("private-id", "Private rule", "private-network", "private-wan", "1000", "2500"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertIn("/bandwidth-control/rules?page=1&pageSize=2", request.call_args.args[1])

    def test_site_log_notification_read_redacts_categories_and_destination_ids(self):
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        result = {"webhookConfig": {"webhookEnable": True, "webhookId": "private-webhook"},
                  "logNotifications": [{"key": "LOGIN_OK", "shortMsg": "Private text",
                                        "alert": False, "event": True,
                                        "email": True, "webhook": False}],
                  "alertEmailSetting": {"alertEmailEnable": True, "delayEnable": False,
                                        "delay": 30}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": result}) as request:
            projected = self.client.read_site_log_notification_summary(site_ref)
        self.assertEqual(projected["notification_category_count"], 1)
        self.assertEqual(projected["channel_enablement_counts"]["event"]["enabled"], 1)
        for secret in ("private-webhook", "LOGIN_OK", "Private text", "30"):
            self.assertNotIn(secret, json.dumps(projected))
        self.assertIn("/site/log-notification", request.call_args.args[1])

    def test_site_voucher_all_time_summary_reports_independent_values_and_redacts_money(self):
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        result = {category: {"count": index + 1, "amount": "120.50",
                             "duration": index * 60, "currency": "USD"}
                  for index, category in enumerate(("current", "inuse", "expired", "unused", "created"))}
        result["supportVoucherTrafficStat"] = False
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0, "msg": "", "result": result}) as request:
            projected = self.client.read_site_voucher_all_time_summary(site_ref)
        self.assertEqual(projected["voucher_counts"]["unused"], 4)
        self.assertEqual(projected["voucher_durations_minutes"]["unused"], 180)
        self.assertEqual(projected["voucher_traffic_statistics_supported"], False)
        self.assertEqual(projected["missing_fields"], [])
        for secret in ("120.50", "USD"):
            self.assertNotIn(secret, json.dumps(projected))
        self.assertTrue(request.call_args.args[1].endswith(
            "/sites/site-1/hotspot/vouchers/statistics/summary"))

    def test_site_lan_network_interface_read_redacts_values_and_allows_type_zero(self):
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        row = {"id": "private-id", "name": "Private network", "purpose": 1,
               "interfaceIds": ["private-port"], "vlanType": 0, "vlan": 120,
               "application": 0, "gatewaySubnet": "192.0.2.1/24",
               "igmpSnoopEnable": True}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "data": [row]}}) as request:
            result = self.client.read_site_lan_network_interface_summary(site_ref, 0)
        self.assertEqual(result["interface_vlan_type_counts"]["single"], 1)
        for secret in ("private-id", "Private network", "private-port", "192.0.2.1", "120"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertIn("/lan-networks/interface?type=0", request.call_args.args[1])
        with self.assertRaises(OpenApiError):
            self.client.read_site_lan_network_interface_summary(site_ref, 1)

    def test_ssid_client_count_binds_selected_site_and_uses_flat_query_fields(self) -> None:
        site_ref, ssid_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        self.client._ssid_ids_by_site_ref[site_ref] = {ssid_ref: "ssid-1"}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 2, "currentPage": 1, "currentSize": 2,
                    "data": [{"mac": "00:11:22:33:44:55", "name": "private"},
                             {"id": "secret"}]}}) as request:
            result = self.client.read_site_ssid_client_count_summary(site_ref, ssid_ref)
        self.assertEqual(result["client_count"], 2)
        self.assertTrue(result["coverage_complete"])
        self.assertNotIn("private", json.dumps(result))
        url = request.call_args.args[1]
        self.assertIn("/clientList/ssid-1?page=1&pageSize=100", url)
        self.client._site_ids_by_ref["c" * 24] = "site-2"
        with patch.object(self.client, "list_ssids", return_value={"items": []}):
            with self.assertRaises(OpenApiError):
                self.client.read_site_ssid_client_count_summary("c" * 24, ssid_ref)

    def test_site_remote_logging_read_redacts_destination_values(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "remoteLog": {"enable": True, "host": "logs.example.invalid",
                                  "port": 6514, "moreClientLog": True, "resource": 2}}}) as request:
            result = self.client.read_site_remote_logging_summary(site_ref)
        self.assertTrue(result["enabled"])
        self.assertTrue(result["client_logs_enabled"])
        self.assertEqual(result["resource_source"], "override")
        self.assertTrue(result["destination_host_configured"])
        self.assertTrue(result["destination_port_configured"])
        self.assertNotIn("logs.example.invalid", json.dumps(result))
        self.assertNotIn("6514", json.dumps(result))
        self.assertIn("/sites/site-1/remote-logging", request.call_args.args[1])

    def test_controller_upgrade_log_summary_reads_one_redacted_page(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 1, "currentPage": 1, "currentSize": 1,
                    "data": [{"id": "private", "siteNames": ["private-site"],
                              "operator": "operator", "currentVersion": ["1.0"],
                              "targetVersion": "2.0", "upgradeTime": "2026-01-01",
                              "rollbacked": False, "failedDeviceNum": 0}]}}) as request:
            result = self.client.read_controller_upgrade_log_summary()
        self.assertEqual(result["rollbacked_counts"], {"true": 0, "false": 1})
        self.assertTrue(result["coverage_complete"])
        for secret in ("private", "private-site", "operator", "1.0", "2.0", "2026-01-01"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertTrue(request.call_args.args[1].endswith("/upgrade/overview/logs?page=1&pageSize=100"))

    def test_controller_upgrade_log_inventory_returns_only_opaque_refs(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"errorCode": 0,
                    "msg": "", "result": {"totalRows": 1, "currentPage": 1,
                    "currentSize": 1, "data": [{"id": "upgrade-secret",
                    "targetVersion": "private-version"}]}}) as request:
            result = self.client.read_controller_upgrade_log_inventory(1, 100)
        self.assertEqual(result["selectable_log_count"], 1)
        self.assertEqual(len(result["upgrade_log_refs"][0]), 24)
        self.assertNotIn("upgrade-secret", json.dumps(result))
        self.assertNotIn("private-version", json.dumps(result))
        self.assertIn("page=1&pageSize=100", request.call_args.args[1])

    def test_controller_upgrade_failed_devices_refreshes_selector_and_redacts_rows(self) -> None:
        ref = self.client._opaque_ref("firmware-upgrade-log", "upgrade-secret")
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[
                    {"errorCode": 0, "msg": "", "result": {
                        "totalRows": 1, "currentPage": 1, "currentSize": 1,
                        "data": [{"id": "upgrade-secret"}]}},
                    {"errorCode": 0, "msg": "", "result": {
                        "totalRows": 2, "currentPage": 1, "currentSize": 2,
                        "data": [{"type": "gateway", "mac": "00:11:22:33:44:55",
                                  "deviceName": "private-device", "siteName": "private-site",
                                  "currentVersion": "private-version"},
                                 {"type": "switch"}]}}]) as request:
            result = self.client.read_controller_upgrade_failed_devices_summary(ref)
        self.assertEqual(result["device_type_counts"],
                         {"gateway": 1, "switch": 1, "ap": 0, "unknown": 0})
        self.assertEqual(result["failed_device_count"], 2)
        for secret in ("upgrade-secret", "00:11:22:33:44:55", "private-device",
                       "private-site", "private-version"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(request.call_count, 2)
        self.assertIn("upgrade-secret", request.call_args_list[1].args[1])

    def test_controller_upgrade_failed_devices_rejects_ambiguous_fresh_selector(self) -> None:
        ref = self.client._opaque_ref("firmware-upgrade-log", "upgrade-secret")
        rows = [{"id": "upgrade-secret"}, {"id": "upgrade-secret"}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"errorCode": 0,
                    "msg": "", "result": {"totalRows": 2, "currentPage": 1,
                    "currentSize": 2, "data": rows}}) as request:
            with self.assertRaisesRegex(OpenApiError, "upgrade_log_ref_unknown"):
                self.client.read_controller_upgrade_failed_devices_summary(ref)
        self.assertEqual(request.call_count, 1)

    def test_stack_cable_test_logs_refresh_stack_binding_and_redact_ports_and_time(self) -> None:
        site_ref, stack_id = "a" * 24, "stack-one"
        self.client._site_ids_by_ref[site_ref] = "site-1"
        stack_ref = self.client._opaque_ref("stack", "site-1:" + stack_id)
        logs = [{"type": 1, "timeStamp": 123456789,
                 "testPortList": [], "completePortList": [{"port": 7,
                 "standardPort": 107}], "cancelPortList": [], "timeoutPortList": []}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[
                    {"errorCode": 0, "result": {"totalRows": 1, "currentPage": 1,
                     "currentSize": 1, "data": [{"id": stack_id}]}},
                    {"errorCode": 0, "result": logs}]) as request:
            result = self.client.read_site_stack_cable_test_log_summary(site_ref, stack_ref)
        self.assertEqual(result["port_entry_counts"]["completed_port_entries"], 1)
        self.assertEqual(result["log_type_counts"]["completed"], 1)
        for secret in ("stack-one", "123456789", '"port":', "107"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertIn("/sites/site-1/stacks", request.call_args_list[0].args[1])
        self.assertIn("/cable-test/stacks/stack-one/logs", request.call_args_list[1].args[1])

    def test_site_poe_schedule_summary_reads_each_fixed_site_feed(self) -> None:
        site_ref = "a" * 24
        switch_ref = "b" * 24
        mac = "aa:bb:cc:dd:ee:ff"
        self.client._site_ids_by_ref[site_ref] = "site-1"
        self.client._switch_macs_by_site_ref[site_ref] = {switch_ref: mac}
        with (patch.object(self.client, "list_devices", return_value={
                  "items": [{"device_ref": switch_ref, "device_type": "switch"}]}),
              patch.object(self.client, "_access_token", return_value="token"),
              patch.object(self.client, "_request_json", side_effect=[
                  {"result": [{"mac": mac, "poePort": {"poePortIds": [1]}}]},
                  {"result": [{"mac": mac, "totalPowerUsed": 1, "totalPower": 10}]},
                  {"result": [{"profileId": "profile"}]},
              ]) as request,
              patch.object(self.client, "_read_pages", side_effect=[
                  [{"status": True, "turnOnTime": "profile", "poePortsMap": {mac: [1]}}],
                  [{"switchMac": mac, "port": 1, "supportPoe": True,
                    "poeDisplayType": 1, "poe": 1, "poeStatus": 1,
                    "power": 1, "voltage": 52, "current": 0.1}],
              ]) as pages):
            result = self.client.read_site_poe_schedule_summary(site_ref)
        self.assertEqual(result["data"]["switches"][0]["power_budget"]["available_watts"], 9)
        self.assertEqual(request.call_count, 3)
        paths = [call.args[1] for call in request.call_args_list]
        self.assertEqual(paths, [
            "/openapi/v1/controller_1/sites/site-1/poe-ports",
            "/openapi/v1/controller_1/sites/site-1/dashboard/poe-usage",
            "/openapi/v1/controller_1/sites/site-1/time-range-profiles",
        ])
        self.assertEqual(pages.call_count, 2)

    def test_site_reboot_schedule_summary_refreshes_inventory_and_uses_fixed_route(self) -> None:
        site_ref = "a" * 24
        device_ref = "b" * 24
        mac = "aa:bb:cc:dd:ee:ff"
        self.client._site_ids_by_ref[site_ref] = "site-1"
        self.client._device_macs_by_site_ref[site_ref] = {device_ref: mac}
        payload = {"result": [{"status": True, "deviceMacs": [mac],
                              "time": {"timingType": 1, "hour": 4, "minute": 0}}]}
        with (patch.object(self.client, "list_devices", return_value={"items": []}) as inventory,
              patch.object(self.client, "_access_token", return_value="token"),
              patch.object(self.client, "_request_json", return_value=payload) as request):
            result = self.client.read_site_reboot_schedule_summary(site_ref)
        inventory.assert_called_once_with(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/controller_1/sites/site-1/reboot-schedules", token="token")
        self.assertEqual(result["resource"], "site_reboot_schedule_summary")
        self.assertEqual(result["schedule_rows"][0][6], [device_ref])

    def test_reboot_schedule_source_path_is_controller_bound(self) -> None:
        path = "/openapi/v1/controller_1/sites/site-1/reboot-schedules"
        with patch.object(self.client, "_connection",
                          side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path, token="token")
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json(
                    "GET", path.replace("controller_1", "other-controller"), token="token")

    def _secret(self, name: str, value: str) -> str:
        path = os.path.join(self.tempdir.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(value)
        os.chmod(path, 0o600)
        return path

    def respond(self, payload: object, status: int = 200,
                content_type: str = "application/json") -> FakeConnection:
        connection = FakeConnection(FakeResponse(payload, status, content_type))
        self.connections.append(connection)
        return connection

    def queue_responses(self, payloads: list[object]) -> None:
        queued = iter(payloads)

        def connect() -> FakeConnection:
            return self.respond(next(queued))

        self.connection_patch = patch.object(self.client, "_connection", side_effect=connect)
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)

    @staticmethod
    def token_payload() -> dict[str, object]:
        return {"errorCode": 0, "result": {"accessToken": "token-value"}}

    @staticmethod
    def grid(rows: list[object], page: int, total: int) -> dict[str, object]:
        return {"errorCode": 0, "result": {
            "totalRows": total, "currentPage": page,
            "currentSize": len(rows), "data": rows,
        }}

    def test_site_audit_summary_uses_fixed_site_path_and_projects_safe_fields(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        payload = self.grid([{
            "time": 1_700_000_000_100, "auditType": "Log", "level": "Warning",
            "result": "Succeed", "operator": "private-user", "content": "private text",
            "oldValue": {"secret": "value"},
        }], 1, 1)
        with patch.object(self.client, "_access_token", return_value="token"), \
             patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_site_audit_log_window_summary(
                site_ref, 1_700_000_000_000, 1_700_000_001_000)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(result["resource"], "site_audit_log_window_summary")
        method, path = request.call_args.args[:2]
        self.assertEqual(method, "GET")
        self.assertTrue(path.startswith(
            "/openapi/v1/controller_1/sites/site-1/audit-logs?page=1&pageSize=2&sorts.time=asc&filters.times="))
        from urllib.parse import parse_qs
        query = parse_qs(path.split("?", 1)[1])
        self.assertEqual(json.loads(query["filters.times"][0]), [{
            "timeStart": 1_700_000_000_000, "timeEnd": 1_700_000_001_000}])
        rendered = json.dumps(result)
        self.assertIn("Warning", rendered)
        for private in ("private-user", "private text", "secret", "value"):
            self.assertNotIn(private, rendered)

    def test_controller_audit_route_is_fixed_and_controller_bound(self) -> None:
        allowed = ("/openapi/v1/controller_1/audit-logs?page=1&pageSize=10&sorts.time=asc&"
                   "filters.times=%5B%7B%22timeStart%22%3A1700000000000%2C%22timeEnd%22%3A1700000001000%7D%5D")
        self.assertTrue(self.client._audit_log_request_valid(allowed))
        self.assertFalse(self.client._audit_log_request_valid(allowed.replace("controller_1", "other")))
        self.assertFalse(self.client._audit_log_request_valid(allowed + "&searchKey=private"))
        self.assertFalse(self.client._audit_log_request_valid(allowed.replace("page=1", "page=11")))
        with patch.object(self.client, "_access_token", return_value="token"), \
             patch.object(self.client, "_request_json", return_value=self.grid([], 1, 0)) as request:
            result = self.client.read_controller_audit_log_window_summary(
                1_700_000_000_000, 1_700_000_001_000)
        self.assertEqual(result["total_count"], 0)
        self.assertEqual(result["resource"], "controller_audit_log_window_summary")
        self.assertIn("/openapi/v1/controller_1/audit-logs?", request.call_args.args[1])

    def test_audit_read_is_bounded_and_marks_truncation(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        rows = [{"time": 1_700_000_000_100, "auditType": "Log",
                 "level": "Information", "result": "Succeed"}]
        with patch.object(self.client, "_access_token", return_value="token"), \
             patch.object(self.client, "_request_json", side_effect=[
                 self.grid(rows, 1, 8), self.grid(rows, 2, 8), self.grid(rows, 3, 8)]) as request:
            result = self.client.read_site_audit_log_window_summary(
                site_ref, 1_700_000_000_000, 1_700_000_001_000)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(result["returned_count"], 3)
        self.assertEqual(result["total_count"], 8)
        self.assertTrue(result["partial"])
        self.assertTrue(result["pagination"]["page_limit_reached"])

    def test_token_body_and_access_token_header(self) -> None:
        self.queue_responses([
            self.token_payload(), self.grid([{"siteId": "site-1"}], 1, 1),
        ])
        result = self.client.list_sites()
        self.assertEqual(result["count"], 1)
        token_call = self.connections[0].calls[0]
        self.assertEqual(token_call[:2], ("POST", OmadaOpenApiClient.TOKEN_PATH))
        self.assertEqual(json.loads(token_call[2] or b""), {
            "omadacId": "controller_1", "client_id": "client-id-value",
            "client_secret": "client-secret-value",
        })
        sites_call = self.connections[1].calls[0]
        self.assertEqual(sites_call[1], "/openapi/v1/controller_1/sites?page=1&pageSize=2")
        self.assertEqual(sites_call[3]["Authorization"], "AccessToken=token-value")
        self.assertTrue(all(connection.closed for connection in self.connections))

    def test_exact_full_final_page_uses_total_rows(self) -> None:
        self.queue_responses([
            self.token_payload(), self.grid([{"siteId": "a"}, {"siteId": "b"}], 1, 4),
            self.grid([{"siteId": "c"}, {"siteId": "d"}], 2, 4),
        ])
        result = self.client.list_sites()
        self.assertEqual(result["count"], 4)
        self.assertEqual([c.calls[0][1] for c in self.connections[1:]], [
            "/openapi/v1/controller_1/sites?page=1&pageSize=2",
            "/openapi/v1/controller_1/sites?page=2&pageSize=2",
        ])

    def test_network_inventory_is_paginated_redacted_and_opaque(self) -> None:
        self.client._site_ids_by_ref["a" * 24] = "site-1"
        private = {"id": "network-1", "name": "Secret LAN", "gatewaySubnet": "192.0.2.1/24",
                   "domain": "private.example", "purpose": 0, "vlan": 44, "vlanType": 0,
                   "primary": True, "portal": False}
        self.queue_responses([self.token_payload(), self.grid([private, {"id": "network-x"}], 1, 3),
                              self.grid([{"id": "network-2", "name": "Other LAN", "purpose": 1}], 2, 3)])
        result = self.client.list_networks("a" * 24)
        self.assertEqual(result["count"], 3)
        item = result["items"][0]
        self.assertEqual(item["network_ref"], self.client._opaque_ref("network", "site-1:network-1"))
        self.assertEqual(item["vlan"], 44)
        rendered = json.dumps(result)
        for private_value in ("Secret LAN", "192.0.2.1/24", "private.example", "network-1"):
            self.assertNotIn(private_value, rendered)
        self.assertEqual(self.connections[1].calls[0][1],
                         "/openapi/v2/controller_1/sites/site-1/lan-networks?page=1&pageSize=2")
        self.assertEqual(self.connections[2].calls[0][1],
                         "/openapi/v2/controller_1/sites/site-1/lan-networks?page=2&pageSize=2")

    def test_upstream_http_and_api_codes_are_preserved_as_numbers(self) -> None:
        self.respond({"errorCode": -1, "msg": "private controller detail"},
                     200, "application/json")
        connection = self.connections[-1]
        with patch.object(self.client, "_connection", return_value=connection):
            with self.assertRaises(OpenApiError) as ctx:
                self.client._request_json("POST", self.client.TOKEN_PATH)
        self.assertEqual(ctx.exception.code, "openapi_rejected")
        self.assertEqual(ctx.exception.upstream_http_status, 200)
        self.assertEqual(ctx.exception.upstream_error_code, -1)
        self.assertNotIn("private controller detail", str(ctx.exception))

        self.respond({"msg": "private controller detail"}, 502, "application/json")
        connection = self.connections[-1]
        with patch.object(self.client, "_connection", return_value=connection):
            with self.assertRaises(OpenApiError) as ctx:
                self.client._request_json("POST", self.client.TOKEN_PATH)
        self.assertEqual(ctx.exception.code, "openapi_http_error")
        self.assertEqual(ctx.exception.upstream_http_status, 502)

    def test_network_inventory_rejects_malformed_scalar_types(self) -> None:
        self.client._site_ids_by_ref["a" * 24] = "site-1"
        self.queue_responses([self.token_payload(), self.grid([{"id": "net", "vlan": True}], 1, 1)])
        with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
            self.client.list_networks("a" * 24)

    def test_gateway_ipv6_ip_passthrough_reads_only_the_documented_boolean(self) -> None:
        site_ref, gateway_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        self.client._gateway_macs_by_site_ref[site_ref] = {
            gateway_ref: "00:11:22:33:44:55",
        }
        self.queue_responses([{"errorCode": 0, "result": {
            "enable": False, "privateGatewayLabel": "omit-this",
        }}])
        with patch.object(self.client, "_access_token", return_value="fixture-token"):
            result = self.client.read_gateway_ipv6_ip_passthrough(site_ref, gateway_ref)

        self.assertEqual(result, {
            "status": "ok", "resource": "gateway_ipv6_ip_passthrough",
            "scope": "gateway_ipv6_ip_passthrough", "site_ref": site_ref,
            "gateway_ref": gateway_ref, "data": {"enable": False},
        })
        self.assertNotIn("omit-this", json.dumps(result))
        self.assertEqual(self.connections[0].calls[0][:2], (
            "GET", "/openapi/v1/controller_1/sites/site-1/gateways/00:11:22:33:44:55/network/ipv6",
        ))

    def test_gateway_ipv6_ip_passthrough_rejects_non_boolean_and_unknown_gateway(self) -> None:
        site_ref, gateway_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        self.client._gateway_macs_by_site_ref[site_ref] = {
            gateway_ref: "00:11:22:33:44:55",
        }
        for value in (1, "false", None):
            with self.subTest(enable=value):
                self.queue_responses([{"errorCode": 0, "result": {"enable": value}}])
                with patch.object(self.client, "_access_token", return_value="fixture-token"):
                    with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                        self.client.read_gateway_ipv6_ip_passthrough(site_ref, gateway_ref)

        with patch.object(self.client, "_access_token", return_value="fixture-token"):
            with self.assertRaisesRegex(OpenApiError, "gateway_ref_unknown"):
                self.client.read_gateway_ipv6_ip_passthrough(site_ref, "c" * 24)
        self.assertEqual(sum(len(connection.calls) for connection in self.connections), 3)

    def test_ssid_inventory_is_paginated_opaque_and_redacted(self) -> None:
        self.client._site_ids_by_ref["a" * 24] = "site-1"
        rows = [
            {"id": "ssid-1", "ssidId": "legacy-id", "name": "Secret WiFi", "description": True,
             "chooseDevices": 2, "band": 7, "guestNetEnable": False, "security": 3,
             "broadcast": True, "vlanEnable": True, "vlanId": 44, "vlanPoolIds": "44,45",
             "password": "secret-password", "mac": "00:11:22:33:44:55", "ip": "192.0.2.1"},
            {"id": "ssid-2", "name": "Another private name", "description": False},
        ]
        self.queue_responses([self.token_payload(), self.grid(rows[:1], 1, 2), self.grid(rows[1:], 2, 2)])
        result = self.client.list_ssids("a" * 24)
        self.assertEqual(result["count"], 2)
        item = result["items"][0]
        self.assertEqual(item["ssid_ref"], self.client._opaque_ref("ssid", "site-1:ssid-1"))
        self.assertEqual(item["band"], 7)
        self.assertTrue(item["enabled"])
        rendered = json.dumps(result)
        for secret in ("ssid-1", "legacy-id", "Secret WiFi", "Another private name", "secret-password",
                       "00:11:22:33:44:55", "192.0.2.1", "44,45"):
            self.assertNotIn(secret, rendered)
        self.assertEqual(self.connections[1].calls[0][1],
                         "/openapi/v2/controller_1/sites/site-1/wireless-network/ssids?page=1&pageSize=2")
        self.assertEqual(self.connections[2].calls[0][1],
                         "/openapi/v2/controller_1/sites/site-1/wireless-network/ssids?page=2&pageSize=2")

    def test_ssid_rows_reject_invalid_types(self) -> None:
        self.client._site_ids_by_ref["a" * 24] = "site-1"
        for row in ({"id": "ssid-1", "band": True}, {"id": "ssid-1", "broadcast": 1}, {"name": "missing id"}):
            with self.subTest(row=row):
                self.queue_responses([self.token_payload(), self.grid([row], 1, 1)])
                with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                    self.client.list_ssids("a" * 24)

    def test_group_ssid_detail_requires_unique_current_same_site_membership(self) -> None:
        site_ref, group_ref, ssid_ref = "a" * 24, "b" * 24, "c" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        self.client._wlan_group_ids_by_site_ref[site_ref] = {group_ref: "group-private"}
        self.client._ssid_ids_by_site_ref[site_ref] = {ssid_ref: "ssid-private"}
        with patch.object(self.client, "read_site_wlan_group_summary",
                          return_value={"items": [{"group_ref": group_ref}]}), \
                patch.object(self.client, "list_ssids",
                             return_value={"items": [{"ssid_ref": ssid_ref}]}), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[
                    {"result": {"data": [{"id": "ssid-private"}],
                                "totalRows": 1, "currentPage": 1, "currentSize": 1}},
                    {"result": {"ssidEnable": True, "band": 3, "deviceType": 1,
                                "name": "private SSID", "pskSetting": {"securityKey": "secret"}}},
                ]) as request:
            result = self.client.read_site_wlan_group_ssid_config_summary(
                site_ref, group_ref, ssid_ref)
        self.assertTrue(result["ssid_enabled"])
        self.assertEqual(result["band_enabled"],
                         {"2.4ghz": True, "5ghz": True, "6ghz": False})
        rendered = json.dumps(result)
        for private in ("ssid-private", "group-private", "private SSID", "secret"):
            self.assertNotIn(private, rendered)
        self.assertIn("/wlans/group-private/ssids/ssid-private", request.call_args_list[-1].args[1])

        for members in ([{"id": "other-ssid"}],
                        [{"id": "ssid-private"}, {"id": "ssid-private"}]):
            with self.subTest(members=members), \
                    patch.object(self.client, "read_site_wlan_group_summary",
                                 return_value={"items": [{"group_ref": group_ref}]}), \
                    patch.object(self.client, "list_ssids",
                                 return_value={"items": [{"ssid_ref": ssid_ref}]}), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": {
                        "data": members, "totalRows": len(members),
                        "currentPage": 1, "currentSize": len(members)}}):
                with self.assertRaisesRegex(OpenApiError, "ssid_group_binding_unavailable"):
                    self.client.read_site_wlan_group_ssid_config_summary(
                        site_ref, group_ref, ssid_ref)

    def test_ap_group_info_rejects_reserved_path_segments_and_keeps_dotted_ids(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        rows = [
            {"id": ".", "primary": False, "apNum": 0},
            {"id": "..", "primary": False, "apNum": 0},
            {"id": "group.v1", "primary": True, "apNum": 1},
        ]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages_result", return_value={
                    "totalRows": 3, "data": rows,
                }):
            inventory = self.client.read_site_ap_group_summary(site_ref)
        self.assertEqual(len(inventory["groups"]), 1)
        self.assertEqual(inventory["group_ref_missing_rows"], 2)
        group_ref = inventory["groups"][0]["group_ref"]
        self.assertEqual(self.client._ap_group_ids_by_site_ref[site_ref][group_ref], "group.v1")
        for invalid_id in (".", ".."):
            path = f"/openapi/v1/controller_1/sites/site-1/ap-groups/{invalid_id}/info"
            self.assertFalse(self.client._site_ap_group_info_request_valid(path))
        valid_path = "/openapi/v1/controller_1/sites/site-1/ap-groups/group.v1/info"
        self.assertTrue(self.client._site_ap_group_info_request_valid(valid_path))

        with patch.object(self.client, "read_site_ap_group_summary",
                          return_value={"groups": [{"group_ref": group_ref}]}), \
                patch.object(self.client, "_request_json") as detail_request:
            self.client._ap_group_ids_by_site_ref[site_ref][group_ref] = ".."
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_ap_group_info_summary(site_ref, group_ref)
        detail_request.assert_not_called()

        self.client._ap_group_ids_by_site_ref[site_ref][group_ref] = "group.v1"
        with patch.object(self.client, "read_site_ap_group_summary",
                          return_value={"groups": [{"group_ref": group_ref}]}), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0,
                    "result": {"primary": True, "apNum": 1,
                               "remainingBinding": {"0": 1, "1": 2, "2": 3}},
                }) as detail_request:
            detail = self.client.read_site_ap_group_info_summary(site_ref, group_ref)
        self.assertEqual(detail["status"], "ok")
        self.assertEqual(detail_request.call_args.args[1], valid_path)

    def test_lte_wan_settings_use_fixed_site_path_and_redact_provider_values(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        source = {"portUuid": "parent-private", "portName": "private port",
                  "portDesc": "private description", "lteWanPortsConfig": [{
                      "portUuId": "port-private", "status": 3, "cardStatus": 4,
                      "mobileData": True, "dataRoaming": False, "networkMode": 4,
                      "bandMode": 1, "dialupSetting": {"networkSearch": 1,
                          "isp": "private carrier", "apnMode": 1, "apn": "private.apn"},
                  }]}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": source}) as request:
            result = self.client.read_site_lte_wan_config_summary(site_ref)
        self.assertEqual(result["documented_modem_status_code_counts"]["3"], 1)
        self.assertEqual(result["configured_flags"]["mobile_data"]["enabled"], 1)
        self.assertIn("internet/lte/ports-config", request.call_args.args[1])
        rendered = repr(result)
        for private in ("parent-private", "private port", "private description",
                        "port-private", "private carrier", "private.apn"):
            self.assertNotIn(private, rendered)

    def test_nat_exception_reader_paginates_fixed_route_and_redacts_rule_data(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        row = {"id": "private-rule-id", "name": "private rule name", "status": True,
               "lanList": ["private-lan-id"], "interface": "private-wan-id",
               "description": "private rule description"}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 1, "currentPage": 1, "currentSize": 1,
                    "data": [row]}}) as request:
            result = self.client.read_site_nat_exception_summary(site_ref)
        self.assertEqual(result["rule_status_counts"]["enabled"], 1)
        self.assertEqual(result["lan_entry_count"], 1)
        self.assertIn("page=1&pageSize=100", request.call_args.args[1])
        self.assertIn("wired-networks/disable-nats", request.call_args.args[1])
        for private in ("private-rule-id", "private rule name", "private-lan-id",
                        "private-wan-id", "private rule description"):
            self.assertNotIn(private, repr(result))

    def test_nat_exception_reader_fetches_each_bounded_page(self) -> None:
        site_ref = "b" * 24
        self.client._site_ids_by_ref[site_ref] = "site-2"
        first_rows = [{"name": f"rule-{index}", "status": True,
                       "lanList": [], "interface": "wan"} for index in range(100)]
        second_rows = [{"name": "rule-last", "status": False,
                        "lanList": ["private-lan"], "interface": "wan"}]
        results = [
            {"totalRows": 101, "currentPage": 1, "currentSize": 100,
             "data": first_rows},
            {"totalRows": 101, "currentPage": 2, "currentSize": 1,
             "data": second_rows},
        ]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json",
                             side_effect=[{"result": item} for item in results]) as request:
            result = self.client.read_site_nat_exception_summary(site_ref)
        self.assertEqual(request.call_count, 2)
        self.assertIn("page=1&pageSize=100", request.call_args_list[0].args[1])
        self.assertIn("page=2&pageSize=100", request.call_args_list[1].args[1])
        self.assertEqual(result["reported_rule_count"], 101)
        self.assertEqual(result["returned_rule_count"], 101)
        self.assertEqual(result["rule_status_counts"]["disabled"], 1)

    def test_device_mac_integer_status_and_output_redaction(self) -> None:
        self.client._site_ids_by_ref["a" * 24] = "site-1"
        private = {"mac": "00:11:22:33:44:55", "status": 1,
                   "name": "Private device", "ip": "192.0.2.5",
                   "serialNumber": "serial-private", "model": "EAP",
                   "firmwareVersion": "1.2.3"}
        self.queue_responses([self.token_payload(), self.grid([private], 1, 1)])
        result = self.client.list_devices("a" * 24)
        rendered = json.dumps(result)
        self.assertEqual(result["items"][0]["state"], 1)
        self.assertEqual(result["items"][0]["model"], "EAP")
        self.assertEqual(result["items"][0]["firmware"], "1.2.3")
        for secret in ("00:11:22:33:44:55", "Private device", "192.0.2.5", "serial-private"):
            self.assertNotIn(secret, rendered)

    def test_client_dash_mac_reference_and_private_fields_redacted(self) -> None:
        self.client._site_ids_by_ref["a" * 24] = "site-1"
        row = {"mac": "00-11-22-33-44-55", "name": "secret-name", "hostName": "secret-host",
               "vendor": "secret-vendor", "ip": "192.0.2.4", "ssid": "secret-ssid",
               "apName": "secret-ap", "wireless": True, "channel": 36, "rssi": -52,
               "snr": 42, "rxRate": 1200, "txRate": 900, "healthScore": 98,
               "active": True, "lastSeen": 1234}
        self.queue_responses([self.token_payload(), self.grid([row], 1, 1)])
        result = self.client.list_clients("a" * 24)
        item = result["items"][0]
        self.assertEqual(result["count"], 1)
        self.assertRegex(item["client_ref"], r"^[0-9a-f]{24}$")
        self.assertEqual(item["rssi"], -52)
        rendered = json.dumps(result)
        for secret in (row["mac"], row["name"], row["hostName"], row["vendor"], row["ip"], row["ssid"], row["apName"]):
            self.assertNotIn(secret, rendered)

    def test_client_rows_with_invalid_mac_or_diagnostic_type_rejected(self) -> None:
        self.client._site_ids_by_ref["a" * 24] = "site-1"
        for row in ({"mac": "not-a-mac"}, {"mac": "00:11:22:33:44:55", "rssi": "strong"}):
            with self.subTest(row=row):
                self.queue_responses([self.token_payload(), self.grid([row], 1, 1)])
                with self.assertRaises(OpenApiError) as ctx:
                    self.client.list_clients("a" * 24)
                self.assertEqual(ctx.exception.code, "openapi_response_invalid")

    def test_site_entity_summary_uses_inventory_bound_fixed_get(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        entity = {
            "siteId": "site-1", "name": "Private site", "type": 1,
            "tagIds": ["private-tag"], "region": "Private region",
            "timeZone": "Secret/Zone", "ntpEnable": True,
            "ntpServers": ["private.ntp"], "dst": {"enable": True},
            "scenario": "private-scenario", "longitude": 5, "latitude": 8,
            "address": "Private address", "supportES": True, "supportL2": False,
        }
        self.queue_responses([self.token_payload(), {"errorCode": 0, "result": entity}])
        result = self.client.read_site_entity_summary(site_ref)
        self.assertEqual(result["resource"], "site_entity_summary")
        self.assertEqual(result["site_ref"], site_ref)
        self.assertEqual(result["data"]["site_tier"], "pro")
        self.assertTrue(result["data"]["ntp_enabled"])
        self.assertFalse(result["partial"])
        self.assertEqual(self.connections[1].calls[0][0], "GET")
        self.assertEqual(self.connections[1].calls[0][1],
                         "/openapi/v1/controller_1/sites/site-1")
        self.assertNotIn("Private", repr(result))
        self.assertNotIn("Secret/Zone", repr(result))

    def test_site_iptv_summary_uses_inventory_bound_fixed_get(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        self.queue_responses([self.token_payload(), {"errorCode": 0, "result": {
            "enable": True, "wanPortId": "private-wan", "mode": 0,
            "portConfig": [{"portId": "private-port", "type": 2}],
            "customConfig": None, "dslConfig": None}}])
        result = self.client.read_site_iptv_summary(site_ref)
        self.assertEqual(result["resource"], "site_iptv_summary")
        self.assertEqual(result["data"]["mode"], "bridge")
        self.assertFalse(result["partial"])
        self.assertEqual(self.connections[1].calls[0][0], "GET")
        self.assertEqual(self.connections[1].calls[0][1],
                         "/openapi/v1/controller_1/sites/site-1/setting/service/iptv")
        self.assertNotIn("private-wan", repr(result))
        self.assertNotIn("private-port", repr(result))

    def test_site_template_upnp_uses_template_inventory_reference(self) -> None:
        self.queue_responses([
            self.token_payload(),
            {"errorCode": 0, "result": {"totalRows": 1, "currentPage": 1,
             "currentSize": 1, "data": [{"id": "private-template-id"}]}},
            self.token_payload(),
            {"errorCode": 0, "result": {"enable": True,
             "wanPortIds": ["private-wan-id"], "networkIds": ["private-network-id"],
             "supportByDsLiteAndMapE": False}},
        ])
        inventory = self.client.list_site_templates()
        template_ref = inventory["items"][0]["site_template_ref"]
        result = self.client.read_site_template_upnp_summary(template_ref)
        self.assertEqual(result["resource"], "site_template_upnp_summary")
        self.assertEqual(result["data"], {"enabled": True, "wan_port_count": 1,
                         "network_count": 1, "supports_ds_lite_or_map_e": False})
        self.assertEqual(self.connections[3].calls[0][1],
                         "/openapi/v1/controller_1/sitetemplates/private-template-id/upnp")
        for value in ("private-wan-id", "private-network-id"):
            self.assertNotIn(value, repr(result))

    def test_site_template_igmp_uses_template_inventory_reference(self) -> None:
        self.queue_responses([
            self.token_payload(),
            {"errorCode": 0, "result": {"totalRows": 1, "currentPage": 1,
             "currentSize": 1, "data": [{"id": "private-template-id", "name": "Room",
                                           "type": 0, "bindSiteNum": 2,
                                           "settings": ["IPTV"]}]}},
            self.token_payload(),
            {"errorCode": 0, "result": {"enable": True, "version": 2,
                                         "wanPortId": "private-wan-id"}},
        ])
        inventory = self.client.list_site_templates()
        self.assertEqual(inventory["count"], 1)
        self.assertNotIn("private-template-id", repr(inventory))
        self.assertNotIn("Room", repr(inventory))
        template_ref = inventory["items"][0]["site_template_ref"]
        result = self.client.read_site_template_igmp_summary(template_ref)
        self.assertEqual(result["resource"], "site_template_igmp_summary")
        self.assertEqual(result["data"], {"enabled": True, "version": 2,
                         "wan_port_configured": True})
        self.assertEqual(self.connections[1].calls[0][1],
                         "/openapi/v1/controller_1/sitetemplates?page=1&pageSize=2")
        self.assertEqual(self.connections[3].calls[0][1],
                         "/openapi/v1/controller_1/sitetemplates/private-template-id/setting/service/iptv/igmp")
        self.assertNotIn("private-wan-id", repr(result))

    def test_site_template_ssh_uses_template_inventory_reference(self) -> None:
        self.queue_responses([
            self.token_payload(),
            {"errorCode": 0, "result": {"totalRows": 1, "currentPage": 1,
             "currentSize": 1, "data": [{"id": "private-template-id"}]}},
            self.token_payload(),
            {"errorCode": 0, "result": {"sshEnable": True, "sshServerPort": 2222,
                                         "layer3Access": False, "controllerSecret": "omit"}},
        ])
        inventory = self.client.list_site_templates()
        template_ref = inventory["items"][0]["site_template_ref"]
        result = self.client.read_site_template_ssh_summary(template_ref)
        self.assertEqual(result["resource"], "site_template_ssh_summary")
        self.assertEqual(result["data"], {"enabled": True,
                         "layer3_access_enabled": False, "server_port": 2222})
        self.assertTrue(result["partial"])
        self.assertEqual(self.connections[3].calls[0][1],
                         "/openapi/v1/controller_1/sitetemplates/private-template-id/ssh")
        self.assertNotIn("private-template-id", repr(result))
        self.assertNotIn("controllerSecret", repr(result))

    def test_site_template_iptv_uses_template_inventory_reference(self) -> None:
        self.queue_responses([
            self.token_payload(),
            {"errorCode": 0, "result": {"totalRows": 1, "currentPage": 1,
             "currentSize": 1, "data": [{"id": "private-template-id"}]}},
            self.token_payload(),
            {"errorCode": 0, "result": {"enable": True, "mode": 0,
             "wanPortId": "private-wan-id", "portConfig": [
                 {"portId": "private-port-id", "name": "LAN 3", "type": 2}],
             "customConfig": {"iptvVlanId": 123}, "featureDescription": [
                 {"feature": "private-feature", "description": "private description"}]}},
        ])
        template_ref = "abc123" + "d" * 18
        with patch.object(self.client, "_opaque_ref", return_value=template_ref):
            inventory = self.client.list_site_templates()
        template_ref = inventory["items"][0]["site_template_ref"]
        result = self.client.read_site_template_iptv_summary(template_ref)
        self.assertEqual(result["resource"], "site_template_iptv_summary")
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["mode"], "bridge")
        self.assertEqual(result["data"]["port_type_counts"],
                         {"internet": 0, "iptv": 1, "ip_phone": 0})
        self.assertTrue(result["data"]["wan_port_configured"])
        self.assertEqual(self.connections[3].calls[0][1],
                         "/openapi/v1/controller_1/sitetemplates/private-template-id/setting/service/iptv/iptv")
        self.assertEqual(result["site_template_ref"], template_ref)
        self.assertEqual(result["data"], {
            "enabled": True, "mode": "bridge", "wan_port_configured": True,
            "custom_vlan_configured": True, "dsl_configured": None,
            "feature_description_count": 1,
            "port_type_counts": {"internet": 0, "iptv": 1, "ip_phone": 0},
            "port_count": 1,
        })
        for value in ("private-template-id", "private-wan-id", "private-port-id",
                      "LAN 3", "private-feature", "private description"):
            self.assertNotIn(value, repr(result))

    def test_site_template_iptv_service_uses_one_template_request(self) -> None:
        self.queue_responses([
            self.token_payload(),
            {"errorCode": 0, "result": {"totalRows": 1, "currentPage": 1,
             "currentSize": 1, "data": [{"id": "private-template-id"}]}},
            self.token_payload(),
            {"errorCode": 0, "result": {
                "igmpSetting": {"enable": True, "version": 2,
                                "wanPortId": "private-igmp-wan"},
                "iptvSetting": {"enable": True, "mode": 1,
                                "wanPortId": "private-iptv-wan",
                                "portConfig": [{"portId": "private-port", "type": 2}],
                                "customConfig": {"ipPhoneVlanId": 1300,
                                                 "ipPhoneVlanPriority": 2,
                                                 "iptvVlanId": 1301,
                                                 "iptvVlanPriority": 4}}}},
        ])
        inventory = self.client.list_site_templates()
        template_ref = inventory["items"][0]["site_template_ref"]
        result = self.client.read_site_template_iptv_settings_summary(template_ref)
        self.assertEqual(result["resource"], "site_template_iptv_settings_summary")
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["igmp"]["version"], 2)
        self.assertEqual(result["data"]["iptv"]["port_type_counts"]["iptv"], 1)
        self.assertEqual(len(self.connections[3].calls), 1)
        self.assertEqual(self.connections[3].calls[0][1],
                         "/openapi/v1/controller_1/sitetemplates/private-template-id/setting/service/iptv")
        for value in ("private-template-id", "private-igmp-wan", "private-iptv-wan",
                      "private-port", "1300", "1301"):
            self.assertNotIn(value, repr(result))

    def test_unknown_site_template_reference_is_rejected(self) -> None:
        with self.assertRaises(OpenApiError):
            self.client.read_site_template_igmp_summary("a" * 24)

    def test_site_igmp_summary_uses_inventory_bound_fixed_get(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        self.queue_responses([self.token_payload(), {"errorCode": 0, "result": {
            "enable": True, "version": 3, "wanPortId": "private-wan",
            "virtualWanId": "private-virtual-wan"}}])
        result = self.client.read_site_igmp_summary(site_ref)
        self.assertEqual(result["resource"], "site_igmp_summary")
        self.assertEqual(result["data"]["version"], 3)
        self.assertFalse(result["partial"])
        self.assertEqual(self.connections[1].calls[0][0], "GET")
        self.assertEqual(self.connections[1].calls[0][1],
                         "/openapi/v1/controller_1/sites/site-1/setting/service/igmp")
        self.assertNotIn("private-wan", repr(result))
        self.assertNotIn("private-virtual-wan", repr(result))

    def test_site_mld_summary_uses_inventory_bound_fixed_get(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        self.queue_responses([self.token_payload(), {"errorCode": 0, "result": {
            "enable": True, "version": 2, "wanPortId": "private-wan-id"}}])
        result = self.client.read_site_mld_summary(site_ref)
        self.assertEqual(result["resource"], "site_mld_summary")
        self.assertEqual(result["data"]["version"], 2)
        self.assertFalse(result["partial"])
        self.assertEqual(self.connections[1].calls[0][0], "GET")
        self.assertEqual(self.connections[1].calls[0][1],
                         "/openapi/v1/controller_1/sites/site-1/setting/service/mld")
        self.assertNotIn("private-wan-id", repr(result))

    def test_site_ssh_summary_uses_inventory_bound_fixed_get(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        self.queue_responses([self.token_payload(), {"errorCode": 0, "result": {
            "sshEnable": True, "sshServerPort": 2222, "layer3Access": False}}])
        result = self.client.read_site_ssh_summary(site_ref)
        self.assertEqual(result["resource"], "site_ssh_summary")
        self.assertEqual(result["data"]["server_port"], 2222)
        self.assertFalse(result["partial"])
        self.assertEqual(self.connections[1].calls[0][0], "GET")
        self.assertEqual(self.connections[1].calls[0][1],
                         "/openapi/v1/controller_1/sites/site-1/ssh")

    def test_site_ssl_vpn_summary_uses_inventory_bound_fixed_get(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        setting = {"status": True, "servicePort": 443, "authType": 0,
                   "exitAtIdle": False, "totalTraffic": True,
                   "supportRadius": True, "existRadius": False,
                   "supportLDAP": False, "existLdap": False,
                   "supportByDsLiteAndMapE": True, "exitTime": 300,
                   "radiusSetting": None, "LDAPSetting": None,
                   "nameLockSetting": {"status": True}, "ipLockSetting": {"status": False}}
        self.queue_responses([self.token_payload(), {"errorCode": 0, "result": setting}])
        result = self.client.read_site_ssl_vpn_summary(site_ref)
        self.assertEqual(result["resource"], "site_ssl_vpn_summary")
        self.assertEqual(result["data"]["authentication_mode"], "local")
        self.assertFalse(result["partial"])
        self.assertEqual(self.connections[1].calls[0][0], "GET")
        self.assertEqual(self.connections[1].calls[0][1],
                         "/openapi/v1/controller_1/sites/site-1/vpn/ssl-vpn-server/setting")

    def test_site_gre_tunnel_summary_uses_inventory_bound_fixed_get(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        setting = {"greEnable": True, "tunnelMtu": 1400, "interval": 30,
                   "maxCount": 5, "primaryAddress": "198.51.100.1",
                   "secondaryAddress": "2001:db8::1"}
        self.queue_responses([self.token_payload(), {"errorCode": 0, "result": setting}])
        result = self.client.read_site_gre_tunnel_summary(site_ref)
        self.assertEqual(result["resource"], "site_gre_tunnel_summary")
        self.assertEqual(result["data"]["tunnel_mtu"], 1400)
        self.assertFalse(result["partial"])
        self.assertEqual(self.connections[1].calls[0][0], "GET")
        self.assertEqual(self.connections[1].calls[0][1],
                         "/openapi/v1/controller_1/sites/site-1/vpn/gre-tunnel")
        self.assertNotIn("198.51.100.1", repr(result))
        self.assertNotIn("2001:db8::1", repr(result))

    def test_site_upnp_summary_uses_inventory_bound_fixed_get(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        setting = {"enable": True, "wanPortIds": ["wan-secret"],
                   "networkIds": ["network-secret"], "supportByDsLiteAndMapE": False}
        self.queue_responses([self.token_payload(), {"errorCode": 0, "result": setting}])
        result = self.client.read_site_upnp_summary(site_ref)
        self.assertEqual(result["resource"], "site_upnp_summary")
        self.assertEqual(result["data"]["wan_port_count"], 1)
        self.assertFalse(result["partial"])
        self.assertEqual(self.connections[1].calls[0][0], "GET")
        self.assertEqual(self.connections[1].calls[0][1],
                         "/openapi/v1/controller_1/sites/site-1/upnp")
        self.assertNotIn("wan-secret", repr(result))
        self.assertNotIn("network-secret", repr(result))

    def test_site_reference_permissions_and_unknown_reference(self) -> None:
        for candidate in ("", "../site", "A" * 24, 42):
            with self.subTest(candidate=candidate), self.assertRaises(OpenApiError) as ctx:
                self.client.list_devices(candidate)  # type: ignore[arg-type]
            self.assertEqual(ctx.exception.code, "site_ref_invalid")
        with self.assertRaises(OpenApiError) as ctx:
            self.client.list_devices("b" * 24)
        self.assertEqual(ctx.exception.code, "site_ref_unknown")
        self.assertEqual(self.connections, [])

    def test_references_are_stable_only_within_one_process_client(self) -> None:
        first = self.client._opaque_ref("device", "00:11:22:33:44:55")
        self.assertEqual(first, self.client._opaque_ref("device", "00:11:22:33:44:55"))
        other = OmadaOpenApiClient(self.config)
        self.assertNotEqual(first, other._opaque_ref("device", "00:11:22:33:44:55"))

    def test_response_errors_are_stable_and_redacted(self) -> None:
        cases = [
            (self.token_payload(), 401, "application/json", "openapi_authentication_failed"),
            (self.token_payload(), 403, "application/json", "openapi_permission_denied"),
            (self.token_payload(), 200, "text/plain", "openapi_content_type_invalid"),
            ({"errorCode": -1202, "msg": "sensitive detail"}, 200,
             "application/json", "openapi_permission_denied"),
            ({"errorCode": 123, "msg": "sensitive detail"}, 200,
             "application/json", "openapi_rejected"),
        ]
        for payload, status, content_type, code in cases:
            with self.subTest(code=code):
                self.respond(payload, status, content_type)
                connection = self.connections[-1]
                with patch.object(self.client, "_connection", return_value=connection):
                    with self.assertRaises(OpenApiError) as ctx:
                        self.client._request_json("POST", self.client.TOKEN_PATH)
                self.assertEqual(ctx.exception.code, code)
                self.assertNotIn("sensitive detail", str(ctx.exception))

        with patch.object(self.client, "_request_json", return_value={
            "errorCode": 0, "result": {"accessToken": "bad\ntoken"},
        }):
            with self.assertRaises(OpenApiError) as ctx:
                self.client._access_token()
        self.assertEqual(ctx.exception.code, "openapi_authentication_failed")

    def test_pagination_metadata_must_match_request(self) -> None:
        self.queue_responses([self.token_payload(), self.grid([], 2, 0)])
        with self.assertRaises(OpenApiError) as ctx:
            self.client.list_sites()
        self.assertEqual(ctx.exception.code, "openapi_response_invalid")

    def test_current_size_can_report_requested_page_size(self) -> None:
        final_page = self.grid([{"siteId": "site-1"}], 1, 1)
        final_page["result"]["currentSize"] = self.config.page_size  # type: ignore[index]
        self.queue_responses([self.token_payload(), final_page])
        self.assertEqual(self.client.list_sites()["count"], 1)

    def test_configuration_size_and_pagination_boundaries(self) -> None:
        for field, value in (("page_size", 0), ("page_size", 201),
                             ("max_pages", 0), ("max_pages", 21),
                             ("max_response_bytes", 1023),
                             ("max_response_bytes", 1_048_577)):
            with self.subTest(field=field, value=value), self.assertRaises(OpenApiError):
                OpenApiConfig("https://controller.example", "controller_1", "id", "secret",
                              cert_sha256="a" * 64, **{field: value})

    def test_oversized_body_and_unapproved_route_are_rejected(self) -> None:
        self.config = OpenApiConfig("https://controller.example", "controller_1", self.client_id,
                                    self.client_secret, cert_sha256="a" * 64,
                                    max_response_bytes=1024)
        self.client = OmadaOpenApiClient(self.config)
        connection = self.respond({"x": "a" * 1100})
        with patch.object(self.client, "_connection", return_value=connection):
            with self.assertRaises(OpenApiError) as ctx:
                self.client._request_json("POST", self.client.TOKEN_PATH)
        self.assertEqual(ctx.exception.code, "openapi_response_too_large")
        with self.assertRaises(OpenApiError) as ctx:
            self.client._request_json("GET", "/openapi/v1/controller_1/users")
        self.assertEqual(ctx.exception.code, "openapi_path_rejected")

    def test_site_wlan_optimizer_start_and_cancel_are_not_guarded_writes(self) -> None:
        paths = (
            "/openapi/v1/controller_1/sites/site_1/cmd/rfPlanning/optimization",
            "/openapi/v1/controller_1/sites/site_1/cmd/rfPlanning/rrmOptimization",
            "/openapi/v1/controller_1/sites/site_1/cmd/rfPlanning/cancel",
        )
        for path in paths:
            with self.subTest(path=path), self.assertRaises(OpenApiError) as ctx:
                self.client._request_json("POST", path, body=b"{}")
            self.assertEqual(ctx.exception.code, "openapi_path_rejected")

    def test_certificate_pin_is_checked_before_request(self) -> None:
        certificate = b"synthetic-certificate"
        expected_pin = hashlib.sha256(certificate).hexdigest()

        class Connection:
            closed = False

            def __init__(self, *_args: object, **_kwargs: object) -> None:
                self.sock = self

            def connect(self) -> None:
                pass

            def getpeercert(self, *, binary_form: bool) -> bytes:
                self_binary = binary_form
                assert self_binary
                return certificate

            def close(self) -> None:
                self.closed = True

        with patch("app.openapi.http.client.HTTPSConnection", Connection):
            good = OmadaOpenApiClient(OpenApiConfig(
                "https://controller.example", "controller_1", "id", "secret",
                cert_sha256=expected_pin,
            ))._connection()
            self.assertFalse(good.closed)
            self.assertIs(good._omada_tls_verified, True)
            good.close()
            with self.assertRaises(OpenApiError) as ctx:
                self.client._connection()
        self.assertEqual(ctx.exception.code, "controller_certificate_changed")

    def test_system_ca_mode_uses_default_context(self) -> None:
        context = object()
        seen: list[object] = []

        class Connection:
            def __init__(self, *_args: object, **kwargs: object) -> None:
                seen.append(kwargs["context"])
                self.sock = None

            def connect(self) -> None:
                pass

            def close(self) -> None:
                pass

        config = OpenApiConfig("https://controller.example", "controller_1", "id",
                               "secret", tls_trust="system_ca")
        with patch("app.openapi.ssl.create_default_context", return_value=context), \
             patch("app.openapi.http.client.HTTPSConnection", Connection):
            connection = OmadaOpenApiClient(config)._connection()
        self.assertEqual(seen, [context])
        self.assertIs(connection._omada_tls_verified, True)


    def test_site_stack_connections_summary_reads_fixed_stack_and_lldp_paths(self) -> None:
        site_ref = "a" * 24
        switch_ref = "b" * 24
        mac = "aa:bb:cc:dd:ee:ff"
        self.client._site_ids_by_ref[site_ref] = "site-1"
        self.client._switch_macs_by_site_ref[site_ref] = {switch_ref: mac}
        stack_rows = [{"id": "stack-1", "status": 0, "member": [{"mac": mac}]}]
        neighbor_rows = [{"portId": 3, "deviceId": "unexposed"}]
        with (patch.object(self.client, "list_devices", return_value={"items": []}) as inventory,
              patch.object(self.client, "_access_token", return_value="token"),
              patch.object(self.client, "_read_bounded_grid_rows",
                           side_effect=[(stack_rows, 0), (neighbor_rows, 0)]) as reads):
            result = self.client.read_site_stack_connections_summary(site_ref)
        self.assertEqual(inventory.call_args.args, (site_ref,))
        self.assertEqual(reads.call_args_list[0].args, (
            "/openapi/v1/controller_1/sites/site-1/stacks", "token", 32))
        self.assertEqual(reads.call_args_list[1].args, (
            "/openapi/v1/controller_1/sites/site-1/stack/stack-1/lldp-neighbors",
            "token", 64))
        self.assertEqual(result["resource"], "site_stack_connections_summary")
        self.assertEqual(result["data"]["stacks"][0]["member_switch_refs"], [switch_ref])
    def test_bounded_grid_reader_reports_rows_beyond_its_limit(self) -> None:
        with patch.object(self.client, "_request_json", side_effect=[
                {"result": {"data": [1, 2], "totalRows": 5,
                            "currentPage": 1, "currentSize": 2}},
                {"result": {"data": [3, 4], "totalRows": 5,
                            "currentPage": 2, "currentSize": 2}},
        ]) as request:
            rows, omitted = self.client._read_bounded_grid_rows(
                "/openapi/v1/controller/sites/site/stacks", "token", 4)
        self.assertEqual(rows, [1, 2, 3, 4])
        self.assertEqual(omitted, 1)
        self.assertEqual([call.args[1] for call in request.call_args_list], [
            "/openapi/v1/controller/sites/site/stacks?page=1&pageSize=2",
            "/openapi/v1/controller/sites/site/stacks?page=2&pageSize=2",
        ])
    def test_stack_list_and_neighbor_paths_are_fixed_and_bounded(self) -> None:
        allowed = (
            "/openapi/v1/controller_1/sites/site-1/stacks?page=1&pageSize=32",
            "/openapi/v1/controller_1/sites/site-1/stack/stack_1/lldp-neighbors?page=1&pageSize=64",
        )
        with patch.object(self.client, "_connection",
                          side_effect=OpenApiError("connection_reached")):
            for path in allowed:
                with self.subTest(path=path), self.assertRaisesRegex(
                        OpenApiError, "connection_reached"):
                    self.client._request_json("GET", path, token="token")
            rejected = (
                allowed[0].replace("pageSize=32", "pageSize=33"),
                allowed[1].replace("pageSize=64", "pageSize=65"),
                allowed[0].replace("controller_1", "other-controller"),
            )
            for path in rejected:
                with self.subTest(path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    self.client._request_json("GET", path, token="token")
    def test_controller_backup_inventory_summary_combines_fixed_list_with_existing_reads(self) -> None:
        payload = {"result": {"fileList": [
            {"fileName": "private-backup.cfg", "backupTime": 1_800_000_000_000,
             "size": 100},
        ]}}
        with (patch.object(self.client, "_access_token", return_value="token"),
              patch.object(self.client, "_request_json", return_value=payload) as request,
              patch.object(self.client, "read_controller_backup_schedule", return_value={
                  "partial": False, "data": {"enabled": True, "schedule_configured": True}}),
              patch.object(self.client, "read_controller_backup_result", return_value={
                  "partial": False, "data": {"status": "idle_or_finished"}})):
            result = self.client.read_controller_backup_inventory_summary()
        request.assert_called_once_with(
            "GET", "/openapi/v1/controller_1/maintenance/backup/files", token="token")
        self.assertEqual(result["resource"], "controller_backup_inventory_summary")
        self.assertEqual(result["backup_file_count"], 1)
        self.assertNotIn("private-backup.cfg", repr(result))
    def test_controller_backup_files_path_is_controller_bound(self) -> None:
        path = "/openapi/v1/controller_1/maintenance/backup/files"
        with patch.object(self.client, "_connection",
                          side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path, token="token")
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json(
                    "GET", path.replace("controller_1", "other-controller"), token="token")
    def test_site_backup_inventory_summary_uses_only_the_selected_site(self) -> None:
        site_ref = "a" * 24
        self.client._site_ids_by_ref[site_ref] = "site-1"
        payloads = [
            {"result": {"fileList": [
                {"fileName": "private-site-file", "backupTime": 1_800_000_000_000,
                 "size": 250}]}},
            {"result": {"status": 0}},
        ]
        with (patch.object(self.client, "list_sites", return_value={"items": []}) as sites,
              patch.object(self.client, "_access_token", return_value="token"),
              patch.object(self.client, "_request_json", side_effect=payloads) as request,
              patch.object(self.client, "read_controller_backup_schedule", return_value={
                  "partial": False, "data": {"schedule_configured": True}})):
            result = self.client.read_site_backup_inventory_summary(site_ref)
        sites.assert_called_once_with()
        self.assertEqual([call.args[1] for call in request.call_args_list], [
            "/openapi/v1/controller_1/sites/site-1/maintenance/backup/files",
            "/openapi/v1/controller_1/sites/site-1/backup/result",
        ])
        self.assertEqual(result["resource"], "site_backup_inventory_summary")
        self.assertEqual(result["source_scope"], "selected_site_file_list_response")
        self.assertNotIn("private-site-file", repr(result))
    def test_site_backup_list_paths_are_controller_bound(self) -> None:
        allowed = [
            "/openapi/v1/controller_1/sites/site-1/maintenance/backup/files",
            "/openapi/v1/controller_1/sites/site-1/backup/result",
        ]
        with patch.object(self.client, "_connection",
                          side_effect=OpenApiError("connection_reached")):
            for path in allowed:
                with self.subTest(path=path), self.assertRaisesRegex(
                        OpenApiError, "connection_reached"):
                    self.client._request_json("GET", path, token="token")
            for path in allowed:
                rejected = path.replace("controller_1", "other-controller")
                with self.subTest(path=rejected), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    self.client._request_json("GET", rejected, token="token")

if __name__ == "__main__":
    unittest.main()
