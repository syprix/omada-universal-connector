from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class SwitchHealthIntegrationTests(unittest.TestCase):
    """Exercise the authenticated HTTP route with the controller request stubbed."""

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.token = "caller-token-switch-health-0123456789abcdef"
        self.token_path = os.path.join(self.tempdir.name, "caller-token")
        with open(self.token_path, "w", encoding="utf-8") as stream:
            stream.write(self.token + "\n")
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.invalid", "controller_test", "unused-id",
            "unused-secret", cert_sha256="a" * 64,
        ))
        self.site_ref = "a" * 24
        self.switch_ref = "b" * 24
        self.other_site_ref = "c" * 24
        self.site_id = "site-bound-id"
        self.switch_mac = "00:11:22:33:44:55"
        self.client._site_ids_by_ref = {
            self.site_ref: self.site_id,
            self.other_site_ref: "another-site-id",
        }
        self.client._switch_macs_by_site_ref = {
            self.site_ref: {self.switch_ref: self.switch_mac},
            self.other_site_ref: {},
        }
        self.request_calls: list[tuple[str, str, str | None]] = []
        self.payload = {
            "score": 82,
            "cpu": {"summaryScore": 90, "support": True, "averageNum": 17,
                    "pastNums": [{"time": 1_000, "pastNum": 20}]},
            "memory": {"summaryScore": 80, "support": True, "averageNum": 60,
                       "pastNums": []},
            "temperature": {"summaryScore": 78, "support": True, "averageNum": 42,
                             "pastNums": []},
            "packetLoss": {"summaryScore": 89, "support": True, "averageNum": 0,
                           "pastNums": [], "averageFloat": 0.0, "pastFloats": []},
            "errorFrame": {"summaryScore": 86, "support": True, "averageNum": 0,
                           "pastNums": [], "averageFloat": 0.0, "pastFloats": []},
            "incident": {"summaryScore": 90, "support": True, "incidentNum": 1,
                         "incidents": [{"incidentId": "private-incident-id",
                                        "object": [self.switch_mac],
                                        "titleParams": {"name": "private-switch-name"}}]},
            "linkError": {"summaryScore": 90, "support": True, "averageNum": 0,
                          "portNum": 48, "pastNums": []},
            "switchName": "private-switch-name",
            "mac": self.switch_mac,
            "ip": "192.0.2.55",
        }

        def request_json(method: str, path: str, *, token: str | None = None, **_kwargs):
            self.request_calls.append((method, path, token))
            return {"errorCode": 0, "result": self.payload}

        self.access_token_patch = patch.object(self.client, "_access_token", return_value="stub-access-token")
        self.request_patch = patch.object(self.client, "_request_json", side_effect=request_json)
        self.access_token_patch.start()
        self.request_patch.start()

        self.logs = io.StringIO()
        self.stdout_patch = patch("builtins.print", side_effect=lambda *args, **kwargs:
                                  self.logs.write(" ".join(map(str, args)) + "\n"))
        self.stdout_patch.start()
        self.env_patch = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": self.token_path})
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.client_patch.stop()
        self.env_patch.stop()
        self.stdout_patch.stop()
        self.request_patch.stop()
        self.access_token_patch.stop()
        self.tempdir.cleanup()

    def get(self, path: str, *, token: str | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer " + token} if token else {}
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        status, payload = response.status, json.loads(response.read())
        connection.close()
        return status, payload

    def test_authenticated_route_projects_data_and_uses_fixed_site_bound_request(self) -> None:
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/health"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_health")
        self.assertEqual(body["query_time_unit"], "milliseconds_documented_not_live_verified")
        self.assertEqual(body["site_ref"], self.site_ref)
        self.assertEqual(body["switch_ref"], self.switch_ref)
        self.assertEqual(body["data"]["score"], 82)
        self.assertEqual(body["data"]["cpu"]["average"], 17)
        self.assertEqual(body["data"]["incident"]["incident_count"], 1)
        self.assertEqual(body["data"]["incident"]["omitted_incident_count"], 1)

        self.assertEqual(len(self.request_calls), 1)
        method, raw_path, token = self.request_calls[0]
        parsed = urlsplit(raw_path)
        self.assertEqual(method, "GET")
        self.assertEqual(parsed.path, (
            "/openapi/v1/controller_test/sites/site-bound-id/switches/"
            "00:11:22:33:44:55/health/detail"
        ))
        self.assertEqual(token, "stub-access-token")
        query = parse_qs(parsed.query)
        self.assertEqual(set(query), {"start", "end"})
        start_ms, end_ms = int(query["start"][0]), int(query["end"][0])
        self.assertEqual(end_ms - start_ms, 86_400_000)
        self.assertEqual(body["window_start_ms"], start_ms)
        self.assertEqual(body["window_end_ms"], end_ms)
        self.assertEqual(body["data"]["cpu"]["values"], [])  # sample is outside the fixed current window

        serialized = json.dumps(body)
        for private in (self.switch_mac, "private-switch-name", "192.0.2.55", "private-incident-id"):
            self.assertNotIn(private, serialized)

    def test_timeline_uses_fixed_24_hour_query_and_projects_only_scores(self) -> None:
        self.payload = {"scores": [{"time": 1, "score": 90}],
                        "switchMac": self.switch_mac}
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/health/timeline"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_health_timeline")
        self.assertEqual(body["data"], {"scores": []})  # fixture time is outside the window
        self.assertTrue(body["partial"])
        method, raw_path, token = self.request_calls[0]
        parsed = urlsplit(raw_path)
        self.assertEqual(method, "GET")
        self.assertEqual(parsed.path, (
            "/openapi/v1/controller_test/sites/site-bound-id/switches/"
            "00:11:22:33:44:55/health/timeline"))
        query = parse_qs(parsed.query)
        self.assertEqual(set(query), {"start", "end"})
        start_ms, end_ms = int(query["start"][0]), int(query["end"][0])
        self.assertEqual(end_ms - start_ms, 86_400_000)
        self.assertEqual(body["window_start_ms"], start_ms)
        self.assertEqual(body["window_end_ms"], end_ms)
        self.assertNotIn(self.switch_mac, json.dumps(body))

    def test_sdm_usage_uses_exact_inventory_bound_read_path(self) -> None:
        self.payload = {"category": 3, "num": 120, "unused": "private"}
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/sdm-usage"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_sdm_usage")
        self.assertEqual(body["data"], {"category": 3, "num": 120})
        self.assertTrue(body["partial"])
        method, raw_path, token = self.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(raw_path,
            "/openapi/v1/controller_test/sites/site-bound-id/switches/"
            "00:11:22:33:44:55/sdm-used")
        self.assertEqual(token, "stub-access-token")
        self.assertNotIn(self.switch_mac, json.dumps(body))

    def test_cable_test_logs_read_stored_results_without_starting_a_test(self) -> None:
        self.payload = [{"type": 0, "timeStamp": 1700000000000,
                         "testPortList": [{"port": 5, "standardPort": {"unit": 1}}],
                         "completePortList": [{"port": 5}],
                         "cancelPortList": [], "timeoutPortList": []}]
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/cable-test/logs"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_cable_test_logs")
        self.assertEqual(body["data"]["logs"][0]["test_ports"], [5])
        self.assertTrue(body["partial"])
        method, raw_path, token = self.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(raw_path,
            "/openapi/v1/controller_test/sites/site-bound-id/cable-test/switches/"
            "00:11:22:33:44:55/logs")
        self.assertEqual(token, "stub-access-token")
        self.assertNotIn("unit", json.dumps(body))

    def test_full_cable_test_results_read_uses_fixed_inventory_bound_route(self) -> None:
        self.payload = {"status": 0,
                        "data": [{"port": 7, "state": [0, 1], "length": [10, 20],
                                  "timeStamp": 1700000000000,
                                  "standardPort": {"unit": 2, "slot": 1, "port": 7}}],
                        "stackData": [{"mac": "private-stack-mac", "unit": 2, "data": []}]}
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/cable-test/full-results"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_cable_test_full_results")
        self.assertEqual(body["data"]["ports"][0]["state_codes"], [0, 1])
        self.assertTrue(body["partial"])
        method, raw_path, token = self.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(raw_path,
            "/openapi/v1/controller_test/sites/site-bound-id/cable-test/switches/"
            "00:11:22:33:44:55/full-results")
        self.assertEqual(token, "stub-access-token")
        for secret in ("private-stack-mac", "unit", "slot"):
            self.assertNotIn(secret, json.dumps(body))

    def test_incremental_cable_test_results_use_their_own_stored_read_route(self) -> None:
        self.payload = {"status": 0,
                        "data": [{"port": 8, "state": [2], "length": [25],
                                  "timeStamp": 1700000000001}]}
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/cable-test/increment-results"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_cable_test_increment_results")
        self.assertEqual(body["data"]["ports"][0]["state_codes"], [2])
        method, raw_path, token = self.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(raw_path,
            "/openapi/v1/controller_test/sites/site-bound-id/cable-test/switches/"
            "00:11:22:33:44:55/increment-results")
        self.assertEqual(token, "stub-access-token")

    def test_cable_test_port_list_is_redacted_and_does_not_start_a_test(self) -> None:
        self.payload = [{"port": 8, "standardPort": {"unit": 2, "slot": 1, "port": 8},
                         "type": 1, "name": "private-port", "editEnable": True,
                         "isUpperPort": False, "isDisabled": False, "isStackPort": False,
                         "reasons": [], "downlinkDevices": [{"mac": "private-device"}],
                         "isCopper": True}]
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/cable-test/ports"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_cable_test_ports")
        self.assertEqual(body["data"]["ports"][0]["port"], 8)
        method, raw_path, token = self.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertTrue(raw_path.endswith("/cable-test/switches/00:11:22:33:44:55/ports"))
        self.assertEqual(token, "stub-access-token")
        for secret in ("private-port", "private-device", "standardPort", "unit", "slot"):
            self.assertNotIn(secret, json.dumps(body))

    def test_switch_dhcp_users_are_paged_and_return_only_opaque_summary(self) -> None:
        self.payload = {"totalRows": 2, "currentPage": 1, "currentSize": 2,
                        "data": [
                            {"type": 0, "status": 0, "macAddress": "00:11:22:33:44:55",
                             "ipAddress": "192.0.2.12", "name": "private-device",
                             "netId": "private-network"},
                            {"type": 1, "status": 1, "macAddress": "00:11:22:33:44:66",
                             "ipAddress": "192.0.2.13", "name": "private-client",
                             "netId": "private-network"},
                        ]}
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/dhcp/users"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_dhcp_users")
        self.assertEqual(body["summary"], {"total": 2, "devices": 1, "clients": 1,
                                            "dynamic": 1, "static": 1})
        method, raw_path, token = self.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(raw_path,
            "/openapi/v1/controller_test/sites/site-bound-id/switches/"
            "00:11:22:33:44:55/dhcp/user-list?page=1&pageSize=100")
        self.assertEqual(token, "stub-access-token")
        for secret in ("00:11:22:33:44:55", "192.0.2.12", "private-device", "private-network"):
            self.assertNotIn(secret, json.dumps(body))

    def test_switch_ospf_neighbors_are_paged_and_aggregate_state_only(self) -> None:
        self.payload = {"totalRows": 2, "currentPage": 1, "currentSize": 2,
                        "data": [{"state": "Full", "neighborIp": "192.0.2.20",
                                  "routerId": "private-router", "neighborInterface": "private-vlan"},
                                 {"state": "Full", "neighborIp": "192.0.2.21",
                                  "routerId": "private-router-2", "processId": "private-process"}]}
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/ospf-neighbors"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_ospf_neighbors")
        self.assertEqual(body["summary"]["by_state"], {"Full": 2})
        method, raw_path, token = self.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(raw_path,
            "/openapi/v1/controller_test/sites/site-bound-id/switches/"
            "00:11:22:33:44:55/ospf-neighbors?page=1&pageSize=100")
        self.assertEqual(token, "stub-access-token")
        for secret in ("192.0.2.20", "private-router", "private-vlan", "private-process"):
            self.assertNotIn(secret, json.dumps(body))

    def test_switch_port_networks_are_paged_and_aggregate_vlan_use(self) -> None:
        self.payload = {"totalRows": 2, "currentPage": 1, "currentSize": 2,
                        "data": [{"id": "private-net-a", "name": "Office", "vlan": 20},
                                 {"id": "private-net-b", "name": "Guest", "vlan": 20}]}
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/port-networks"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_port_networks")
        self.assertEqual(body["summary"]["vlans"], [{"vlan_id": 20, "network_count": 2}])
        method, raw_path, token = self.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(raw_path,
            "/openapi/v1/controller_test/sites/site-bound-id/switches/"
            "00:11:22:33:44:55/port-lag-networks?page=1&pageSize=100")
        self.assertEqual(token, "stub-access-token")
        for secret in ("private-net-a", "private-net-b", "Office", "Guest"):
            self.assertNotIn(secret, json.dumps(body))

    def test_switch_exist_networks_return_vlan_counts_without_configuration_details(self) -> None:
        self.payload = {"data": [{"id": "private-network", "name": "Office", "vlan": 20,
                                  "vlanType": 0, "primary": True,
                                  "ip": {"ip": "192.0.2.1"},
                                  "dhcpServer": {"ip": "192.0.2.2"}}],
                        "supportMultiVlan": True, "supportRA": False,
                        "supportCustomDhcpOption": True}
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/exist-networks"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_exist_networks")
        self.assertEqual(body["summary"]["by_vlan"], {"20": 1})
        self.assertEqual(body["summary"]["by_vlan_type"], {"0": 1})
        method, raw_path, token = self.request_calls[0]
        self.assertEqual((method, token), ("GET", "stub-access-token"))
        self.assertEqual(raw_path,
            "/openapi/v1/controller_test/sites/site-bound-id/switches/"
            "00:11:22:33:44:55/exist-network")
        for secret in ("private-network", "Office", "192.0.2.1", "192.0.2.2"):
            self.assertNotIn(secret, json.dumps(body))

    def test_switch_networks_are_paged_and_return_only_vlan_status_and_mode_counts(self) -> None:
        self.payload = {"totalRows": 2, "currentPage": 1, "currentSize": 2,
                        "data": [{"id": "private-net-a", "name": "Office", "vlan": 20,
                                  "status": 1, "mode": 1, "ip": {"ip": "192.0.2.1"}},
                                 {"id": "private-net-b", "name": "Guest", "vlan": 20,
                                  "status": 0, "mode": 2, "dhcpServer": {"ip": "192.0.2.2"}}]}
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/networks"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_networks")
        self.assertEqual(body["summary"]["by_vlan"], {"20": 2})
        self.assertEqual(body["summary"]["by_status_code"], {"0": 1, "1": 1})
        self.assertEqual(body["summary"]["by_dhcp_mode_code"], {"1": 1, "2": 1})
        method, raw_path, token = self.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(raw_path,
            "/openapi/v1/controller_test/sites/site-bound-id/switches/"
            "00:11:22:33:44:55/networks?page=1&pageSize=100")
        self.assertEqual(token, "stub-access-token")
        for secret in ("private-net-a", "private-net-b", "Office", "Guest", "192.0.2.1", "192.0.2.2"):
            self.assertNotIn(secret, json.dumps(body))

    def test_switch_interfaces_return_type_counts_without_interface_identifiers(self) -> None:
        self.payload = [{"type": 0, "id": "private-loopback", "interfaceId": 9, "name": "Loopback9"},
                        {"type": 1, "id": "private-vlan", "interfaceId": 20, "name": "VLAN20"}]
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/interfaces"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_interfaces")
        self.assertEqual(body["summary"]["by_type_code"], {"0": 1, "1": 1})
        method, raw_path, token = self.request_calls[0]
        self.assertEqual((method, token), ("GET", "stub-access-token"))
        self.assertEqual(raw_path,
            "/openapi/v1/controller_test/sites/site-bound-id/switches/"
            "00:11:22:33:44:55/interfaces/brief")
        for secret in ("private-loopback", "private-vlan", "Loopback9", "VLAN20"):
            self.assertNotIn(secret, json.dumps(body))

    def test_switch_routing_table_is_paged_and_omits_addresses(self) -> None:
        self.payload = {"totalRows": 1, "currentPage": 1, "currentSize": 1,
                        "data": [{"type": "static", "distance": 1, "metric": 10,
                                  "destinationIp": "192.0.2.0/24", "nextHop": "192.0.2.1",
                                  "interfaceName": ["private-lan"]}]}
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/routing-table"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_routing_table")
        self.assertEqual(body["summary"]["by_type"], {"static": 1})
        self.assertEqual(body["summary"]["by_distance"], {"1": 1})
        self.assertEqual(body["summary"]["by_metric"], {"10": 1})
        method, raw_path, token = self.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(raw_path,
            "/openapi/v1/controller_test/sites/site-bound-id/switches/"
            "00:11:22:33:44:55/routingTable?page=1&pageSize=100")
        self.assertEqual(token, "stub-access-token")
        for secret in ("192.0.2.0/24", "192.0.2.1", "private-lan"):
            self.assertNotIn(secret, json.dumps(body))

    def test_switch_static_routes_are_paged_and_redact_all_address_fields(self) -> None:
        self.payload = {"totalRows": 1, "currentPage": 1, "currentSize": 1,
                        "data": [{"status": True, "distance": 1,
                                  "destinations": ["192.0.2.0/24"], "ipVersion": 0,
                                  "resource": 1, "nextHopIp": "192.0.2.1",
                                  "vrfId": "private-vrf", "description": "private-description"}],
                        "supportIpv6StaticRouting": True}
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/static-routes"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_static_routes")
        self.assertEqual(body["summary"]["by_status"], {"true": 1})
        self.assertEqual(body["summary"]["by_ip_version"], {"0": 1})
        self.assertEqual(body["summary"]["by_destination_count"], {"1": 1})
        self.assertTrue(body["summary"]["support_ipv6_static_routing"])
        method, raw_path, token = self.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(raw_path,
            "/openapi/v1/controller_test/sites/site-bound-id/switches/"
            "00:11:22:33:44:55/staticRoutings?page=1&pageSize=100")
        self.assertEqual(token, "stub-access-token")
        for secret in ("192.0.2.0/24", "192.0.2.1", "private-vrf", "private-description"):
            self.assertNotIn(secret, json.dumps(body))

    def test_switch_vrfs_support_unpaged_documentation_and_redact_names_and_identifiers(self) -> None:
        self.payload = {"totalRows": 1, "currentPage": 0, "currentSize": 1,
                        "data": [{"id": "private-vrf-id", "vrf": "private-vrf-name",
                                  "ipv4Enable": True, "ipv6Enable": False,
                                  "isDefault": True, "resource": 0}]}
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/vrfs"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_vrfs")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["summary"]["by_ipv4_enabled"], {"true": 1})
        self.assertEqual(body["summary"]["by_ipv6_enabled"], {"false": 1})
        self.assertEqual(body["summary"]["default_count"], 1)
        method, raw_path, token = self.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(raw_path,
            "/openapi/v1/controller_test/sites/site-bound-id/switches/"
            "00:11:22:33:44:55/vrfs")
        self.assertEqual(token, "stub-access-token")
        self.assertNotIn("private-vrf-id", json.dumps(body))
        self.assertNotIn("private-vrf-name", json.dumps(body))

    def test_switch_vrfs_fall_back_to_required_pagination_after_rejection(self) -> None:
        row = {"id": "private-vrf-id", "vrf": "private-vrf-name",
               "ipv4Enable": True, "ipv6Enable": False, "isDefault": False,
               "resource": 1}
        self.request_patch.stop()
        self.request_calls.clear()

        def request_json(method: str, path: str, *, token: str | None = None, **_kwargs):
            self.request_calls.append((method, path, token))
            if "?page=" not in path:
                raise OpenApiError("openapi_http_error")
            return {"errorCode": 0, "result": {"totalRows": 1, "currentPage": 1,
                                                    "currentSize": 1, "data": [row]}}

        self.request_patch = patch.object(self.client, "_request_json", side_effect=request_json)
        self.request_patch.start()
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/vrfs"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)
        self.assertEqual([path for _method, path, _token in self.request_calls], [
            "/openapi/v1/controller_test/sites/site-bound-id/switches/"
            "00:11:22:33:44:55/vrfs",
            "/openapi/v1/controller_test/sites/site-bound-id/switches/"
            "00:11:22:33:44:55/vrfs?page=1&pageSize=100",
        ])
        self.assertNotIn("private-vrf-id", json.dumps(body))
        self.assertNotIn("private-vrf-name", json.dumps(body))

    def test_switch_vlan_interfaces_return_only_counts(self) -> None:
        self.payload = [{"vlanInterfaceId": "private-vlan-interface-id",
                         "vlanInterfaceName": "private-vlan-interface-name", "vlanId": 20}]
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/vlan-interfaces"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_vlan_interfaces")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["summary"], {"unique_vlan_count": 1, "unknown_rows": 0})
        self.assertEqual(self.request_calls[0][1],
            "/openapi/v1/controller_test/sites/site-bound-id/vlan-interface/switches/"
            "00:11:22:33:44:55")
        for secret in ("private-vlan-interface-id", "private-vlan-interface-name", "vlanId"):
            self.assertNotIn(secret, json.dumps(body))

    def test_switch_statistics_return_redacted_port_counters(self) -> None:
        self.payload = {
            "name": "private-switch-name", "status": 14, "statusCategory": 1,
            "portNum": 1,
            "ports": [{"port": 1, "name": "private-port-name", "type": 1,
                       "portStatus": {"linkStatus": 1, "poe": True,
                                      "stpDiscarding": False, "tx": 100,
                                      "rx": 50, "total": 150}}],
            "uplink": {"port": 1, "mac": "00:11:22:33:44:66", "name": "private-uplink"},
            "supportPoe": True, "supportStack": False, "supportSTP": True,
            "speeds": [0, 3], "mlagMsg": {"role": 0, "dadLinkPort": [], "peerLinkPort": []},
        }
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/statistics"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["resource"], "switch_statistics")
        self.assertEqual(body["data"]["by_link_status_code"], {"1": 1})
        self.assertEqual(body["data"]["tx_bytes"], 100)
        self.assertEqual(body["data"]["rx_bytes"], 50)
        self.assertEqual(self.request_calls[0][1],
            "/openapi/v1/controller_test/sites/site-bound-id/stat/switches/00:11:22:33:44:55")
        for secret in ("private-switch-name", "private-port-name", "00:11:22:33:44:66", "private-uplink"):
            self.assertNotIn(secret, json.dumps(body))

    def test_route_requires_auth_and_rejects_unbound_or_cross_site_switch_refs(self) -> None:
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/health"
        status, body = self.get(route)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")
        self.assertEqual(self.request_calls, [])

        other_site_route = f"/v1/sites/{self.other_site_ref}/switches/{self.switch_ref}/health"
        status, body = self.get(other_site_route, token=self.token)
        self.assertEqual(status, 502)
        self.assertEqual(body["error"], "switch_ref_unknown")
        self.assertEqual(self.request_calls, [])

        malformed = f"/v1/sites/{self.site_ref}/switches/NOT-A-REF/health"
        status, body = self.get(malformed, token=self.token)
        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "not_found")
        self.assertEqual(self.request_calls, [])

    def test_upstream_response_shape_failure_is_redacted_and_does_not_leak_payload(self) -> None:
        self.payload = {"score": True, "switchName": "private-switch-name"}
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/health"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 502)
        self.assertEqual(body["error"], "openapi_response_invalid")
        self.assertNotIn("private-switch-name", json.dumps(body))
        self.assertEqual(len(self.request_calls), 1)

    def test_query_parameters_cannot_override_fixed_health_window(self) -> None:
        route = f"/v1/sites/{self.site_ref}/switches/{self.switch_ref}/health?start=0&end=1"
        status, body = self.get(route, token=self.token)
        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "not_found")
        self.assertEqual(self.request_calls, [])


if __name__ == "__main__":
    unittest.main()
