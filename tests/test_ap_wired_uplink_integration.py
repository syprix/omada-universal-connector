from __future__ import annotations

import builtins
import io
import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


TOKEN = "ap-wired-uplink-integration-token-0123456789abcdef"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
DEVICE_REF = "c" * 24
OTHER_DEVICE_REF = "d" * 24
PRIVATE_SITE_ID = "private-site-id"
AP_MAC = "AA-BB-CC-DD-EE-FF"
OTHER_AP_MAC = "11:22:33:44:55:66"
PRIVATE_MARKERS = (
    "private-uplink-mac", "private-stack-id", "private-uplink-type",
    "private-uplink-name", "private-port-id", "192.0.2.222",
    "private-ap-model", "private-model-version", "private-uplink-port",
)


def full_uplink(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "uplinkMac": PRIVATE_MARKERS[0],
        "stackId": PRIVATE_MARKERS[1],
        "type": PRIVATE_MARKERS[2],
        "name": PRIVATE_MARKERS[3],
        "rate": "1000",
        "duplex": 2,
        "upBytes": 1000,
        "downBytes": 2000,
        "upPackets": 30,
        "downPackets": 40,
        "upDropPackets": 1,
        "downDropPackets": 2,
        "upErrorsPackets": 3,
        "downErrorsPackets": 4,
        "activity": 500,
        "port": PRIVATE_MARKERS[4],
        "ip": PRIVATE_MARKERS[5],
        "portType": 0,
        "txPower": 1.25,
        "rxPower": 2.5,
        "temp": 31.0,
        "voltage": 3.3,
        "current": 0.2,
        "model": PRIVATE_MARKERS[6],
        "modelVersion": PRIVATE_MARKERS[7],
        "uplinkPort": PRIVATE_MARKERS[8],
        "linkStatus": 1,
        "linkSpeed": 1000,
    }
    values.update(overrides)
    return values


class ApWiredUplinkIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(TOKEN)
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = PRIVATE_SITE_ID
        self.client._device_macs_by_site_ref[SITE_REF] = {DEVICE_REF: AP_MAC}
        self.client._device_macs_by_site_ref[OTHER_SITE_REF] = {OTHER_DEVICE_REF: OTHER_AP_MAC}
        self.result: object = {"wiredUplink": full_uplink()}
        self.fail_upstream = False
        self.transport_calls: list[tuple[str, str, bytes | None]] = []

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.transport_calls.append((method, path, body))
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(token, "synthetic-upstream-token")
            self.assertEqual(path, self._upstream_path())
            if self.fail_upstream:
                raise OpenApiError("openapi_rejected", -1001)
            return {"result": json.loads(json.dumps(self.result))}

        self.transport_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.transport_patch.start()
        self.access_patch = patch.object(
            self.client, "_access_token", return_value="synthetic-upstream-token")
        self.access_patch.start()
        self.env_patch = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": self.token_file})
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.logs = io.StringIO()
        self.print_patch = patch.object(
            builtins, "print", lambda *args, **_kwargs: self.logs.write(
                " ".join(map(str, args)) + "\n"))
        self.print_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.print_patch.stop()
        self.client_patch.stop()
        self.env_patch.stop()
        self.access_patch.stop()
        self.transport_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def _upstream_path(controller_id: str = "ctrl") -> str:
        return f"/openapi/v1/{controller_id}/sites/{PRIVATE_SITE_ID}/aps/{AP_MAC}/wired-uplink"

    @staticmethod
    def _public_path(site_ref: str = SITE_REF, device_ref: str = DEVICE_REF) -> str:
        return f"/v1/sites/{site_ref}/aps/{device_ref}/wired-uplink"

    def request(self, method: str, path: str, *, token: str | None = None,
                body: dict[str, object] | None = None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer " + token} if token is not None else {}
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = {}
        status = response.status
        connection.close()
        return status, value

    def test_mcp_dispatch_uses_same_fixed_wired_uplink_projection(self) -> None:
        status, response = self.request(
            "POST", "/mcp", token=TOKEN,
            body={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": "omada_ap_wired_uplink",
                             "arguments": {"site_ref": SITE_REF,
                                           "device_ref": DEVICE_REF}}})
        self.assertEqual(status, 200)
        self.assertFalse(response["result"]["isError"])
        result = response["result"]["structuredContent"]
        self.assertEqual(result["resource"], "ap_wired_uplink")
        self.assertEqual(result["data"]["wiredUplink"]["linkSpeed"], 1000)
        self.assertEqual(self.transport_calls, [("GET", self._upstream_path(), None)])

    def test_auth_binding_stats_and_complete_identity_redaction(self) -> None:
        route = "GET /v1/sites/{site_ref}/aps/{device_ref}/wired-uplink"
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == route)
        self.assertEqual(operation["support_state"], "unknown")
        self.assertEqual(operation["runtime_evidence"], [])

        status, denied = self.request("GET", self._public_path())
        self.assertEqual(status, 401)
        self.assertEqual(denied["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])

        status, value = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertEqual(value["resource"], "ap_wired_uplink")
        self.assertEqual(value["data"]["wiredUplink"]["duplex"], 2)
        self.assertEqual(value["data"]["wiredUplink"]["rate_mbps"], 1000)
        self.assertEqual(value["data"]["wiredUplink"]["upBytes"], 1000)
        self.assertEqual(value["data"]["wiredUplink"]["downErrorsPackets"], 4)
        self.assertEqual(value["data"]["wiredUplink"]["linkSpeed"], 1000)
        self.assertEqual(value["redacted_field_count"], 9)
        self.assertFalse(value["partial"])
        self.assertEqual(self.transport_calls, [("GET", self._upstream_path(), None)])
        rendered = json.dumps(value)
        for marker in PRIVATE_MARKERS:
            self.assertNotIn(marker, rendered)
            self.assertNotIn(marker, self.logs.getvalue())

        before = len(self.transport_calls)
        for site_ref, device_ref in (("e" * 24, DEVICE_REF),
                                     (OTHER_SITE_REF, DEVICE_REF),
                                     (SITE_REF, OTHER_DEVICE_REF)):
            status, error = self.request("GET", self._public_path(site_ref, device_ref), token=TOKEN)
            self.assertNotEqual(status, 200)
            self.assertEqual(len(self.transport_calls), before)
            self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))
            self.assertNotIn(AP_MAC, json.dumps(error))

    def test_er_optional_poe_voip_absence_does_not_make_partial(self) -> None:
        self.result = {"wiredUplink": full_uplink()}
        status, value = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertFalse(value["partial"])
        self.assertNotIn("poeState", value["data"]["wiredUplink"])
        self.assertNotIn("voipState", value["data"]["wiredUplink"])

        self.result["wiredUplink"].update({"poeState": 0, "voipState": 1})
        status, value = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertFalse(value["partial"])
        self.assertEqual(value["data"]["wiredUplink"]["poeState"], 0)
        self.assertEqual(value["data"]["wiredUplink"]["voipState"], 1)

    def test_missing_invalid_and_unknown_data_mark_partial_without_leaking(self) -> None:
        fixtures = (
            {"wiredUplink": {k: v for k, v in full_uplink().items() if k != "duplex"}},
            {"wiredUplink": full_uplink(duplex=3)},
            {"wiredUplink": full_uplink(portType=4)},
            {"wiredUplink": full_uplink(rate="10000Mbps")},
            {"wiredUplink": full_uplink(linkSpeed=True)},
            {"wiredUplink": full_uplink(privateUnknown="private-unknown-value")},
        )
        route = "GET /v1/sites/{site_ref}/aps/{device_ref}/wired-uplink"
        for raw in fixtures:
            with self.subTest(raw=raw):
                self.result = raw
                status, value = self.request("GET", self._public_path(), token=TOKEN)
                self.assertEqual(status, 200, value)
                self.assertTrue(value["partial"])
                rendered = json.dumps(value)
                for private in (*PRIVATE_MARKERS, "privateUnknown", "private-unknown-value"):
                    self.assertNotIn(private, rendered)
                    self.assertNotIn(private, self.logs.getvalue())
                operation = next(item for item in self.client.capabilities()["items"]
                                 if item["route"] == route)
                evidence = operation["runtime_evidence"][-1]
                self.assertEqual(evidence["support_state"], "unknown")
                self.assertEqual(evidence["observation"], "response_partial")

    def test_invalid_root_and_upstream_failure_are_redacted(self) -> None:
        self.result = None
        status, error = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_response_invalid")
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))

        self.fail_upstream = True
        status, error = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_rejected")
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))

    def test_only_fixed_controller_get_route_and_no_query_or_other_methods(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        valid = self._upstream_path()
        with patch.object(client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", valid, token="token")
            rejected = (
                ("POST", valid), ("PUT", valid), ("PATCH", valid), ("DELETE", valid),
                ("GET", valid + "?raw=true"),
                ("GET", self._upstream_path("foreign-controller")),
                ("GET", valid.replace("/wired-uplink", "/other")),
            )
            for method, path in rejected:
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, token="token")

        for method in ("POST", "PUT", "PATCH", "DELETE"):
            status, _ = self.request(method, self._public_path(), token=TOKEN)
            self.assertNotEqual(status, 200)
        status, _ = self.request("GET", self._public_path() + "?debug=1", token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(self.transport_calls, [])


if __name__ == "__main__":
    unittest.main()
