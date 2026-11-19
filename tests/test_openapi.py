from __future__ import annotations

import json
import hashlib
import os
import tempfile
import unittest
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
        for value in ("private-template-id", "private-wan-id", "private-port-id",
                      "LAN 3", "123", "private-feature", "private description"):
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
