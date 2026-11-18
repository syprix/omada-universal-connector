from __future__ import annotations

import contextlib
import io
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from tests import live_read_probe


class LiveReadProbeTests(unittest.TestCase):
    def test_ap_selection_requires_explicit_type_and_valid_opaque_ref(self) -> None:
        ap_ref, switch_ref, unknown_ref = "a" * 24, "b" * 24, "c" * 24
        rows = [
            {"device_ref": ap_ref, "device_type": " Access Point ", "name": "private"},
            {"device_ref": switch_ref, "device_type": "switch"},
            {"device_ref": unknown_ref, "name": "missing type"},
            {"device_ref": "bad-ref", "device_type": "ap"},
        ]
        self.assertEqual(live_read_probe._ap_candidates(rows), [ap_ref])

    def test_counts_summarize_only_cardinality(self) -> None:
        self.assertEqual(live_read_probe._safe_result_count("site_topology", {
            "nodes": [{"device_ref": "private-ref"}], "edges": [{"from_device_ref": "secret"}]
        }), 1)
        self.assertEqual(live_read_probe._safe_result_count("ap_mesh_statistics", {
            "data": {"child_aps_count": 2, "candidate_parents_count": 3,
                     "omitted_field_count": 0,
                     "wireless_uplink": {"ip": "192.0.2.1"}}
        }), 5)
        self.assertEqual(live_read_probe._safe_result_count("ap_health", {
            "data": {"cpu": {"average": 10}, "private": "discarded"}
        }), 2)
        self.assertIsNone(live_read_probe._safe_result_count("site_topology", {"nodes": []}))
        self.assertIsNone(live_read_probe._safe_result_count("ap_mesh_statistics", {
            "data": {"child_aps_count": "unknown", "omitted_field_count": 0}
        }))
        self.assertIsNone(live_read_probe._safe_result_count("ap_health", {"data": None}))

    def test_request_refuses_redirect_without_following_or_sending_token_again(self) -> None:
        received: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.path)
                if self.path == "/start":
                    self.send_response(302)
                    self.send_header("Location", "/redirect-target")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')

            def log_message(self, format, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {
                "http_proxy": "http://proxy.invalid:3128",
                "HTTP_PROXY": "http://proxy.invalid:3128",
                "https_proxy": "http://proxy.invalid:3128",
                "HTTPS_PROXY": "http://proxy.invalid:3128",
                "ALL_PROXY": "http://proxy.invalid:3128",
                "no_proxy": "",
                "NO_PROXY": "",
            }, clear=False):
                status, payload, error = live_read_probe._request(
                    f"http://127.0.0.1:{server.server_port}", "do-not-forward",
                    "/start", live_read_probe._RequestBudget())
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
        self.assertEqual(status, 302)
        self.assertIsNone(payload)
        self.assertIsNotNone(error)
        self.assertEqual(received, ["/start"])

    def test_extended_opt_in_probes_only_inventory_aps_and_redacts_output(self) -> None:
        site_ref, ap_ref, switch_ref = "1" * 24, "2" * 24, "3" * 24
        calls: list[str] = []

        def request(base, token, path, budget=None):
            self.assertEqual(base, "http://127.0.0.1:8080")
            self.assertEqual(token, "caller-token-value")
            calls.append(path)
            if path == "/v1/sites":
                return 200, {"status": "ok", "items": [{"site_ref": site_ref}]}, None
            if path.endswith("/devices"):
                return 200, {"status": "ok", "items": [
                    {"device_ref": ap_ref, "device_type": "ap"},
                    {"device_ref": switch_ref, "device_type": "switch"}]}, None
            if path.endswith("/clients"):
                return 200, {"status": "ok", "items": []}, None
            if path.endswith("/topology"):
                return 200, {"status": "ok", "nodes": [{"device_ref": "private-topology-ref"}],
                             "edges": [],
                             "private": "controller-name"}, None
            if path.endswith("/health"):
                return 200, {"status": "ok", "data": {"cpu": {"average": 12},
                             "private": "health-text"}}, None
            if path.endswith("/mesh"):
                return 200, {"status": "ok", "data": {"child_aps_count": 2,
                             "omitted_field_count": 0, "private": "mesh-name"}}, None
            return 200, {"status": "ok", "data": {}}, None

        with tempfile.TemporaryDirectory() as directory:
            token_file = os.path.join(directory, "caller-token")
            with open(token_file, "w", encoding="utf-8") as handle:
                handle.write("caller-token-value")
            output = io.StringIO()
            with patch.dict(os.environ, {
                "OMADA_CONNECTOR_TOKEN_FILE": token_file,
                "CONNECTOR_BASE_URL": "http://127.0.0.1:8080",
                "OMADA_PROBE_EXTENDED_READS": "1",
            }, clear=False), patch.object(live_read_probe, "_request", side_effect=request), \
                    contextlib.redirect_stdout(output):
                result = live_read_probe.main()

        self.assertEqual(result, 0)
        self.assertIn(f"/v1/sites/{site_ref}/topology", calls)
        self.assertIn(f"/v1/sites/{site_ref}/aps/{ap_ref}/health", calls)
        self.assertIn(f"/v1/sites/{site_ref}/aps/{ap_ref}/mesh", calls)
        self.assertFalse(any(switch_ref in path for path in calls))
        rendered = output.getvalue()
        for private_value in (site_ref, ap_ref, switch_ref, "private-topology-ref",
                              "controller-name", "health-text", "mesh-name"):
            self.assertNotIn(private_value, rendered)
        self.assertIn("site_topology status=200 count=1", rendered)
        self.assertIn("ap_health status=200 count=2", rendered)
        self.assertIn("ap_mesh_statistics status=200 count=2", rendered)

    def test_malformed_successful_extended_response_fails_probe(self) -> None:
        site_ref, ap_ref = "4" * 24, "5" * 24

        def request(base, token, path, budget=None):
            if path == "/v1/sites":
                return 200, {"status": "ok", "items": [{"site_ref": site_ref}]}, None
            if path.endswith("/devices"):
                return 200, {"status": "ok", "items": [
                    {"device_ref": ap_ref, "device_type": "ap"}]}, None
            if path.endswith("/clients"):
                return 200, {"status": "ok", "items": []}, None
            if path.endswith("/topology"):
                return 200, {"status": "ok", "nodes": [], "edges": []}, None
            if path.endswith("/health"):
                return 200, {"status": "ok", "data": None}, None
            if path.endswith("/mesh"):
                return 200, {"status": "ok", "data": {"omitted_field_count": 0}}, None
            return 200, {"status": "ok", "data": {}}, None

        with tempfile.TemporaryDirectory() as directory:
            token_file = os.path.join(directory, "caller-token")
            with open(token_file, "w", encoding="utf-8") as handle:
                handle.write("caller-token-value")
            output = io.StringIO()
            with patch.dict(os.environ, {
                "OMADA_CONNECTOR_TOKEN_FILE": token_file,
                "CONNECTOR_BASE_URL": "http://127.0.0.1:8080",
                "OMADA_PROBE_EXTENDED_READS": "1",
            }, clear=False), patch.object(live_read_probe, "_request", side_effect=request), \
                    contextlib.redirect_stdout(output):
                result = live_read_probe.main()
        self.assertEqual(result, 1)
        self.assertIn("ap_health status=200 error=response_invalid", output.getvalue())


if __name__ == "__main__":
    unittest.main()
