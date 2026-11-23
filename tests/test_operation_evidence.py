from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.operation_registry import REGISTRY
from tools.full_api_matrix import IMPLEMENTED
from tools.operation_evidence import _canonical, build_report


class OperationEvidenceTests(unittest.TestCase):
    def test_keeps_documentation_mapping_test_references_and_verification_separate(self) -> None:
        catalog = {
            "catalog_scope": "documentation_presence_only_not_runtime_support",
            "operations": [
                {"method": "GET", "path_template": "/openapi/v1/{omadacId}/sites/{siteId}/devices",
                 "documented_in": ["hardware", "edge"]},
                {"method": "PATCH", "path_template": "/openapi/v1/{omadacId}/controller/setting/example",
                 "documented_in": ["hardware"]},
                {"method": "DELETE", "path_template": "/openapi/v1/{omadacId}/sites/{siteId}/widgets/{id}",
                 "documented_in": ["edge"]},
            ],
        }
        entry = SimpleNamespace(
            upstream_method="GET",
            upstream_template="/openapi/v1/{controller_id}/sites/{site_id}/devices",
            operation_id="devices",
            public_template="/v1/sites/{site_ref}/devices",
        )
        with tempfile.TemporaryDirectory() as tmp:
            tests = Path(tmp)
            (tests / "test_devices.py").write_text("self.assertEqual(op, 'devices')\n", encoding="utf-8")
            report = build_report(
                catalog,
                source_map={_canonical("PATCH", "/openapi/v1/{controller_id}/controller/setting/example"):
                            "implemented_controlled_write_unverified_live"},
                registry_entries=(entry,),
                test_root=tests,
                catalog_sha256="fixture-sha",
            )

        self.assertEqual(report["operation_count"], 3)
        self.assertEqual(report["connector_evidence_counts"], {
            "fixed_get_registry_route": 1,
            "manual_source_map_only": 1,
            "not_mapped": 1,
        })
        by_method = {row["method"]: row for row in report["operations"]}
        route, patch, delete = by_method["GET"], by_method["PATCH"], by_method["DELETE"]
        self.assertEqual(route["connector_evidence"], "fixed_get_registry_route")
        self.assertEqual(route["static_test_references"], ["test_devices.py"])
        self.assertEqual(patch["connector_evidence"], "manual_source_map_only")
        self.assertEqual(delete["connector_evidence"], "not_mapped")
        for row in report["operations"]:
            self.assertFalse(row["function_verified"])
            self.assertEqual(row["test_execution"], "not_assessed_by_this_report")
            self.assertEqual(row["live_status"], "not_assessed_by_this_report")

    def test_path_literals_remain_case_sensitive_and_placeholders_align(self) -> None:
        self.assertEqual(
            _canonical("get", "/openapi/v1/{omadacId}/X/{siteId}"),
            ("GET", "/openapi/v1/{}/X/{}"),
        )
        self.assertNotEqual(
            _canonical("GET", "/openapi/v1/sites"),
            _canonical("GET", "/openapi/v1/Sites"),
        )

    def test_records_tests_that_call_the_read_method_without_operation_id_literal(self) -> None:
        catalog = {
            "catalog_scope": "documentation_presence_only_not_runtime_support",
            "operations": [
                {"method": "GET", "path_template": "/openapi/v1/{controller_id}/sites/{site_id}/devices",
                 "documented_in": ["hardware"]},
            ],
        }
        entry = SimpleNamespace(
            upstream_method="GET",
            upstream_template="/openapi/v1/{controller_id}/sites/{site_id}/devices",
            operation_id="devices",
            public_template="/v1/sites/{site_ref}/devices",
        )
        with tempfile.TemporaryDirectory() as tmp:
            tests = Path(tmp)
            (tests / "test_devices_projection.py").write_text(
                "self.client.read_devices(site_ref)\n", encoding="utf-8")
            report = build_report(
                catalog, source_map={}, registry_entries=(entry,), test_root=tests,
                catalog_sha256="fixture-sha",
            )

        self.assertEqual(report["operations"][0]["static_test_references"],
                         ["test_devices_projection.py"])
        self.assertFalse(report["operations"][0]["function_verified"])

    def test_rejects_catalogs_that_could_overstate_their_scope(self) -> None:
        with self.assertRaisesRegex(ValueError, "scope"):
            build_report(
                {"catalog_scope": "runtime_support", "operations": []},
                source_map={}, registry_entries=(), test_root=Path("/missing"),
                catalog_sha256="fixture-sha",
            )

    def test_rejects_duplicate_operation_identity_after_placeholder_normalization(self) -> None:
        catalog = {
            "catalog_scope": "documentation_presence_only_not_runtime_support",
            "operations": [
                {"method": "GET", "path_template": "/openapi/v1/{siteId}/devices", "documented_in": ["a"]},
                {"method": "get", "path_template": "/openapi/v1/{id}/devices", "documented_in": ["b"]},
            ],
        }
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_report(
                catalog,
                source_map={}, registry_entries=(), test_root=Path("/missing"),
                catalog_sha256="fixture-sha",
            )

    def test_generated_ledger_matches_the_repository_catalog_and_route_registry(self) -> None:
        root = Path(__file__).resolve().parents[1]
        catalog_path = root / "docs/OPENAPI_ROUTE_CATALOG.json"
        catalog_bytes = catalog_path.read_bytes()
        catalog = json.loads(catalog_bytes)
        source_map = {
            _canonical(method, path): label
            for (method, path), label in IMPLEMENTED.items()
        }
        expected = build_report(
            catalog,
            source_map=source_map,
            registry_entries=REGISTRY.entries,
            test_root=root / "tests",
            catalog_sha256=hashlib.sha256(catalog_bytes).hexdigest(),
        )
        generated = json.loads((root / "docs/OPERATION_EVIDENCE.json").read_text(encoding="utf-8"))

        self.assertEqual(generated, expected)
        self.assertEqual(generated["operation_count"], 2445)
        self.assertEqual(generated["connector_evidence_counts"], {
            "not_mapped": 2002,
            "fixed_get_registry_route": 418,
            "manual_source_map_only": 25,
        })
        registry_rows = [row for row in generated["operations"]
                         if row["connector_evidence"] == "fixed_get_registry_route"]
        self.assertTrue(all(row["static_test_references"] for row in registry_rows))
        self.assertTrue(all(not row["function_verified"] for row in generated["operations"]))
        indexed = {operation_id for row in registry_rows
                   for operation_id in row["operation_ids"]}
        self.assertIn("site_vpn_s2s_status_summary", indexed)
        self.assertIn("site_ssid_topology_device_summary", indexed)
        public_templates = {
            "/v1/sites/{site_ref}/clients/recent-summary",
            "/v1/sites/{site_ref}/networks/{network_ref}/vlans/affected-ports-summary",
            "/v1/sites/{site_ref}/port-schedules/summary",
            "/v1/sites/{site_ref}/routing-table/summary",
            "/v1/sites/{site_ref}/vpn/clients/status-summary",
            "/v1/sites/{site_ref}/remote-logging/summary",
            "/v1/controller/firmware-upgrades/summary",
        }
        new_rows = [row for row in registry_rows
                    if public_templates.intersection(row["public_templates"])]
        self.assertEqual(len(new_rows), 7)
        self.assertTrue(all(row["documented_in"] == [
            "er7212pc-6.2.14", "hardware-controller-6.3.0",
            "omada-cbc-standard-6.3.0"] for row in new_rows))
        matrix = json.loads((root / "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        for source in matrix["sources"]:
            recent = source["operations"]["site_recent_clients_summary"]["contract_review"]
            affected = source["operations"]["site_vlan_affected_ports_summary"]["contract_review"]
            self.assertEqual(recent["operation_id"], "getGridKnownClients")
            self.assertIn("unit is not specified", recent["response"])
            self.assertEqual(affected["operation_id"],
                             "getGridVlanNetworkAffectedDevicePorts")
            self.assertIn("not unique physical ports", affected["connector_projection"])
            vpn = source["operations"]["site_vpn_client_status_summary"]["contract_review"]
            self.assertEqual(vpn["operation_id"], "getGridVpnClientStatus")
            self.assertIn("no status-code semantics", vpn["response"])
            s2s = source["operations"]["site_vpn_s2s_status_summary"]["contract_review"]
            self.assertEqual(s2s["operation_id"], "getGridVpnS2SStatus")
            self.assertIn("without enumerated values", s2s["response"])
            self.assertIn("does not say connected or disconnected", s2s["projection"])
            topology = source["operations"]["site_ssid_topology_device_summary"]
            if source["label"].startswith("ER7212PC"):
                self.assertFalse(topology["documented"])
            else:
                self.assertEqual(topology["contract_review"]["operation_id"],
                                 "getFilterDevicesOfSsid")
            remote = source["operations"]["site_remote_logging_summary"]["contract_review"]
            self.assertEqual(remote["operation_id"], "getRemoteLoggingSetting")
            self.assertIn("host and port", remote["projection"])
            upgrade = source["operations"]["controller_upgrade_log_summary"]["contract_review"]
            self.assertEqual(upgrade["operation_id"], "getGridUpgradeLogs")
            self.assertIn("no timestamps", upgrade["projection"].lower())
            ssid_clients = source["operations"]["site_ssid_client_count_summary"]
            if source["label"].startswith("ER7212PC"):
                self.assertFalse(ssid_clients["documented"])
            else:
                self.assertEqual(ssid_clients["contract_review"]["operation_id"],
                                 "getGridSsidClients")
            schedules = source["operations"]["site_port_schedule_summary"]["contract_review"]
            self.assertEqual(schedules["operation_id"], "getPortScheduleList")
            self.assertEqual(schedules["additional_operation_id"], "getPortSchedulePorts")
            routes = source["operations"]["site_routing_table_summary"]["contract_review"]
            self.assertEqual(routes["operation_id"], "getGridRouting")
            self.assertEqual(routes["path_parameter"]["type"],
                             "required string; documented values are gateway and switch")


if __name__ == "__main__":
    unittest.main()
