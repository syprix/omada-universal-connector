from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from io import StringIO
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE = "a" * 24
GATEWAY = "b" * 24
OTHER = "c" * 24


class RawResponse:
    def __init__(self, body: bytes) -> None:
        self.body, self.status = body, 200

    def read(self, _limit: int = -1) -> bytes:
        return self.body

    def getheader(self, _name: str, default: str = "") -> str:
        return "application/json"


class RawConnection:
    def __init__(self, body: bytes) -> None:
        self.response = RawResponse(body)

    def request(self, *_args, **_kwargs) -> None:
        pass

    def getresponse(self) -> RawResponse:
        return self.response

    def close(self) -> None:
        pass


class FakeGatewayClient:
    def __init__(self) -> None:
        self.calls = []

    def read_gateway_wan_health(self, site_ref: str, device_ref: str):
        self.calls.append((site_ref, device_ref))
        return {"status": "ok", "resource": "gateway_wan_health",
                "device_ref": device_ref, "wan_details": [], "count": 0,
                "partial": False, "omitted_field_count": 0}


class WanHealthIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE] = "site_known"
        self.client._gateway_macs_by_site_ref[SITE] = {GATEWAY: "00:11:22:33:44:55"}

    def test_inventory_gateway_ref_fixed_get_projection_and_capability(self) -> None:
        calls = []
        payload = {"result": {"wanDetails": [
            {"port": 1, "speed": 1000, "loss": 0.2,
             "name": "private", "ip": "192.0.2.1", "mac": "AA:BB"}
        ]}}
        def request(method, path, **_kwargs):
            calls.append((method, path))
            return payload

        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.read_gateway_wan_health(SITE, GATEWAY)
        self.assertEqual(calls, [("GET", "/openapi/v1/ctrl/sites/site_known/health/gateways/00:11:22:33:44:55/wans/details")])
        self.assertEqual(result["wan_details"], [{"port": 1, "speed_code": 1000,
                                                   "loss": 0.2, "omitted_field_count": 3}])
        self.assertNotIn("private", str(result))
        evidence = next(row for row in self.client.capabilities()["items"]
                        if row["operation"] == "gateway_wan_health")["runtime_evidence"]
        self.assertEqual(evidence[0]["target_ref"], SITE + ":" + GATEWAY)

    def test_unknown_site_or_gateway_ref_is_rejected_before_request(self) -> None:
        with patch.object(self.client, "_request_json", side_effect=AssertionError("must not request")):
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                self.client.read_gateway_wan_health(OTHER, GATEWAY)
            with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
                self.client.read_gateway_wan_health(SITE, OTHER)

    def test_fixed_get_allowlist_rejects_other_path_and_method(self) -> None:
        with patch.object(self.client, "_connection", side_effect=AssertionError("network must not start")):
            for method, path in (
                ("POST", "/openapi/v1/ctrl/sites/site_known/health/gateways/00:11:22:33:44:55/wans/details"),
                ("GET", "/openapi/v1/ctrl/sites/site_known/health/gateways/anything/wans/details"),
                ("GET", "/openapi/v1/other/sites/site_known/health/gateways/00:11:22:33:44:55/wans/details"),
            ):
                with self.subTest(method=method, path=path), \
                        self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                    self.client._request_json(method, path)

    def test_http_route_auth_dispatch_and_log_scrubbing(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        token_path = os.path.join(tempdir.name, "token")
        with open(token_path, "w", encoding="ascii") as stream:
            stream.write("x" * 40)
        fake = FakeGatewayClient()
        server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)
        env = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": token_path})
        env.start()
        self.addCleanup(env.stop)
        client_patch = patch.object(main, "_openapi_client", return_value=fake)
        client_patch.start()
        self.addCleanup(client_patch.stop)

        captured = StringIO()
        with redirect_stdout(captured):
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            connection.request("GET", f"/v1/sites/{SITE}/gateways/{GATEWAY}/wan-health")
            response = connection.getresponse()
            self.assertEqual(response.status, 401)
            response.read()
            connection.close()

            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            connection.request("GET", f"/v1/sites/{SITE}/gateways/{GATEWAY}/wan-health",
                               headers={"Authorization": "Bearer " + "x" * 40})
            response = connection.getresponse()
            body = json.loads(response.read())
            self.assertEqual(response.status, 200)
            connection.close()

            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "omada_gateway_wan_health",
                                  "arguments": {"site_ref": SITE,
                                                "device_ref": GATEWAY}}}
            connection.request("POST", "/mcp", body=json.dumps(request), headers={
                "Authorization": "Bearer " + "x" * 40,
                "Content-Type": "application/json",
            })
            response = connection.getresponse()
            mcp_body = json.loads(response.read())
            self.assertEqual(response.status, 200)
            connection.close()
        self.assertEqual(fake.calls, [(SITE, GATEWAY), (SITE, GATEWAY)])
        self.assertEqual(body["resource"], "gateway_wan_health")
        self.assertEqual(mcp_body["result"]["structuredContent"]["resource"],
                         "gateway_wan_health")
        self.assertFalse(mcp_body["result"]["isError"])
        self.assertNotIn(SITE, captured.getvalue())
        self.assertNotIn(GATEWAY, captured.getvalue())
        self.assertIn("/v1/sites/<ref>/gateways/<ref>/wan-health", captured.getvalue())

    def test_http_route_rejects_malformed_paths_without_dispatch(self) -> None:
        fake = FakeGatewayClient()
        with patch.object(main, "_openapi_client", return_value=fake):
            server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                connection.request("GET", f"/v1/sites/{SITE}/gateways/not-a-ref/wan-health")
                response = connection.getresponse()
                self.assertEqual(response.status, 404)
                response.read()
                connection.close()
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
        self.assertEqual(fake.calls, [])

    def test_https_json_parser_rejects_huge_integer_nan_and_infinity(self) -> None:
        valid_path = "/openapi/v1/ctrl/sites/site_known/setting/service/dns-cache"
        for raw in (b'{"result":' + b"9" * 5000 + b"}",
                    b'{"result":NaN}', b'{"result":Infinity}', b'{"result":1e999}'):
            with self.subTest(sample=raw[:24]):
                with patch.object(self.client, "_connection", return_value=RawConnection(raw)):
                    with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                        self.client._request_json("GET", valid_path, token="token")


if __name__ == "__main__":
    unittest.main()
