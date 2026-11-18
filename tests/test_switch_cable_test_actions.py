from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF = "a" * 24
SWITCH_REF = "b" * 24
SWITCH_MAC = "00:11:22:33:44:55"


class SwitchCableTestActionOpenApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"
        self.client._switch_macs_by_site_ref[SITE_REF] = {SWITCH_REF: SWITCH_MAC}

    def test_start_is_exact_and_requires_the_dispatch_guard(self):
        path = ("/openapi/v1/ctrl/sites/site_1/cable-test/switches/"
                f"{SWITCH_MAC}/start")
        body = b'{"portList":[{"port":3},{"port":7}]}'
        with patch.object(self.client, "_connection", side_effect=AssertionError("must not connect")):
            with self.assertRaisesRegex(OpenApiError, "operator_approval_required"):
                self.client._request_json("POST", path, body=body)

        guards: list[str] = []
        self.client._write_dispatch_guard = lambda: guards.append("checked")
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"errorCode": 0}) as request:
            self.client.start_switch_cable_test(SITE_REF, SWITCH_REF, [3, 7])
        request.assert_called_once_with("POST", path, body=body, token="token")

    def test_cancel_is_effectful_post_and_uses_the_same_guard(self):
        path = ("/openapi/v1/ctrl/sites/site_1/cable-test/switches/"
                f"{SWITCH_MAC}/cancel")
        with patch.object(self.client, "_connection", side_effect=AssertionError("must not connect")):
            with self.assertRaisesRegex(OpenApiError, "operator_approval_required"):
                self.client._request_json("POST", path)

        guards: list[str] = []
        self.client._write_dispatch_guard = lambda: guards.append("checked")
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"errorCode": 0}) as request:
            self.client.cancel_switch_cable_test(SITE_REF, SWITCH_REF)
        request.assert_called_once_with("POST", path, token="token")

    def test_invalid_target_or_ambiguous_inventory_fails_before_io(self):
        with patch.object(self.client, "_access_token", side_effect=AssertionError("must not auth")), \
                patch.object(self.client, "_request_json", side_effect=AssertionError("must not send")):
            for ports in ([], [True], [0], [4097], [3, 3], list(range(1, 18))):
                with self.subTest(ports=ports), self.assertRaisesRegex(
                        OpenApiError, "cable_test_ports_invalid"):
                    self.client.start_switch_cable_test(SITE_REF, SWITCH_REF, ports)
            self.client._switch_macs_by_site_ref[SITE_REF]["c" * 24] = SWITCH_MAC.lower()
            with self.assertRaisesRegex(OpenApiError, "switch_ref_ambiguous"):
                self.client.start_switch_cable_test(SITE_REF, SWITCH_REF, [3])
            with self.assertRaisesRegex(OpenApiError, "switch_ref_ambiguous"):
                self.client.cancel_switch_cable_test(SITE_REF, SWITCH_REF)

    def test_transport_rejects_bad_method_path_body_and_response(self):
        path = ("/openapi/v1/ctrl/sites/site_1/cable-test/switches/"
                f"{SWITCH_MAC}/start")
        with patch.object(self.client, "_connection", side_effect=AssertionError("must not connect")):
            for method, candidate, body in (
                    ("GET", path, b'{"portList":[{"port":3}]}'),
                    ("POST", path + "/extra", b'{"portList":[{"port":3}]}'),
                    ("POST", path, b'{"portList":null}'),
                    ("POST", path, b'{"portList":[{"port":3,"other":1}]}'),
                    ("POST", path, b'{"portList":[{"port":true}]}'),
                    ("POST", path.replace("/ctrl/", "/other/"),
                     b'{"portList":[{"port":3}]}')):
                with self.subTest(method=method, path=candidate), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    self.client._request_json(method, candidate, body=body)

        self.client._write_dispatch_guard = lambda: None
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json",
                             side_effect=OpenApiError("openapi_rejected", -39700)):
            with self.assertRaisesRegex(OpenApiError, "openapi_rejected"):
                self.client.start_switch_cable_test(SITE_REF, SWITCH_REF, [3])
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"errorCode": 0, "result": {}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.start_switch_cable_test(SITE_REF, SWITCH_REF, [3])


if __name__ == "__main__":
    unittest.main()
