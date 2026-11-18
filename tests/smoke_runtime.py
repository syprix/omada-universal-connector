from __future__ import annotations

import hashlib
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class MockController(BaseHTTPRequestHandler):
    mode = "valid"

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/api/info":
            self.send_error(404)
            return
        if type(self).mode == "valid":
            payload = {"result": {"omadacId": "runtime-controller-id", "version": "5.15.8"}}
        else:
            payload = {"result": {"version": "5.15.8"}}
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        self.send_error(405)

    def log_message(self, *_args: object) -> None:
        return


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_tls_controller(tempdir: str) -> tuple[ThreadingHTTPServer, str]:
    key = os.path.join(tempdir, "key.pem")
    cert = os.path.join(tempdir, "cert.pem")
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
        der = ssl.PEM_cert_to_DER_cert(handle.read())
    pin = hashlib.sha256(der).hexdigest()
    controller = ThreadingHTTPServer(("127.0.0.1", 0), MockController)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    controller.socket = context.wrap_socket(controller.socket, server_side=True)
    threading.Thread(target=controller.serve_forever, daemon=True).start()
    return controller, pin


def get(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=2) as response:
        return json.loads(response.read())


with tempfile.TemporaryDirectory() as tempdir:
    controller, pin = start_tls_controller(tempdir)
    port = free_port()
    env = os.environ | {
        "LISTEN_HOST": "127.0.0.1",
        "LISTEN_PORT": str(port),
        "OMADA_BASE_URL": f"https://127.0.0.1:{controller.server_port}",
        "OMADA_CERT_SHA256": pin,
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        for _ in range(30):
            try:
                state = get(f"http://127.0.0.1:{port}/state")
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("connector did not start")
        result = get(f"http://127.0.0.1:{port}/omada/controller-info")
        assert state["implemented_query"] == "/api/info"
        assert result["status"] == "verified"
        assert result["resource"] == "controller_info"
        assert result["path"] == "/api/info"
        assert result["data"]["controller_id_present"] is True

        # The same fixed route reports an unreachable controller as a bounded
        # 502 error; no credentials, cookies, or response body are exposed.
        unreachable_env = env | {"OMADA_BASE_URL": "https://127.0.0.1:1"}
        process.terminate()
        process.wait(timeout=5)
        process = subprocess.Popen(
            [sys.executable, "-m", "app.main"],
            env=unreachable_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for _ in range(30):
            try:
                get(f"http://127.0.0.1:{port}/state")
                break
            except Exception:
                time.sleep(0.1)
        try:
            get(f"http://127.0.0.1:{port}/omada/controller-info")
            raise AssertionError("unreachable controller unexpectedly succeeded")
        except urllib.error.HTTPError as exc:
            assert exc.code == 502
            error = json.loads(exc.read())
            assert error == {"error": "controller_unreachable", "status": "error"}
        print(json.dumps({"state": state, "positive": result, "unreachable": "controller_unreachable"}, sort_keys=True))
    finally:
        process.terminate()
        process.wait(timeout=5)
        controller.shutdown()
        controller.server_close()
