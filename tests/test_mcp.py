from __future__ import annotations

import unittest

from app.mcp import McpRequestError, TOOLS_PER_PAGE, handle_mcp_request


class Operation:
    def __init__(self, operation_id: str, path: str):
        self.operation_id = operation_id
        self.public_method = self.upstream_method = "GET"
        self.public_template = self.upstream_template = path


class Registry:
    def __init__(self, operations):
        self.entries = tuple(operations)
        self.by_id = {op.operation_id: op for op in operations}

    def get(self, operation_id):
        if operation_id not in self.by_id:
            raise ValueError("unknown")
        return self.by_id[operation_id]


class McpTests(unittest.TestCase):
    def setUp(self):
        self.registry = Registry([
            Operation("sites", "/v1/sites"),
            Operation("devices", "/v1/sites/{site_ref}/devices"),
            Operation("ap_scan_status", "/v1/sites/{site_ref}/aps/{device_ref}/scan-status"),
            Operation("ap_speed_test_results", "/v1/sites/{site_ref}/aps/{device_ref}/speed-test-results"),
            Operation("ap_wifi_interference", "/v1/sites/{site_ref}/aps/{device_ref}/wifi-neighbors"),
            Operation("gateway_health", "/v1/sites/{site_ref}/gateways/{gateway_ref}/health"),
            Operation("switch_port_status", "/v1/sites/{site_ref}/switches/{switch_ref}/ports/{port}/status"),
        ])

    def call(self, request, invoke=lambda operation_id, args: {"status": "ok"}):
        return handle_mcp_request(request, None, self.registry, invoke)

    def test_initialize_and_notification(self):
        initialized = self.call({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                 "params": {"protocolVersion": "2025-03-26"}})
        self.assertEqual(initialized["result"]["protocolVersion"], "2025-03-26")
        self.assertIsNone(self.call({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_list_tools_and_fixed_read_only_annotations(self):
        request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        result = self.call(request)["result"]
        all_tools = list(result["tools"])
        while "nextCursor" in result:
            result = self.call({**request, "params": {"cursor": result["nextCursor"]}})["result"]
            all_tools.extend(result["tools"])
        devices = next(item for item in all_tools if item["name"] == "omada_devices")
        self.assertTrue(devices["annotations"]["readOnlyHint"])
        self.assertFalse(devices["annotations"]["destructiveHint"])
        self.assertEqual(devices["inputSchema"]["required"], ["site_ref"])
        switch_anomalies = next(item for item in all_tools
                                if item["name"] == "omada_site_switch_port_anomaly_summary")
        self.assertTrue(switch_anomalies["annotations"]["readOnlyHint"])
        self.assertFalse(switch_anomalies["annotations"]["destructiveHint"])
        self.assertIn("does not provide drop counts", switch_anomalies["description"])
        self.assertIn("same portStatus fields and int64 txErrors/rxErrors",
                      switch_anomalies["description"])
        self.assertNotIn("only in the ER7212PC export", switch_anomalies["description"])
        outage_overlap = next(item for item in all_tools
                              if item["name"] == "omada_site_client_outage_overlap_summary")
        self.assertTrue(outage_overlap["annotations"]["readOnlyHint"])
        self.assertFalse(outage_overlap["annotations"]["destructiveHint"])
        self.assertEqual(outage_overlap["inputSchema"]["properties"]["client_refs"]["minItems"], 2)
        self.assertEqual(outage_overlap["inputSchema"]["properties"]["client_refs"]["maxItems"], 16)
        roaming_backtrack = next(item for item in all_tools
                                 if item["name"] == "omada_site_client_roaming_backtrack_summary")
        self.assertTrue(roaming_backtrack["annotations"]["readOnlyHint"])
        self.assertFalse(roaming_backtrack["annotations"]["destructiveHint"])
        self.assertEqual(roaming_backtrack["inputSchema"]["properties"]["client_refs"]["minItems"], 1)
        self.assertEqual(roaming_backtrack["inputSchema"]["properties"]["client_refs"]["maxItems"], 16)
        ap_uplink_path = next(item for item in all_tools
                              if item["name"] == "omada_site_ap_uplink_path_summary")
        self.assertTrue(ap_uplink_path["annotations"]["readOnlyHint"])
        self.assertFalse(ap_uplink_path["annotations"]["destructiveHint"])
        self.assertEqual(ap_uplink_path["inputSchema"]["properties"]["device_refs"]["minItems"], 1)
        self.assertEqual(ap_uplink_path["inputSchema"]["properties"]["device_refs"]["maxItems"], 16)
        diagnosis = next(item for item in all_tools
                         if item["name"] == "omada_wifi_diagnose_site")
        self.assertTrue(diagnosis["annotations"]["readOnlyHint"])
        self.assertIn("No RF scan", diagnosis["description"])
        ap_diagnosis = next(item for item in all_tools
                            if item["name"] == "omada_wifi_diagnose_ap")
        self.assertTrue(ap_diagnosis["annotations"]["readOnlyHint"])
        self.assertEqual(ap_diagnosis["inputSchema"]["required"], ["site_ref", "ap_ref"])
        client_diagnosis = next(item for item in all_tools
                                if item["name"] == "omada_wifi_diagnose_client")
        self.assertTrue(client_diagnosis["annotations"]["readOnlyHint"])
        self.assertEqual(client_diagnosis["inputSchema"]["required"],
                         ["site_ref", "client_ref"])
        journal_summary = next(item for item in all_tools
                               if item["name"] == "omada_change_journal_summary")
        self.assertTrue(journal_summary["annotations"]["readOnlyHint"])
        self.assertFalse(journal_summary["annotations"]["destructiveHint"])
        comparison = next(item for item in all_tools
                          if item["name"] == "omada_wifi_compare_aps")
        self.assertTrue(comparison["annotations"]["readOnlyHint"])
        self.assertEqual(comparison["inputSchema"]["required"],
                         ["site_ref", "ap_ref_a", "ap_ref_b"])
        network = next(item for item in all_tools
                       if item["name"] == "omada_network_diagnose_gateway")
        self.assertTrue(network["annotations"]["readOnlyHint"])
        self.assertEqual(network["inputSchema"]["required"], ["site_ref", "gateway_ref"])
        ssid_summary = next(item for item in all_tools
                            if item["name"] == "omada_ssid_network_summary")
        self.assertTrue(ssid_summary["annotations"]["readOnlyHint"])
        self.assertEqual(ssid_summary["inputSchema"]["required"], ["site_ref"])
        switch_network = next(item for item in all_tools
                              if item["name"] == "omada_network_diagnose_switch")
        self.assertTrue(switch_network["annotations"]["readOnlyHint"])
        self.assertEqual(switch_network["inputSchema"]["required"], ["site_ref", "switch_ref"])
        capability = next(item for item in all_tools
                          if item["name"] == "omada_capability_summary")
        self.assertTrue(capability["annotations"]["readOnlyHint"])
        self.assertEqual(capability["inputSchema"]["additionalProperties"], False)
        self.assertIn("without contacting the controller", capability["description"])
        ap_scan = next(item for item in all_tools
                       if item["name"] == "omada_ap_scan_status")
        self.assertEqual(ap_scan["inputSchema"]["required"], ["site_ref", "device_ref"])
        neighbors = next(item for item in all_tools
                         if item["name"] == "omada_ap_wifi_interference")
        self.assertEqual(neighbors["inputSchema"]["required"], ["site_ref", "device_ref"])
        speed_test = next(item for item in all_tools
                          if item["name"] == "omada_ap_speed_test_results")
        self.assertEqual(speed_test["inputSchema"]["required"], ["site_ref", "device_ref"])
        cable_test = next(item for item in all_tools
                          if item["name"] == "omada_switch_cable_test")
        self.assertTrue(cable_test["annotations"]["destructiveHint"])
        self.assertIn("exact short-lived operator approval", cable_test["description"])

    def test_switch_cable_test_mcp_actions_validate_and_dispatch(self):
        seen = []
        def action(name, args):
            seen.append((name, args))
            return {"status": "ok", "action": name}
        preview = {"action": "preview", "site_ref": "a" * 24, "switch_ref": "b" * 24,
                   "port": 3, "disruption_confirmed": True}
        result = handle_mcp_request(
            {"jsonrpc": "2.0", "id": 70, "method": "tools/call", "params": {
                "name": "omada_switch_cable_test", "arguments": preview}},
            None, self.registry, lambda op, args: {"status": "ok"}, invoke_action=action)
        self.assertEqual(seen, [("preview", preview)])
        self.assertFalse(result["result"]["isError"])
        rejected = handle_mcp_request(
            {"jsonrpc": "2.0", "id": 71, "method": "tools/call", "params": {
                "name": "omada_switch_cable_test", "arguments": {
                    "action": "apply", "plan_id": "c" * 48, "approval": {}}}},
            None, self.registry, lambda op, args: {"status": "ok"}, invoke_action=action)
        self.assertEqual(rejected["error"]["message"], "arguments_invalid")
        self.assertEqual(len(seen), 1)

    def test_ap_wifi_neighbors_tool_accepts_only_opaque_inventory_refs(self):
        seen = []
        args = {"site_ref": "a" * 24, "device_ref": "b" * 24}
        result = self.call({"jsonrpc": "2.0", "id": 19, "method": "tools/call",
                            "params": {"name": "omada_ap_wifi_interference", "arguments": args}},
                           lambda op, values: seen.append((op, values)) or {"status": "ok"})
        self.assertFalse(result["result"]["isError"])
        self.assertEqual(seen, [("ap_wifi_interference", args)])

    def test_gateway_health_tool_accepts_only_opaque_gateway_reference(self):
        seen = []
        args = {"site_ref": "a" * 24, "gateway_ref": "b" * 24}
        result = self.call({"jsonrpc": "2.0", "id": 28, "method": "tools/call",
                            "params": {"name": "omada_gateway_health", "arguments": args}},
                           lambda op, values: seen.append((op, values)) or {"status": "ok"})
        self.assertFalse(result["result"]["isError"])
        self.assertEqual(seen, [("gateway_health", args)])

    def test_site_ap_uplink_path_dispatch_accepts_only_bounded_ap_refs(self):
        seen = []
        refs = ["b" * 24, "c" * 24]
        args = {"site_ref": "a" * 24, "device_refs": refs}
        result = self.call({"jsonrpc": "2.0", "id": 32, "method": "tools/call",
                            "params": {"name": "omada_site_ap_uplink_path_summary",
                                       "arguments": args}},
                           lambda op, values: seen.append((op, values)) or {"status": "ok"})
        self.assertFalse(result["result"]["isError"])
        self.assertEqual(seen, [("site_ap_uplink_path_summary", {
            "site_ref": args["site_ref"], "device_refs": ",".join(refs)})])

    def test_wifi_diagnose_dispatch_accepts_only_site_reference(self):
        seen = []
        result = self.call({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                            "params": {"name": "omada_wifi_diagnose_site",
                                       "arguments": {"site_ref": "a" * 24}}},
                           lambda op, args: seen.append((op, args)) or {"status": "ok"})
        self.assertEqual(seen, [("wifi_diagnose_site", {"site_ref": "a" * 24})])
        self.assertFalse(result["result"]["isError"])
        for arguments in ({}, {"site_ref": "a" * 24, "scan": True},
                          {"site_ref": "../invalid"}):
            rejected = self.call({"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                                  "params": {"name": "omada_wifi_diagnose_site",
                                             "arguments": arguments}})
            self.assertEqual(rejected["error"]["message"], "arguments_invalid")

    def test_ap_diagnose_dispatch_requires_two_valid_references(self):
        seen = []
        result = self.call({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                            "params": {"name": "omada_wifi_diagnose_ap",
                                       "arguments": {"site_ref": "a" * 24,
                                                     "ap_ref": "b" * 24}}},
                           lambda op, args: seen.append((op, args)) or {"status": "ok"})
        self.assertEqual(seen, [("wifi_diagnose_ap", {"site_ref": "a" * 24,
                                                       "ap_ref": "b" * 24})])
        self.assertFalse(result["result"]["isError"])
        for arguments in ({"site_ref": "a" * 24},
                          {"site_ref": "a" * 24, "ap_ref": "../invalid"},
                          {"site_ref": "a" * 24, "ap_ref": "b" * 24, "scan": True}):
            rejected = self.call({"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                                  "params": {"name": "omada_wifi_diagnose_ap",
                                             "arguments": arguments}})
            self.assertEqual(rejected["error"]["message"], "arguments_invalid")

    def test_client_diagnose_dispatch_requires_site_bound_opaque_refs(self):
        seen = []
        args = {"site_ref": "a" * 24, "client_ref": "b" * 24}
        result = self.call({"jsonrpc": "2.0", "id": 24, "method": "tools/call",
                            "params": {"name": "omada_wifi_diagnose_client",
                                       "arguments": args}},
                           lambda op, values: seen.append((op, values)) or {"status": "ok"})
        self.assertEqual(seen, [("wifi_diagnose_client", args)])
        self.assertFalse(result["result"]["isError"])
        for invalid in ({"site_ref": "a" * 24},
                        {**args, "client_ref": "../invalid"},
                        {**args, "client_ref": "b" * 24, "history": True}):
            rejected = self.call({"jsonrpc": "2.0", "id": 25, "method": "tools/call",
                                  "params": {"name": "omada_wifi_diagnose_client",
                                             "arguments": invalid}})
            self.assertEqual(rejected["error"]["message"], "arguments_invalid")

    def test_ap_comparison_dispatch_requires_two_distinct_site_and_ap_refs(self):
        seen = []
        args = {"site_ref": "a" * 24, "ap_ref_a": "b" * 24, "ap_ref_b": "c" * 24}
        result = self.call({"jsonrpc": "2.0", "id": 12, "method": "tools/call",
                            "params": {"name": "omada_wifi_compare_aps", "arguments": args}},
                           lambda op, values: seen.append((op, values)) or {"status": "ok"})
        self.assertEqual(seen, [("wifi_compare_aps", args)])
        self.assertFalse(result["result"]["isError"])
        for invalid in (
                {"site_ref": "a" * 24, "ap_ref_a": "b" * 24, "ap_ref_b": "b" * 24},
                {"site_ref": "a" * 24, "ap_ref_a": "b" * 24},
                {**args, "scan": True},
                {**args, "ap_ref_b": "../invalid"}):
            rejected = self.call({"jsonrpc": "2.0", "id": 13, "method": "tools/call",
                                  "params": {"name": "omada_wifi_compare_aps",
                                             "arguments": invalid}})
            self.assertEqual(rejected["error"]["message"], "arguments_invalid")

    def test_network_gateway_diagnosis_dispatch_requires_site_bound_refs(self):
        seen = []
        args = {"site_ref": "a" * 24, "gateway_ref": "d" * 24}
        result = self.call({"jsonrpc": "2.0", "id": 22, "method": "tools/call",
                            "params": {"name": "omada_network_diagnose_gateway",
                                       "arguments": args}},
                           lambda op, values: seen.append((op, values)) or {"status": "ok"})
        self.assertEqual(seen, [("network_diagnose_gateway", args)])
        self.assertFalse(result["result"]["isError"])
        for invalid in ({"site_ref": "a" * 24}, {**args, "gateway_ref": "../invalid"},
                        {**args, "write": True}):
            rejected = self.call({"jsonrpc": "2.0", "id": 23, "method": "tools/call",
                                  "params": {"name": "omada_network_diagnose_gateway",
                                             "arguments": invalid}})
            self.assertEqual(rejected["error"]["message"], "arguments_invalid")

    def test_ssid_network_summary_dispatch_accepts_only_site_ref(self):
        seen = []
        args = {"site_ref": "a" * 24}
        result = self.call({"jsonrpc": "2.0", "id": 30, "method": "tools/call",
                            "params": {"name": "omada_ssid_network_summary",
                                       "arguments": args}},
                           lambda operation, values: seen.append((operation, values)) or
                           {"status": "ok"})
        self.assertFalse(result["result"]["isError"])
        self.assertEqual(seen, [("ssid_network_summary", args)])
        rejected = self.call({"jsonrpc": "2.0", "id": 31, "method": "tools/call",
                              "params": {"name": "omada_ssid_network_summary",
                                         "arguments": {**args, "ssid_ref": "b" * 24}}})
        self.assertEqual(rejected["error"]["message"], "arguments_invalid")

    def test_switch_port_index_has_integer_schema_and_strict_bounds(self):
        request = {"jsonrpc": "2.0", "id": 50, "method": "tools/list"}
        page = self.call(request)["result"]
        tools = list(page["tools"])
        while "nextCursor" in page:
            page = self.call({**request, "params": {"cursor": page["nextCursor"]}})["result"]
            tools.extend(page["tools"])
        tool = next(item for item in tools if item["name"] == "omada_switch_port_status")
        port = tool["inputSchema"]["properties"]["port"]
        self.assertEqual((port["type"], port["minimum"], port["maximum"]),
                         ("integer", 0, 4096))
        seen = []
        for value in (0, 4096):
            args = {"site_ref": "a" * 24, "switch_ref": "b" * 24, "port": value}
            result = self.call({"jsonrpc": "2.0", "id": 51, "method": "tools/call",
                                "params": {"name": "omada_switch_port_status",
                                           "arguments": args}},
                               lambda op, values: seen.append((op, values)) or {"status": "ok"})
            self.assertFalse(result["result"]["isError"])
        self.assertEqual([x[1]["port"] for x in seen], ["0", "4096"])
        for value in (-1, 4097, True, 1.5, "24"):
            rejected = self.call({"jsonrpc": "2.0", "id": 52, "method": "tools/call",
                                  "params": {"name": "omada_switch_port_status",
                                             "arguments": {"site_ref": "a" * 24,
                                                           "switch_ref": "b" * 24,
                                                           "port": value}}})
            self.assertEqual(rejected["error"]["message"], "arguments_invalid")

    def test_network_switch_diagnosis_dispatch_requires_opaque_refs(self):
        seen = []
        args = {"site_ref": "a" * 24, "switch_ref": "b" * 24}
        result = self.call({"jsonrpc": "2.0", "id": 26, "method": "tools/call",
                            "params": {"name": "omada_network_diagnose_switch",
                                       "arguments": args}},
                           lambda op, values: seen.append((op, values)) or {"status": "ok"})
        self.assertEqual(seen, [("network_diagnose_switch", args)])
        self.assertFalse(result["result"]["isError"])
        for invalid in ({"site_ref": "a" * 24},
                        {**args, "switch_ref": "../invalid"},
                        {**args, "write": True}):
            rejected = self.call({"jsonrpc": "2.0", "id": 27, "method": "tools/call",
                                  "params": {"name": "omada_network_diagnose_switch",
                                             "arguments": invalid}})
            self.assertEqual(rejected["error"]["message"], "arguments_invalid")

    def test_site_outage_summary_dispatch_requires_integer_window(self):
        seen = []
        args = {"site_ref": "a" * 24, "start_ms": 1_790_000_000_000,
                "end_ms": 1_790_000_030_000}
        result = self.call({"jsonrpc": "2.0", "id": 91, "method": "tools/call",
                            "params": {"name": "omada_site_outage_summary",
                                       "arguments": args}},
                           lambda op, values: seen.append((op, values)) or {"status": "ok"})
        self.assertEqual(seen, [("site_outage_summary", {
            "site_ref": args["site_ref"], "start_ms": str(args["start_ms"]),
            "end_ms": str(args["end_ms"]),
        })])
        self.assertFalse(result["result"]["isError"])
        for invalid in ({**args, "end_ms": True}, {**args, "extra": "no"}):
            rejected = self.call({"jsonrpc": "2.0", "id": 92, "method": "tools/call",
                                  "params": {"name": "omada_site_outage_summary",
                                             "arguments": invalid}})
            self.assertEqual(rejected["error"]["message"], "arguments_invalid")

    def test_ap_scan_status_tool_accepts_only_opaque_inventory_refs(self):
        seen = []
        args = {"site_ref": "a" * 24, "device_ref": "b" * 24}
        result = self.call({"jsonrpc": "2.0", "id": 14, "method": "tools/call",
                            "params": {"name": "omada_ap_scan_status", "arguments": args}},
                           lambda op, values: seen.append((op, values)) or {"status": "ok"})
        self.assertEqual(seen, [("ap_scan_status", args)])
        self.assertFalse(result["result"]["isError"])
        for invalid in ({"site_ref": "a" * 24, "device_ref": "../invalid"},
                        {**args, "path": "https://example.com"}):
            rejected = self.call({"jsonrpc": "2.0", "id": 15, "method": "tools/call",
                                  "params": {"name": "omada_ap_scan_status",
                                             "arguments": invalid}})
            self.assertEqual(rejected["error"]["message"], "arguments_invalid")

    def test_tool_list_is_paginated(self):
        many = Registry([Operation(f"item_{index:02d}", "/v1/sites")
                         for index in range(TOOLS_PER_PAGE + 2)])
        page = handle_mcp_request({"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
                                  None, many, lambda *_: {})["result"]
        self.assertEqual(len(page["tools"]), TOOLS_PER_PAGE)
        self.assertEqual(page["nextCursor"], str(TOOLS_PER_PAGE))

    def test_tool_call_passes_only_valid_opaque_reference(self):
        seen = []
        result = self.call({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                            "params": {"name": "omada_devices",
                                       "arguments": {"site_ref": "a" * 24}}},
                           lambda operation_id, args: seen.append((operation_id, args)) or {"status": "ok"})
        self.assertEqual(seen, [("devices", {"site_ref": "a" * 24})])
        self.assertFalse(result["result"]["isError"])

    def test_capability_summary_is_compact_and_redacts_runtime_references(self):
        catalog = {"status": "ok", "catalog_scope": "instrumented_openapi_operations",
                   "catalog_complete": False, "items": [
            {"operation": "sites", "route": "/v1/sites",
             "support_state": "unknown", "implementation_state": "implemented",
             "controller_response_evidence_count": 1,
             "runtime_evidence": [{"target_ref": "sensitive-ref",
                                    "controller_response_observed": True,
                                    "response_shape_state": "response_shape_supported",
                                    "support_state": "live_verified_supported",
                                    "permission_state": "allowed"}]},
            {"operation": "devices", "route": "/v1/sites/{site_ref}/devices",
             "support_state": "unknown", "implementation_state": "implemented",
             "runtime_evidence": []},
        ]}
        calls = []
        result = self.call({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                            "params": {"name": "omada_capability_summary", "arguments": {}}},
                           lambda operation_id, args: calls.append((operation_id, args)) or catalog)
        summary = result["result"]["structuredContent"]
        self.assertEqual(calls, [("capability_catalog", {})])
        self.assertFalse(summary["catalog_complete"])
        self.assertEqual(summary["operation_count"], 2)
        self.assertEqual(summary["operations_with_runtime_evidence"], 1)
        self.assertEqual(summary["operations_with_controller_responses"], 1)
        self.assertNotIn("sensitive-ref", str(summary))

        detail = self.call({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                            "params": {"name": "omada_capability_summary",
                                       "arguments": {"operation_id": "sites"}}},
                           lambda *_: catalog)["result"]["structuredContent"]
        self.assertEqual(detail["observed_support_states"],
                         {"live_verified_supported": 1})
        self.assertEqual(detail["controller_response_evidence_count"], 1)
        self.assertEqual(detail["observed_response_shape_states"],
                         {"response_shape_supported": 1})
        self.assertNotIn("target_ref", detail)

    def test_capability_summary_rejects_unknown_and_malformed_operation(self):
        catalog = {"status": "ok", "catalog_scope": "instrumented_openapi_operations",
                   "catalog_complete": False, "items": []}
        for arguments in ({"operation_id": "../sites"}, {"extra": True},
                          {"operation_id": "missing"}):
            result = self.call({"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                                "params": {"name": "omada_capability_summary",
                                           "arguments": arguments}}, lambda *_: catalog)
            self.assertIn(result["error"]["message"], {"arguments_invalid", "operation_unknown"})

    def test_rejects_unknown_tools_and_injected_arguments(self):
        for params in (
            {"name": "omada_not_registered", "arguments": {}},
            {"name": "omada_sites", "arguments": {"path": "https://example.com"}},
            {"name": "omada_devices", "arguments": {"site_ref": "../etc/passwd"}},
        ):
            result = self.call({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": params})
            self.assertIn(result["error"]["code"], {-32601, -32602})

    def test_rejects_untrusted_origin(self):
        with self.assertRaises(McpRequestError):
            handle_mcp_request({"jsonrpc": "2.0", "id": 1, "method": "ping"},
                               "https://evil.example", self.registry, lambda *_: {})

    def test_accepts_local_origin_with_client_port(self):
        result = handle_mcp_request({"jsonrpc": "2.0", "id": 1, "method": "ping"},
                                    "http://localhost:3000", self.registry, lambda *_: {})
        self.assertEqual(result["result"], {})

    def test_unknown_method_is_a_json_rpc_error(self):
        result = self.call({"jsonrpc": "2.0", "id": 6, "method": "resources/read"})
        self.assertEqual(result["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
