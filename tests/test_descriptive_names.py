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

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig


class DescriptiveNamesTests(unittest.TestCase):
    def _client(self, enabled: bool = False) -> OmadaOpenApiClient:
        return OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller_1", "client-id-file",
            "client-secret-file", cert_sha256="a" * 64,
            expose_descriptive_names=enabled))

    @staticmethod
    def _fixture_rows(path: str, _token: str) -> list[dict[str, object]]:
        if path.endswith("/sites"):
            return [{"siteId": "site-1", "name": "Fixture Site",
                     "password": "must-never-escape", "description": "raw site data"}]
        if path.endswith("/devices"):
            return [{"id": "ap-1", "deviceType": "AP", "mac": "00-11-22-33-44-55",
                     "name": "Lab Access Point", "ip": "192.0.2.8",
                     "password": "must-never-escape", "raw": "raw device data"}]
        if path.endswith("/wireless-network/ssids"):
            return [{"id": "ssid-1", "name": "Fixture Guest WiFi",
                     "password": "must-never-escape", "psk": "must-never-escape",
                     "description": True, "raw": "raw SSID data"}]
        raise AssertionError("unexpected fixture path")

    def _all_three_lists(self, client: OmadaOpenApiClient) -> dict[str, dict[str, object]]:
        with patch.object(client, "_access_token", return_value="fixture-token"), \
                patch.object(client, "_read_pages", side_effect=self._fixture_rows):
            sites = client.list_sites()
            site_ref = sites["items"][0]["site_ref"]
            devices = client.list_devices(site_ref)
            ssids = client.list_ssids(site_ref)
        return {"sites": sites["items"][0], "devices": devices["items"][0],
                "ssids": ssids["items"][0]}

    def test_default_off_and_explicit_opt_in_returns_only_named_fields(self) -> None:
        disabled = self._all_three_lists(self._client())
        enabled = self._all_three_lists(self._client(enabled=True))
        for row in disabled.values():
            self.assertFalse(any(key.endswith("_name") for key in row))
        self.assertEqual(enabled["sites"]["site_name"], "Fixture Site")
        self.assertEqual(enabled["devices"]["device_name"], "Lab Access Point")
        self.assertEqual(enabled["ssids"]["ssid_name"], "Fixture Guest WiFi")
        rendered = json.dumps(enabled, ensure_ascii=False)
        for excluded in ("must-never-escape", "192.0.2.8", "raw site data",
                         "raw device data", "raw SSID data", "password", "psk"):
            self.assertNotIn(excluded, rendered)

    def test_environment_opt_in_requires_literal_true_and_defaults_off(self) -> None:
        required = {
            "OMADA_BASE_URL": "https://controller.example",
            "OMADA_CONTROLLER_ID": "controller_1",
            "OMADA_CLIENT_ID_FILE": "/private/client-id",
            "OMADA_CLIENT_SECRET_FILE": "/private/client-secret",
            "OMADA_CERT_SHA256": "a" * 64,
        }
        with patch.dict(os.environ, required, clear=True):
            self.assertFalse(OpenApiConfig.from_env().expose_descriptive_names)
        with patch.dict(os.environ, {**required, "OMADA_EXPOSE_DESCRIPTIVE_NAMES": "true"}, clear=True):
            self.assertTrue(OpenApiConfig.from_env().expose_descriptive_names)
        with patch.dict(os.environ, {**required, "OMADA_EXPOSE_DESCRIPTIVE_NAMES": "yes"}, clear=True):
            self.assertFalse(OpenApiConfig.from_env().expose_descriptive_names)

    def test_omits_overlong_control_and_invalid_unicode_names(self) -> None:
        invalid_names = ("", "   ", "bad\nsite", "bad\x00site", "bad\u200bsite", "bad\ud800site")
        client = self._client(enabled=True)
        for maximum, object_id in ((64, "site"), (128, "device"), (32, "ssid")):
            with self.subTest(maximum=maximum):
                self.assertEqual(client._display_name({"name": "n" * maximum}, maximum), "n" * maximum)
                self.assertIsNone(client._display_name({"name": "n" * (maximum + 1)}, maximum))
                for name in invalid_names:
                    self.assertIsNone(client._display_name({"name": name}, maximum),
                                      f"{object_id} name accepted invalid input")

    def test_http_names_require_bearer_auth_and_never_enter_logs(self) -> None:
        token = "fixture-caller-token-0123456789abcdef"
        site_name, device_name, ssid_name = "site-name-sentinel", "device-name-sentinel", "ssid-name-sentinel"
        rows = {
            "sites": [{"siteId": "site-1", "name": site_name}],
            "devices": [{"id": "ap-1", "deviceType": "AP", "mac": "00-11-22-33-44-55",
                         "name": device_name}],
            "ssids": [{"id": "ssid-1", "name": ssid_name}],
        }
        client = self._client(enabled=True)
        request_log = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            token_file = os.path.join(directory, "caller-token")
            with open(token_file, "w", encoding="utf-8") as handle:
                handle.write(token)

            with patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": token_file}), \
                    patch.object(client, "_access_token", return_value="fixture-upstream-token"), \
                    patch.object(client, "_read_pages", side_effect=lambda path, _token: (
                        rows["sites"] if path.endswith("/sites") else
                        rows["devices"] if path.endswith("/devices") else rows["ssids"])), \
                    patch.object(main, "_openapi_client", return_value=client), \
                    patch.object(main.Handler, "log_message",
                                 lambda _self, fmt, *args: request_log.write(fmt % args + "\n")):
                server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    status, denied = self._request(server.server_port, "/v1/sites")
                    self.assertEqual(status, 401)
                    self.assertFalse(any(name in json.dumps(denied)
                                         for name in (site_name, device_name, ssid_name)))

                    status, sites = self._request(server.server_port, "/v1/sites", token)
                    self.assertEqual(status, 200)
                    self.assertEqual(sites["items"][0]["site_name"], site_name)
                    site_ref = sites["items"][0]["site_ref"]
                    status, devices = self._request(server.server_port,
                                                    f"/v1/sites/{site_ref}/devices", token)
                    self.assertEqual(status, 200)
                    self.assertEqual(devices["items"][0]["device_name"], device_name)
                    status, ssids = self._request(server.server_port,
                                                  f"/v1/sites/{site_ref}/ssids", token)
                    self.assertEqual(status, 200)
                    self.assertEqual(ssids["items"][0]["ssid_name"], ssid_name)
                finally:
                    server.shutdown()
                    thread.join(timeout=2)
                    server.server_close()

        for name in (site_name, device_name, ssid_name):
            self.assertNotIn(name, request_log.getvalue())

    @staticmethod
    def _request(port: int, path: str, token: str | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", port, timeout=2)
        headers = {"Authorization": "Bearer " + token} if token else {}
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        return response.status, body


if __name__ == "__main__":
    unittest.main()
