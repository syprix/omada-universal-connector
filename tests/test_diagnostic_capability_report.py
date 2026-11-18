from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main
from app.diagnostic_capability_report import (
    WORKFLOWS, project_diagnostic_capability_report,
)
from app.openapi import OmadaOpenApiClient


class DiagnosticCapabilityReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = OmadaOpenApiClient.capability_catalog()
        self.items = {item["operation"]: item for item in self.catalog["items"]}

    def test_unobserved_workflows_are_reported_as_documented_not_live(self) -> None:
        result = project_diagnostic_capability_report(self.catalog)
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["catalog_complete"])
        self.assertEqual(result["network_requests_made"], 0)
        self.assertEqual(len(result["workflows"]), 8)
        for workflow in result["workflows"]:
            self.assertEqual(workflow["status"], "documented")
            self.assertEqual(workflow["operation_status_counts"]["documented"],
                             workflow["required_operation_count"])
            self.assertEqual(workflow["operation_status_counts"]["observed"], 0)

    def test_one_failure_and_one_live_success_have_distinct_statuses(self) -> None:
        self.items["wifi_health"]["runtime_evidence"] = [{
            "result": "failure", "controller_response_observed": True,
            "failure_class": "permission_denied",
            "error_code": "openapi_permission_denied", "target_ref": "a" * 24,
            "recorded_at": "2026-11-18T10:00:00+00:00",
        }]
        self.items["site_dashboard_channels"]["runtime_evidence"] = [{
            "result": "success", "controller_response_observed": True,
            "response_shape_state": "response_shape_supported",
            "target_ref": "b" * 24,
            "recorded_at": "2026-11-18T10:01:00+00:00",
        }]
        result = project_diagnostic_capability_report(self.catalog)
        workflow = next(item for item in result["workflows"] if item["id"] == "site_wlan")
        self.assertEqual(workflow["status"], "failed")
        entries = {item["operation"]: item for item in workflow["operations"]}
        self.assertEqual(entries["wifi_health"]["status"], "failed")
        self.assertEqual(entries["wifi_health"]["failure_classes"], {"permission_denied": 1})
        self.assertEqual(entries["site_dashboard_channels"]["status"], "observed")
        self.assertEqual(entries["site_dashboard_channels"]["observed_success_count"], 1)
        rendered = json.dumps(result)
        self.assertNotIn("a" * 24, rendered)
        self.assertNotIn("b" * 24, rendered)

    def test_mixed_incomplete_evidence_and_missing_catalog_rows_remain_unknown(self) -> None:
        self.items["wifi_health"]["runtime_evidence"] = [{
            "result": "success", "controller_response_observed": False,
            "response_shape_state": "unknown",
        }]
        self.catalog["items"] = [item for item in self.catalog["items"]
                                  if item["operation"] != "site_dashboard_channels"]
        result = project_diagnostic_capability_report(self.catalog)
        workflow = next(item for item in result["workflows"] if item["id"] == "site_wlan")
        self.assertEqual(workflow["status"], "unknown")
        entries = {item["operation"]: item for item in workflow["operations"]}
        self.assertEqual(entries["wifi_health"]["status"], "unknown")
        self.assertEqual(entries["site_dashboard_channels"]["status"], "unknown")

    def test_workflow_definitions_match_checked_operation_evidence_sources(self) -> None:
        evidence = json.loads((Path(__file__).resolve().parents[1] /
                               "docs/OPERATION_EVIDENCE.json").read_text(encoding="utf-8"))
        source_counts: dict[str, int] = {}
        for operation in evidence["operations"]:
            for operation_id in operation["operation_ids"]:
                source_counts[operation_id] = max(
                    source_counts.get(operation_id, 0), len(operation["documented_in"]))
        report = project_diagnostic_capability_report(self.catalog)
        for workflow in report["workflows"]:
            for operation in workflow["operations"]:
                self.assertEqual(operation["documented_source_count"],
                                 source_counts.get(operation["operation"], 0),
                                 operation["operation"])

    def test_http_and_mcp_expose_the_same_catalog_projection_without_probing(self) -> None:
        class Fake:
            calls = 0

            def capabilities(self):
                self.calls += 1
                return OmadaOpenApiClient.capability_catalog()

        with tempfile.TemporaryDirectory() as directory:
            token = "connector-caller-token-0123456789abcdef0123456789"
            token_path = Path(directory) / "caller-token"
            token_path.write_text(token, encoding="ascii")
            fake = Fake()
            with patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": str(token_path)}), \
                    patch.object(main, "_openapi_client", return_value=fake):
                server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    connection.request("GET", "/v1/diagnostic-capabilities")
                    unauthorized = connection.getresponse()
                    self.assertEqual(unauthorized.status, 401)
                    unauthorized.read()
                    connection.close()

                    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    connection.request("GET", "/v1/diagnostic-capabilities",
                                       headers={"Authorization": "Bearer " + token})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    http_result = json.loads(response.read())
                    connection.close()

                    rpc = {"jsonrpc": "2.0", "id": "workflow-capabilities",
                           "method": "tools/call", "params": {
                               "name": "omada_diagnostic_capability_summary",
                               "arguments": {}}}
                    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    connection.request("POST", "/mcp", json.dumps(rpc), headers={
                        "Authorization": "Bearer " + token,
                        "Content-Type": "application/json",
                    })
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    mcp_result = json.loads(response.read())["result"]["structuredContent"]
                    connection.close()
                    self.assertEqual(http_result, mcp_result)
                    self.assertEqual(fake.calls, 2)
                    self.assertEqual(http_result["network_requests_made"], 0)
                finally:
                    server.shutdown()
                    thread.join(timeout=2)
                    server.server_close()

    def test_invalid_catalog_fails_closed(self) -> None:
        self.assertEqual(project_diagnostic_capability_report(None), {
            "status": "error", "error": "capability_catalog_invalid"})
        self.assertTrue(WORKFLOWS)


if __name__ == "__main__":
    unittest.main()
