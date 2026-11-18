from __future__ import annotations

import builtins
import io
import json
import os
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.operator_approval import sign_approval


TOKEN = "ap-ofdma-integration-token-0123456789abcdef"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
DEVICE_REF = "c" * 24
OTHER_DEVICE_REF = "d" * 24
SITE_ID = "private-site-id"
AP_MAC = "AA-BB-CC-DD-EE-FF"
PRIVATE_NAME = "private-access-point"
PRIVATE_IP = "192.0.2.33"
OPERATOR_ID = "op_" + "5" * 24

ENABLE_FIELDS = ("ofdmaEnable2g", "ofdmaEnable5g", "ofdmaEnable5g2", "ofdmaEnable6g")
SUPPORT_FIELDS = ("supportOfdma2g", "supportOfdma5g", "supportOfdma5g2", "supportOfdma6g")
ALL_FIELDS = ENABLE_FIELDS + SUPPORT_FIELDS
TARGET_CHANGE = {"ofdmaEnable5g": True}


def complete_state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "ofdmaEnable2g": True, "ofdmaEnable5g": False,
        "ofdmaEnable5g2": False, "ofdmaEnable6g": False,
        "supportOfdma2g": True, "supportOfdma5g": True,
        "supportOfdma5g2": True, "supportOfdma6g": True,
    }
    state.update(overrides)
    return state


class ApOfdmaIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.journal_dir = os.path.join(self.temp.name, "journal")
        os.mkdir(self.journal_dir, 0o700)
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as handle:
            handle.write(TOKEN)
        self.operator_key = b"o" * 32
        self.operator_key_file = os.path.join(self.temp.name, "operator-key")
        fd = os.open(self.operator_key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(self.operator_key)

        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        # Synthetic stable ref key and real isolated journal; transport is fake.
        self.client._ref_key = b"r" * 32
        self.client.config = replace(self.client.config, reference_key_file="synthetic-reference-key")
        self.client._site_ids_by_ref[SITE_REF] = SITE_ID
        self.client._site_ids_by_ref[OTHER_SITE_REF] = "other-private-site-id"
        self.client._device_macs_by_site_ref[SITE_REF] = {DEVICE_REF: AP_MAC}
        self.client._device_macs_by_site_ref[OTHER_SITE_REF] = {
            OTHER_DEVICE_REF: "11:22:33:44:55:66"}
        self.get_result: object = complete_state()
        self.put_calls: list[tuple[str, dict[str, object]]] = []
        self.transport_calls: list[tuple[str, str, bytes | None]] = []
        self.mutate_other_band_on_patch = False

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.transport_calls.append((method, path, body))
            self.assertEqual(path, self._upstream_path())
            self.assertEqual(token, "synthetic-upstream-token")
            if method == "GET":
                self.assertIsNone(body)
                return {"result": json.loads(json.dumps(self.get_result))}
            self.assertEqual(method, "PATCH")
            self.assertIsInstance(body, bytes)
            decoded = json.loads(body)
            self.assertEqual(len(decoded), 1)
            field, value = next(iter(decoded.items()))
            self.assertIn(field, ENABLE_FIELDS)
            self.assertIs(type(value), bool)
            self.put_calls.append((path, decoded))
            if not isinstance(self.get_result, dict):
                raise AssertionError("fake OFDMA state must be an object")
            self.get_result[field] = value
            if self.mutate_other_band_on_patch:
                self.get_result["ofdmaEnable2g"] = False
            return {"result": None}

        self.transport_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.transport_patch.start()
        self.access_patch = patch.object(
            self.client, "_access_token", return_value="synthetic-upstream-token")
        self.access_patch.start()
        self.env_patch = patch.dict(os.environ, {
            "OMADA_CONNECTOR_TOKEN_FILE": self.token_file,
            "OMADA_ENABLE_WRITES": "false",
            "OMADA_CHANGE_JOURNAL_DIR": self.journal_dir,
            "OMADA_OPERATOR_APPROVAL_KEY_FILE": self.operator_key_file,
        })
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.runtime_patch = patch.object(main, "_JOURNAL_RUNTIME", None)
        self.runtime_patch.start()
        self.plans_patch = patch.object(main, "_AP_OFDMA_PLANS", None)
        self.plans_patch.start()
        self.active_patch = patch.object(main, "_ACTIVE_APPROVAL", None)
        self.active_patch.start()
        self.consumed_patch = patch.dict(main._CONSUMED_APPROVALS, {}, clear=True)
        self.consumed_patch.start()
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
        runtime = main._JOURNAL_RUNTIME
        if runtime is not None:
            runtime.close()
        self.print_patch.stop()
        self.plans_patch.stop()
        self.runtime_patch.stop()
        self.active_patch.stop()
        self.consumed_patch.stop()
        self.client_patch.stop()
        self.env_patch.stop()
        self.access_patch.stop()
        self.transport_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def _upstream_path(controller_id: str = "ctrl") -> str:
        return f"/openapi/v1/{controller_id}/sites/{SITE_ID}/aps/{AP_MAC}/ofdma"

    @staticmethod
    def _read_path(site_ref: str = SITE_REF, device_ref: str = DEVICE_REF) -> str:
        return f"/v1/sites/{site_ref}/aps/{device_ref}/ofdma"

    @staticmethod
    def _preview_path(site_ref: str = SITE_REF, device_ref: str = DEVICE_REF) -> str:
        return f"/v1/sites/{site_ref}/aps/{device_ref}/ofdma-preview"

    def request(self, method: str, path: str, *, token: str | None = None,
                body: dict[str, object] | None = None,
                raw_body: str | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers: dict[str, str] = {}
        encoded = raw_body
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if body is not None or raw_body is not None:
            if encoded is None:
                encoded = json.dumps(body, separators=(",", ":"))
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {}
        status = response.status
        connection.close()
        return status, result

    def approval_body(self, preview: dict[str, object], *, key: bytes | None = None,
                      expiry: int | None = None, signing_now: int | None = None) -> dict[str, object]:
        current = int(time.time()) if signing_now is None else signing_now
        request = preview["approval_request"]
        assert isinstance(request, dict)
        signed = sign_approval(
            key or self.operator_key, operation="ap-ofdma", plan_id=preview["plan_id"],
            plan_digest=request["digest"], operator_id=OPERATOR_ID,
            expires_at=expiry if expiry is not None else current + 120, now=current)
        return {"approval": signed}

    def preview(self, *, changes: dict[str, object] | None = None,
                disruption_confirmed: object = True) -> dict[str, object]:
        status, value = self.request(
            "POST", self._preview_path(), token=TOKEN,
            body={"changes": changes if changes is not None else dict(TARGET_CHANGE),
                  "disruption_confirmed": disruption_confirmed})
        self.assertEqual(status, 200, value)
        return value

    def test_auth_site_ap_binding_and_eight_field_redacted_get(self) -> None:
        status, unauth = self.request("GET", self._read_path())
        self.assertEqual(status, 401)
        self.assertEqual(unauth["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])

        status, result = self.request("GET", self._read_path(), token=TOKEN)
        self.assertEqual(status, 200, result)
        self.assertEqual(set(result["data"]), set(ALL_FIELDS))
        self.assertEqual(result["data"], complete_state())
        self.assertFalse(result["partial"])
        self.assertEqual(self.transport_calls, [("GET", self._upstream_path(), None)])

        before = len(self.transport_calls)
        status, unknown_site = self.request("GET", self._read_path("e" * 24), token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(len(self.transport_calls), before)
        self.assertNotIn(SITE_ID, json.dumps(unknown_site))

        status, cross_site_ap = self.request(
            "GET", self._read_path(OTHER_SITE_REF, DEVICE_REF), token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(len(self.transport_calls), before)
        self.assertNotIn(AP_MAC, json.dumps(cross_site_ap))

        status, unknown_ap = self.request(
            "GET", self._read_path(SITE_REF, OTHER_DEVICE_REF), token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(len(self.transport_calls), before)
        self.assertNotIn(AP_MAC, json.dumps(unknown_ap))

        self.get_result = complete_state(
            name=PRIVATE_NAME, ip=PRIVATE_IP, model="private-model", mac="11:22:33:44:55:66")
        status, partial = self.request("GET", self._read_path(), token=TOKEN)
        self.assertEqual(status, 200)
        self.assertTrue(partial["partial"])
        rendered = json.dumps(partial)
        for private in (PRIVATE_NAME, PRIVATE_IP, "private-model", "11:22:33:44:55:66"):
            self.assertNotIn(private, rendered)
            self.assertNotIn(private, self.logs.getvalue())

    def test_preview_requires_confirmed_single_boolean_and_complete_supported_state(self) -> None:
        for raw_state, expected_error in (
                ({key: value for key, value in complete_state().items() if key != "supportOfdma5g"},
                 "readback_unavailable"),
                (complete_state(supportOfdma5g=False), "ofdma_band_not_reported_supported"),
                (complete_state(extra="private-unknown"), "readback_unavailable")):
            with self.subTest(error=expected_error):
                self.get_result = raw_state
                before_patch = len(self.put_calls)
                status, error = self.request(
                    "POST", self._preview_path(), token=TOKEN,
                    body={"changes": dict(TARGET_CHANGE), "disruption_confirmed": True})
                self.assertNotEqual(status, 200)
                self.assertEqual(error["error"], expected_error)
                self.assertNotIn("plan_id", error)
                self.assertEqual(len(self.put_calls), before_patch)

        self.get_result = complete_state()
        bad_requests = (
            {"changes": dict(TARGET_CHANGE)},
            {"changes": dict(TARGET_CHANGE), "disruption_confirmed": False},
            {"changes": {"ofdmaEnable5g": 1}, "disruption_confirmed": True},
            {"changes": {"ofdmaEnable5g": True, "ofdmaEnable2g": False},
             "disruption_confirmed": True},
            {"changes": {"supportOfdma5g": False}, "disruption_confirmed": True},
            {"changes": dict(TARGET_CHANGE), "disruption_confirmed": True, "extra": 1},
        )
        for body in bad_requests:
            status, error = self.request("POST", self._preview_path(), token=TOKEN, body=body)
            self.assertEqual(status, 400, (body, error))
            self.assertNotIn("plan_id", error)
        status, error = self.request("POST", self._preview_path(), token=TOKEN,
                                     body={"changes": dict(TARGET_CHANGE),
                                           "disruption_confirmed": True})
        self.assertEqual(status, 200, error)
        self.assertEqual(error["band_field"], "ofdmaEnable5g")
        self.assertEqual(error["before"], complete_state())
        expected_target = complete_state(ofdmaEnable5g=True)
        self.assertEqual(error["target"], expected_target)
        self.assertEqual(error["rollback"], {"ofdmaEnable5g": False})
        self.assertEqual(error["warning"],
                         "ofdma_partial_patch_effect_unknown_other_settings_might_be_affected")

    def test_disabled_missing_forged_and_expired_approval_never_patch(self) -> None:
        status, unauthorized_preview = self.request(
            "POST", self._preview_path(),
            body={"changes": dict(TARGET_CHANGE), "disruption_confirmed": True})
        self.assertEqual(status, 401)
        self.assertEqual(unauthorized_preview["error"], "unauthorized")
        self.assertEqual(self.transport_calls, [])
        preview = self.preview()
        apply_path = f"/v1/ap-ofdma-plans/{preview['plan_id']}/apply"
        status, unauthorized_apply = self.request("POST", apply_path, body={})
        self.assertEqual(status, 401)
        self.assertEqual(unauthorized_apply["error"], "unauthorized")
        self.assertEqual(self.put_calls, [])

        status, disabled = self.request("POST", apply_path, token=TOKEN, body={})
        self.assertEqual(status, 409)
        self.assertEqual(disabled["error"], "writes_disabled")
        self.assertEqual(self.put_calls, [])

        os.environ["OMADA_ENABLE_WRITES"] = "true"
        status, no_approval = self.request("POST", apply_path, token=TOKEN, body={})
        self.assertEqual(status, 409)
        self.assertEqual(no_approval["error"], "operator_approval_required")
        self.assertEqual(self.put_calls, [])

        forged = self.approval_body(preview, key=b"x" * 32)
        status, forged_result = self.request("POST", apply_path, token=TOKEN, body=forged)
        self.assertEqual(status, 409)
        self.assertIn(forged_result["error"], {"operator_approval_invalid", "operator_approval_mismatch"})
        self.assertEqual(self.put_calls, [])

        now = int(time.time())
        expired = self.approval_body(preview, expiry=now - 1, signing_now=now - 10)
        status, expired_result = self.request("POST", apply_path, token=TOKEN, body=expired)
        self.assertEqual(status, 409)
        self.assertEqual(expired_result["error"], "operator_approval_expired")
        self.assertEqual(self.put_calls, [])

    def test_stale_state_or_support_change_blocks_apply_without_patch(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        for changed_state, expected_error in (
                (complete_state(ofdmaEnable2g=False), "state_changed"),
                (complete_state(supportOfdma5g=False), "ofdma_support_state_changed")):
            self.get_result = complete_state()
            preview = self.preview()
            self.get_result = changed_state
            status, error = self.request(
                "POST", f"/v1/ap-ofdma-plans/{preview['plan_id']}/apply", token=TOKEN,
                body=self.approval_body(preview))
            self.assertEqual(status, 409)
            self.assertEqual(error["error"], expected_error)
            self.assertEqual(self.put_calls, [])

    def test_approved_apply_patches_one_field_and_verifies_all_eight_readback_fields(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        initial = complete_state()
        self.get_result = dict(initial)
        preview = self.preview()
        self.assertEqual(preview["before"], initial)
        self.assertEqual(preview["target"], complete_state(ofdmaEnable5g=True))

        status, applied = self.request(
            "POST", f"/v1/ap-ofdma-plans/{preview['plan_id']}/apply", token=TOKEN,
            body=self.approval_body(preview))
        self.assertEqual(status, 200, applied)
        self.assertEqual(applied["status"], "verified")
        self.assertEqual(applied["before"], initial)
        self.assertEqual(applied["after"], complete_state(ofdmaEnable5g=True))
        self.assertEqual(applied["patch"], TARGET_CHANGE)
        self.assertEqual(self.get_result, complete_state(ofdmaEnable5g=True))
        self.assertEqual([item[0] for item in self.transport_calls],
                         ["GET", "GET", "GET", "PATCH", "GET"])
        self.assertEqual(self.put_calls, [(self._upstream_path(), TARGET_CHANGE)])
        patch_body = json.loads(next(body for method, _path, body in self.transport_calls
                                     if method == "PATCH"))
        self.assertEqual(patch_body, TARGET_CHANGE)
        for private in (AP_MAC, PRIVATE_NAME, PRIVATE_IP, "private-model"):
            self.assertNotIn(private, json.dumps(preview) + json.dumps(applied))
            self.assertNotIn(private, self.logs.getvalue())

        status, replay = self.request(
            "POST", f"/v1/ap-ofdma-plans/{preview['plan_id']}/apply", token=TOKEN,
            body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len(self.put_calls), 1)

    def test_other_band_readback_change_becomes_in_doubt_and_recovers_without_replay(self) -> None:
        os.environ["OMADA_ENABLE_WRITES"] = "true"
        self.get_result = complete_state()
        preview = self.preview()
        self.mutate_other_band_on_patch = True
        apply_path = f"/v1/ap-ofdma-plans/{preview['plan_id']}/apply"
        status, result = self.request("POST", apply_path, token=TOKEN,
                                      body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "change_in_doubt")
        self.assertEqual(len(self.put_calls), 1)

        status, replay = self.request("POST", apply_path, token=TOKEN,
                                      body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(replay["error"], "plan_unavailable")
        self.assertEqual(len(self.put_calls), 1)

        runtime = main._JOURNAL_RUNTIME
        self.assertIsNotNone(runtime)
        runtime.close()
        main._JOURNAL_RUNTIME = None
        main._AP_OFDMA_PLANS = None
        status, in_doubt = self.request(
            "GET", "/v1/change-plans/ap-ofdma/in-doubt", token=TOKEN)
        self.assertEqual(status, 200, in_doubt)
        self.assertEqual(len(in_doubt["items"]), 1)
        self.assertEqual(in_doubt["items"][0]["plan_id"], preview["plan_id"])
        self.assertEqual(in_doubt["items"][0]["state"], "in_doubt")

        status, recovered = self.request("POST", apply_path, token=TOKEN,
                                          body=self.approval_body(preview))
        self.assertEqual(status, 409)
        self.assertEqual(recovered["error"], "plan_unavailable")
        self.assertEqual(len(self.put_calls), 1)

    def test_controller_transport_allowlist_has_only_exact_patch_field(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        path = self._upstream_path()
        valid_body = b'{"ofdmaEnable5g":true}'
        with patch.object(client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", path, token="token")
            with self.assertRaisesRegex(OpenApiError, "operator_approval_required"):
                client._request_json("PATCH", path, body=valid_body, token="token")
            client._write_dispatch_guard = lambda: None
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("PATCH", path, body=valid_body, token="token")
            rejected = (
                ("GET", path + "?raw=true", None),
                ("GET", self._upstream_path("foreign-controller"), None),
                ("PATCH", self._upstream_path("foreign-controller"), valid_body),
                ("POST", path, valid_body),
                ("PUT", path, valid_body),
                ("PATCH", path, b'{"ofdmaEnable5g":1}'),
                ("PATCH", path, b'{"ofdmaEnable5g":true,"ofdmaEnable2g":false}'),
                ("PATCH", path, b'{"supportOfdma5g":false}'),
                ("PATCH", path, b'{"ofdmaEnable5g":true,"ofdmaEnable5g":false}'),
                ("PATCH", path.replace("/ofdma", "/ofdma-unknown"), valid_body),
                ("DELETE", path, None),
            )
            for method, rejected_path, body in rejected:
                with self.subTest(method=method, path=rejected_path, body=body), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, rejected_path, body=body, token="token")


if __name__ == "__main__":
    unittest.main()
