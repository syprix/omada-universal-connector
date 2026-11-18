from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class SwitchPortStatusOpenApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=2, max_pages=4))
        self.site_ref, self.switch_ref = "a" * 24, "b" * 24
        self.switch_mac = "00:11:22:33:44:55"
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._switch_macs_by_site_ref[self.site_ref] = {
            self.switch_ref: self.switch_mac}

    @staticmethod
    def row(port: int = 7, *, disable=False, connected=0, mac="00:11:22:33:44:55"):
        return {"switchMac": mac, "port": port, "disable": disable,
                "connectedStatus": connected, "portName": "private-port-label"}

    def test_reads_single_matching_row_from_paged_inventory_and_normalizes_status(self):
        rows = [
            self.row(1, mac="00:11:22:33:44:66"),
            self.row(3, disable=True, connected=2),
            self.row(7, disable=False, connected=1),
        ]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows) as read_pages:
            result = self.client.read_switch_port_status(self.site_ref, self.switch_ref, 7)
        read_pages.assert_called_once_with(
            "/openapi/v1/ctrl/sites/site_1/switches/ports/overview", "token")
        self.assertEqual(result["data"], {"status": 1})
        self.assertNotIn("private-port-label", str(result))
        self.assertNotIn(self.switch_mac, str(result))

    def test_disabled_row_maps_to_status_zero(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=[
                    self.row(disable=True, connected=2)]):
            result = self.client.read_switch_port_status(self.site_ref, self.switch_ref, 7)
        self.assertEqual(result["data"], {"status": 0})

    def test_unknown_and_ambiguous_matching_port_are_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=[self.row(2)]):
            with self.assertRaisesRegex(OpenApiError, "switch_port_unknown"):
                self.client.read_switch_port_status(self.site_ref, self.switch_ref, 7)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=[self.row(), self.row()]):
            with self.assertRaisesRegex(OpenApiError, "switch_port_ambiguous"):
                self.client.read_switch_port_status(self.site_ref, self.switch_ref, 7)

    def test_invalid_disable_connected_status_and_inconsistent_pairs_fail_closed(self):
        cases = [
            ({**self.row(), "disable": 0}, "openapi_response_invalid"),
            ({**self.row(), "connectedStatus": True}, "openapi_response_invalid"),
            ({**self.row(), "connectedStatus": "0"}, "openapi_response_invalid"),
            ({**self.row(), "connectedStatus": -1}, "openapi_response_invalid"),
            ({**self.row(), "connectedStatus": 3}, "openapi_response_invalid"),
            ({**self.row(), "disable": True, "connectedStatus": 0}, "switch_port_state_inconsistent"),
            ({**self.row(), "disable": False, "connectedStatus": 2}, "switch_port_state_inconsistent"),
        ]
        for row, code in cases:
            with self.subTest(row=row), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_read_pages", return_value=[row]):
                with self.assertRaisesRegex(OpenApiError, code):
                    self.client.read_switch_port_status(self.site_ref, self.switch_ref, 7)

    def test_site_switch_and_port_identifiers_are_validated_before_read(self):
        with self.assertRaisesRegex(OpenApiError, "site_ref_invalid"):
            self.client.read_switch_port_status("raw-site-id", self.switch_ref, 7)
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_switch_port_status("c" * 24, self.switch_ref, 7)
        with self.assertRaisesRegex(OpenApiError, "switch_ref_invalid"):
            self.client.read_switch_port_status(self.site_ref, "raw-switch-id", 7)
        with self.assertRaisesRegex(OpenApiError, "switch_ref_unknown"):
            self.client.read_switch_port_status(self.site_ref, "c" * 24, 7)
        for port in (True, -1, 4097, "7"):
            with self.subTest(port=port), self.assertRaisesRegex(OpenApiError, "switch_port_invalid"):
                self.client.read_switch_port_status(self.site_ref, self.switch_ref, port)

    def test_ambiguous_switch_mac_blocks_status_read_and_write_before_io(self):
        self.client._switch_macs_by_site_ref[self.site_ref]["c" * 24] = self.switch_mac
        with patch.object(self.client, "_read_pages", side_effect=AssertionError("must not read")), \
                patch.object(self.client, "_access_token", side_effect=AssertionError("must not authenticate")), \
                patch.object(self.client, "_request_json", side_effect=AssertionError("must not write")):
            with self.assertRaisesRegex(OpenApiError, "switch_ref_ambiguous"):
                self.client.read_switch_port_status(self.site_ref, self.switch_ref, 7)
            with self.assertRaisesRegex(OpenApiError, "switch_ref_ambiguous"):
                self.client.put_switch_port_status(
                    self.site_ref, self.switch_ref, 7, {"status": 0})

    def test_put_accepts_only_status_zero_or_one_and_uses_exact_fixed_request(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={}) as request:
            self.client.put_switch_port_status(
                self.site_ref, self.switch_ref, 7, {"status": 1})
        request.assert_called_once_with(
            "PUT", "/openapi/v1/ctrl/sites/site_1/switches/00:11:22:33:44:55/ports/7/status",
            body=b'{"status":1}', token="token")

    def test_put_rejects_invalid_bodies_ids_and_ports_before_dispatch(self):
        invalid_bodies = (
            None, {}, {"status": True}, {"status": 2}, {"status": -1},
            {"status": "1"}, {"status": 1, "extra": 0}, {"poeMode": 1},
        )
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json") as request:
            for body in invalid_bodies:
                with self.subTest(body=body), self.assertRaisesRegex(
                        OpenApiError, "switch_port_status_invalid"):
                    self.client.put_switch_port_status(
                        self.site_ref, self.switch_ref, 7, body)
            with self.assertRaisesRegex(OpenApiError, "switch_ref_unknown"):
                self.client.put_switch_port_status(self.site_ref, "c" * 24, 7, {"status": 1})
            with self.assertRaisesRegex(OpenApiError, "switch_port_invalid"):
                self.client.put_switch_port_status(self.site_ref, self.switch_ref, True, {"status": 1})
        request.assert_not_called()

    def test_request_allowlist_rejects_other_methods_paths_ids_and_bodies(self):
        good_path = "/openapi/v1/ctrl/sites/site_1/switches/00:11:22:33:44:55/ports/7/status"
        with patch.object(self.client, "_connection", side_effect=AssertionError("must not connect")):
            with self.assertRaisesRegex(OpenApiError, "operator_approval_required"):
                self.client._request_json("PUT", good_path, body=b'{"status":1}')

        guard_calls: list[str] = []
        self.client._write_dispatch_guard = lambda: guard_calls.append("checked")

        class Response:
            status = 200

            @staticmethod
            def read(_limit):
                return b'{"result":null}'

            @staticmethod
            def getheader(_name, _default=""):
                return "application/json"

        class Connection:
            def request(_self, method, path, *, body, headers):
                self.assertEqual(guard_calls, ["checked"])
                self.assertEqual((method, path, body), ("PUT", good_path, b'{"status":1}'))

            @staticmethod
            def getresponse():
                return Response()

            @staticmethod
            def close():
                pass

        with patch.object(self.client, "_connection", return_value=Connection()) as connection:
            self.assertEqual(self.client._request_json(
                "PUT", good_path, body=b'{"status":1}'), {"result": None})
        connection.assert_called_once()
        self.assertEqual(guard_calls, ["checked"])

        with patch.object(self.client, "_connection", side_effect=AssertionError("must not connect")):
            bad_requests = (
                ("GET", good_path, None),
                ("PATCH", good_path, b'{"status":1}'),
                ("POST", good_path, b'{"status":1}'),
                ("PUT", good_path + "/extra", b'{"status":1}'),
                ("PUT", good_path.replace("/ctrl/", "/other/"), b'{"status":1}'),
                ("PUT", good_path.replace("/ports/7/", "/ports/07/"), b'{"status":1}'),
                ("PUT", good_path, b'{"status":2}'),
                ("PUT", good_path, b'{"status":1,"extra":0}'),
            )
            for method, path, body in bad_requests:
                with self.subTest(method=method, path=path, body=body), \
                        self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                    self.client._request_json(method, path, body=body)


if __name__ == "__main__":
    unittest.main()
