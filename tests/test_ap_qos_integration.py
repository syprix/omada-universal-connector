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
from app.ap_qos_changes import ApQosPlans


TOKEN = "ap-qos-integration-token-0123456789abcdef"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
DEVICE_REF = "c" * 24
OTHER_DEVICE_REF = "d" * 24
PRIVATE_SITE_ID = "private-site-id"
AP_MAC = "AA-BB-CC-DD-EE-FF"
PRIVATE_NAME = "private-access-point"
PRIVATE_IP = "192.0.2.44"

FIELDS = (
    "support2g", "support5g", "support5g2", "support6g",
    "deliveryEnable2g", "deliveryEnable5g", "deliveryEnable5g2", "deliveryEnable6g",
)


def full_qos(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {field: True for field in FIELDS}
    values.update(overrides)
    return values


class ApQosIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(TOKEN)
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = PRIVATE_SITE_ID
        self.client._site_ids_by_ref[OTHER_SITE_REF] = "other-private-site-id"
        self.client._device_macs_by_site_ref[SITE_REF] = {DEVICE_REF: AP_MAC}
        self.client._device_macs_by_site_ref[OTHER_SITE_REF] = {
            OTHER_DEVICE_REF: "11:22:33:44:55:66"}
        self.result: object = full_qos()
        self.transport_calls: list[tuple[str, str, bytes | None]] = []
        self.fail_upstream = False

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
        return f"/openapi/v1/{controller_id}/sites/{PRIVATE_SITE_ID}/aps/{AP_MAC}/qos"

    @staticmethod
    def _public_path(site_ref: str = SITE_REF, device_ref: str = DEVICE_REF) -> str:
        return f"/v1/sites/{site_ref}/aps/{device_ref}/qos"

    def request(self, method: str, path: str, *, token: str | None = None,
                body: bytes | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer " + token} if token is not None else {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = {}
        status = response.status
        connection.close()
        return status, value

    def test_auth_site_ap_binding_and_redacted_eight_boolean_get(self) -> None:
        route = "GET /v1/sites/{site_ref}/aps/{device_ref}/qos"
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == route)
        self.assertEqual(operation["support_state"], "unknown")
        self.assertEqual(operation["runtime_evidence"], [])

        status, unauth = self.request("GET", self._public_path())
        self.assertEqual(status, 401)
        self.assertEqual(unauth["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])

        status, value = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertEqual(value["resource"], "ap_qos")
        self.assertEqual(value["data"], full_qos())
        self.assertFalse(value["partial"])
        self.assertEqual(self.transport_calls, [("GET", self._upstream_path(), None)])

        before = len(self.transport_calls)
        for site_ref, device_ref in (("e" * 24, DEVICE_REF),
                                     (OTHER_SITE_REF, DEVICE_REF),
                                     (SITE_REF, OTHER_DEVICE_REF)):
            status, error = self.request("GET", self._public_path(site_ref, device_ref), token=TOKEN)
            self.assertNotEqual(status, 200)
            self.assertEqual(len(self.transport_calls), before)
            self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))
            self.assertNotIn(AP_MAC, json.dumps(error))

        self.result = full_qos(name=PRIVATE_NAME, ip=PRIVATE_IP, mac=AP_MAC,
                               model="private-model", secret="private-value")
        status, value = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertTrue(value["partial"])
        for private in (PRIVATE_NAME, PRIVATE_IP, AP_MAC, "private-model", "private-value"):
            self.assertNotIn(private, json.dumps(value))
            self.assertNotIn(private, self.logs.getvalue())

    def test_missing_invalid_and_unknown_fields_are_partial_and_capability_unknown(self) -> None:
        fixtures = (
            {key: value for key, value in full_qos().items() if key != "support5g"},
            full_qos(deliveryEnable5g=1),
            full_qos(privateField="private-unrecognized-value"),
        )
        route = "GET /v1/sites/{site_ref}/aps/{device_ref}/qos"
        for raw in fixtures:
            with self.subTest(raw=raw):
                self.result = raw
                status, value = self.request("GET", self._public_path(), token=TOKEN)
                self.assertEqual(status, 200, value)
                self.assertTrue(value["partial"])
                self.assertNotIn("privateField", json.dumps(value))
                self.assertNotIn("private-unrecognized-value", json.dumps(value))
                operation = next(item for item in self.client.capabilities()["items"]
                                 if item["route"] == route)
                evidence = operation["runtime_evidence"][-1]
                self.assertEqual(evidence["support_state"], "unknown")
                self.assertEqual(evidence["observation"], "response_partial")
                self.assertEqual(evidence["hardware_support_state"], "unknown")
                self.assertEqual(evidence["firmware_support_state"], "unknown")

    def test_fixed_controller_get_route_and_upstream_failures_are_redacted(self) -> None:
        self.fail_upstream = True
        status, error = self.request("GET", self._public_path(), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_rejected")
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))

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
                ("GET", valid.replace("/qos", "/other")),
            )
            for method, path in rejected:
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, token="token")

    def test_public_route_rejects_other_methods_and_query_strings(self) -> None:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            status, _ = self.request(method, self._public_path(), token=TOKEN)
            self.assertNotEqual(status, 200)
        status, _ = self.request("GET", self._public_path() + "?debug=1", token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(self.transport_calls, [])

    def test_qos_patch_requires_guard_and_uses_only_documented_body_fields(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE_REF] = PRIVATE_SITE_ID
        client._device_macs_by_site_ref[SITE_REF] = {DEVICE_REF: AP_MAC}
        body = {"deliveryEnable2g": False, "deliveryEnable5g1": True,
                "deliveryEnable5g2": False, "deliveryEnable6g": True}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "operator_approval_required"):
                client.patch_ap_qos(SITE_REF, DEVICE_REF, body)
            client._write_dispatch_guard = lambda: None
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client.patch_ap_qos(SITE_REF, DEVICE_REF, body)
            for invalid in ({"support5g": False}, {"deliveryEnable5g1": 1},
                            {"deliveryEnable5g1": True, "support5g": True}):
                with self.assertRaisesRegex(OpenApiError, "ap_qos_change_invalid"):
                    client.patch_ap_qos(SITE_REF, DEVICE_REF, invalid)

    def test_http_preview_accepts_absent_values_for_explicitly_unsupported_bands(self) -> None:
        self.result = full_qos(support5g2=False, support6g=False)
        del self.result["deliveryEnable5g2"]
        del self.result["deliveryEnable6g"]
        writes: list[tuple[str, str, dict[str, bool]]] = []

        def read_state(site_ref: str, device_ref: str) -> dict[str, bool]:
            return self.client.read_ap_qos_change_state(site_ref, device_ref)["data"]

        plans = ApQosPlans(read_state,
                           lambda site, device, patch: writes.append((site, device, patch)),
                           writes_enabled=False)
        path = f"/v1/sites/{SITE_REF}/aps/{DEVICE_REF}/qos-preview"
        body = json.dumps({"changes": {"deliveryEnable5g": False},
                           "disruption_confirmed": True}).encode()
        with patch.object(main, "_AP_QOS_PLANS", plans):
            status, result = self.request("POST", path, token=TOKEN, body=body)

        self.assertEqual(status, 200, result)
        self.assertTrue(result["before"]["support5g2"] is False)
        self.assertNotIn("deliveryEnable5g2", result["before"])
        self.assertNotIn("deliveryEnable6g", result["before"])
        self.assertIn("approval_request", result)
        self.assertEqual(result["patch"], {
            "deliveryEnable2g": True, "deliveryEnable5g": False,
        })
        self.assertEqual(writes, [])
        self.assertEqual(self.transport_calls, [("GET", self._upstream_path(), None)])

    def test_http_preview_rejects_missing_delivery_values_for_supported_bands(self) -> None:
        self.result = full_qos()
        del self.result["deliveryEnable5g2"]
        del self.result["deliveryEnable6g"]
        writes: list[tuple[str, str, dict[str, bool]]] = []

        def read_state(site_ref: str, device_ref: str) -> dict[str, bool]:
            return self.client.read_ap_qos_change_state(site_ref, device_ref)["data"]

        plans = ApQosPlans(read_state,
                           lambda site, device, patch: writes.append((site, device, patch)),
                           writes_enabled=True)
        path = f"/v1/sites/{SITE_REF}/aps/{DEVICE_REF}/qos-preview"
        body = json.dumps({"changes": {"deliveryEnable5g": False},
                           "disruption_confirmed": True}).encode()
        with patch.object(main, "_AP_QOS_PLANS", plans):
            status, result = self.request("POST", path, token=TOKEN, body=body)

        self.assertEqual(status, 502, result)
        self.assertEqual(result, {"status": "error", "error": "ap_qos_state_unavailable"})
        self.assertEqual(plans.plans, {})
        self.assertEqual(writes, [])
        self.assertEqual(self.transport_calls, [("GET", self._upstream_path(), None)])

    def test_http_preview_rejects_invalid_or_unknown_source_state(self) -> None:
        base = full_qos(support5g2=False, support6g=False)
        del base["deliveryEnable5g2"]
        del base["deliveryEnable6g"]
        fixtures = ({**base, "deliveryEnable6g": "invalid"},
                    {**base, "unrecognizedField": True})
        path = f"/v1/sites/{SITE_REF}/aps/{DEVICE_REF}/qos-preview"
        body = json.dumps({"changes": {"deliveryEnable5g": False},
                           "disruption_confirmed": True}).encode()
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                self.result = fixture
                plans = ApQosPlans(
                    lambda site_ref, device_ref: self.client.read_ap_qos_change_state(
                        site_ref, device_ref)["data"],
                    lambda *_: self.fail("write called"), writes_enabled=False)
                with patch.object(main, "_AP_QOS_PLANS", plans):
                    status, result = self.request("POST", path, token=TOKEN, body=body)
                self.assertEqual(status, 502, result)
                self.assertEqual(result["error"], "ap_qos_state_unavailable")
                self.assertEqual(plans.plans, {})

    def test_http_preview_returns_supported_full_state_without_dispatch(self) -> None:
        state = {"support2g": True, "support5g": True, "support5g2": True,
                 "support6g": False, "deliveryEnable2g": True,
                 "deliveryEnable5g": True, "deliveryEnable5g2": False,
                 "deliveryEnable6g": False}
        plans = ApQosPlans(lambda *_: state.copy(), lambda *_: self.fail("write called"),
                           writes_enabled=False)
        path = f"/v1/sites/{SITE_REF}/aps/{DEVICE_REF}/qos-preview"
        body = json.dumps({"changes": {"deliveryEnable5g": False},
                           "disruption_confirmed": True}).encode()
        with patch.object(main, "_AP_QOS_PLANS", plans):
            status, result = self.request("POST", path, token=TOKEN, body=body)
        self.assertEqual(status, 200, result)
        self.assertFalse(result["writes_enabled"])
        self.assertEqual(result["patch"], {"deliveryEnable2g": True,
                         "deliveryEnable5g1": False, "deliveryEnable5g2": False})
        self.assertEqual(self.transport_calls, [])


if __name__ == "__main__":
    unittest.main()
