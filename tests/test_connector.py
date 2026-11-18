from __future__ import annotations

import hashlib
import json
import os
import ssl
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from app.main import Handler
from app.omada import OmadaClient, OmadaConfig, OmadaError


class ControllerInfoHandler(BaseHTTPRequestHandler):
    response_mode = "valid"
    request_methods: list[str] = []
    request_paths: list[str] = []

    def do_GET(self) -> None:  # noqa: N802
        type(self).request_methods.append("GET")
        type(self).request_paths.append(self.path)
        if self.path != "/api/info":
            self.send_error(404)
            return
        if type(self).response_mode == "valid":
            payload = {"result": {"omadacId": "controller-secret-ish-id", "version": "5.15.8"}}
        elif type(self).response_mode == "incomplete":
            payload = {"result": {"version": "5.15.8"}}
        else:
            payload = {"status": "ok"}
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        type(self).request_methods.append("POST")
        self.send_error(405)

    def log_message(self, *_args: object) -> None:
        return


class ControllerInfoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        key = os.path.join(cls.tempdir.name, "key.pem")
        cert = os.path.join(cls.tempdir.name, "cert.pem")
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", key, "-out", cert, "-subj", "/CN=localhost", "-days", "1",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with open(cert, encoding="ascii") as handle:
            cls.cert_der = ssl.PEM_cert_to_DER_cert(handle.read())
        cls.cert_pin = hashlib.sha256(cls.cert_der).hexdigest()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ControllerInfoHandler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        cls.httpd.socket = context.wrap_socket(cls.httpd.socket, server_side=True)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"https://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.thread.join(timeout=2)
        cls.tempdir.cleanup()

    def setUp(self) -> None:
        ControllerInfoHandler.response_mode = "valid"
        ControllerInfoHandler.request_methods.clear()
        ControllerInfoHandler.request_paths.clear()

    def config(self, **overrides: object) -> OmadaConfig:
        values = {
            "base_url": self.url,
            "timeout_seconds": 1.0,
            "cert_sha256": self.cert_pin,
        }
        values.update(overrides)
        return OmadaConfig(**values)

    def test_controller_info_success_is_redacted_and_verified(self) -> None:
        result = OmadaClient(self.config()).read_controller_info()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["resource"], "controller_info")
        self.assertEqual(result["path"], "/api/info")
        self.assertTrue(result["data"]["controller_id_present"])
        self.assertEqual(result["data"]["version"], "5.15.8")
        self.assertNotIn("controller-secret-ish-id", json.dumps(result))
        self.assertEqual(ControllerInfoHandler.request_methods, ["GET"])
        self.assertEqual(ControllerInfoHandler.request_paths, ["/api/info"])

    def test_direct_config_normalizes_uppercase_certificate_pin(self) -> None:
        config = self.config(cert_sha256=self.cert_pin.upper())
        self.assertEqual(config.cert_sha256, self.cert_pin)
        result = OmadaClient(config).read_controller_info()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(ControllerInfoHandler.request_paths, ["/api/info"])

    def test_direct_config_rejects_malformed_certificate_pins(self) -> None:
        for pin in ("not-a-pin", "g" * 64, "a" * 63):
            with self.subTest(pin_length=len(pin)), self.assertRaises(OmadaError) as ctx:
                self.config(cert_sha256=pin)
            self.assertEqual(ctx.exception.code, "controller_certificate_pin_invalid")

    def test_http_is_rejected_without_any_request(self) -> None:
        with self.assertRaises(OmadaError) as ctx:
            OmadaClient(OmadaConfig("http://127.0.0.1:80", cert_sha256=self.cert_pin)).read_controller_info()
        self.assertEqual(ctx.exception.code, "controller_https_required")

    def test_pin_is_required(self) -> None:
        with patch("app.omada.http.client.HTTPSConnection") as connection:
            with self.assertRaises(OmadaError) as ctx:
                OmadaClient(self.config(cert_sha256="")).read_controller_info()
            connection.assert_not_called()
        self.assertEqual(ctx.exception.code, "controller_certificate_pin_required")

    def test_http_200_without_expected_fields_is_not_verified(self) -> None:
        ControllerInfoHandler.response_mode = "incomplete"
        with self.assertRaises(OmadaError) as ctx:
            OmadaClient(self.config()).read_controller_info()
        self.assertEqual(ctx.exception.code, "controller_info_incomplete")

    def test_unreachable_controller_is_redacted(self) -> None:
        with self.assertRaises(OmadaError) as ctx:
            OmadaClient(self.config(base_url="https://127.0.0.1:1")).read_controller_info()
        self.assertEqual(ctx.exception.code, "controller_unreachable")

    def test_authenticated_phase_two_route_is_not_exposed(self) -> None:
        self.assertEqual(OmadaClient.FIXED_PATH, "/api/info")
        self.assertEqual(Handler.server_version, "omada-universal-connector/0.3.0-dev")


if __name__ == "__main__":
    unittest.main()
