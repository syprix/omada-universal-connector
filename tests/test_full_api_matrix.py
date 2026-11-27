from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.operation_registry import REGISTRY
from tools.full_api_matrix import IMPLEMENTED, build_matrix


def document(*, suffix: str = "", method: str = "get", media: str = "application/json") -> dict[str, object]:
    path = "/openapi/v1/{omadacId}/sites"
    return {
        "openapi": "3.0.3", "info": {"title": "Test", "version": "1"},
        "paths": {path: {method: {
            "operationId": "sites", "parameters": [
                {"name": "page", "in": "query", "required": True,
                 "schema": {"type": "integer"}},
            ],
            "responses": {"200": {"description": "ok"}},
            "requestBody": {"required": True, "content": {media: {"schema": {"type": "object"}}}},
        }}}
    }


class FullApiMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_site_group_profiles_coverage_is_documented_in_all_three_sources(self):
        path = Path(__file__).resolve().parents[1] / "docs/CONTRACT_MATRIX.json"
        matrix = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        for source in matrix["sources"]:
            operation = source["operations"]["site_group_profiles_coverage"]
            self.assertTrue(operation["documented"])
            self.assertEqual(operation["live_support"], "unknown")
            review = operation["contract_review"]
            self.assertEqual(review["operation_id"], "getGroupProfiles")
            self.assertEqual(review["query"], {})
            self.assertIn("500 rows", review["connector_projection"])
            self.assertIn("no completeness marker", review["connector_projection"])

    def test_site_access_control_policy_coverage_matches_three_source_contract(self):
        path = Path(__file__).resolve().parents[1] / "docs/CONTRACT_MATRIX.json"
        matrix = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        for source in matrix["sources"]:
            operation = source["operations"]["site_access_control_policy_coverage"]
            self.assertTrue(operation["documented"])
            self.assertEqual(operation["live_support"], "unknown")
            review = operation["contract_review"]
            self.assertEqual(review["operation_id"], "getAccessControl")
            self.assertEqual(review["query"], {})
            self.assertIn("preAuthAccessEnable", review["response"])
            self.assertIn("freeAuthClientEnable", review["response"])
            self.assertIn("preAuthAccessPolicies", review["response"])
            self.assertIn("freeAuthClientPolicies", review["response"])
            self.assertIn("never iterated", review["connector_projection"])
            self.assertIn("500", review["connector_projection"])
            self.assertIn("enforcement", review["connector_projection"])

    def test_upgrade_failure_and_stack_cable_log_reads_match_three_source_contracts(self):
        path = Path(__file__).resolve().parents[1] / "docs/CONTRACT_MATRIX.json"
        matrix = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        expected = {
            "controller_upgrade_log_inventory": "getGridUpgradeLogs",
            "controller_upgrade_failed_devices_summary": "getUpgradeFailedDeviceInfos",
            "site_stack_cable_test_log_summary": "getStackCableTestLogs",
        }
        for source in matrix["sources"]:
            for operation_id, source_id in expected.items():
                operation = source["operations"][operation_id]
                self.assertTrue(operation["documented"])
                self.assertEqual(operation["live_support"], "unknown")
                self.assertEqual(operation["contract_review"]["operation_id"], source_id)


    def test_all_time_voucher_summary_matches_three_source_contracts(self):
        path = Path(__file__).resolve().parents[1] / "docs/CONTRACT_MATRIX.json"
        matrix = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        for source in matrix["sources"]:
            operation = source["operations"]["site_voucher_all_time_summary"]
            self.assertTrue(operation["documented"])
            self.assertEqual(operation["live_support"], "unknown")
            review = operation["contract_review"]
            self.assertEqual(review["operation_id"], "getAllTimeVoucherSummary")
            self.assertEqual(review["query"], {})
            self.assertIn("duration:int64", review["response"])
            self.assertIn("Amount and currency source values are omitted", review["projection"])

    def test_lan_switch_assignment_and_v2_ssid_topology_contracts_are_distinct(self):
        path = Path(__file__).resolve().parents[1] / "docs/CONTRACT_MATRIX.json"
        matrix = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        for source in matrix["sources"]:
            lan = source["operations"]["site_lan_switch_profile_assignments_summary"]
            self.assertTrue(lan["documented"])
            self.assertEqual(lan["live_support"], "unknown")
            self.assertIn("Direct GridVO", lan["contract_review"]["response"])
            wlan = source["operations"]["site_ssid_topology_reference_count"]
            self.assertEqual(wlan["documented"], source["label"] != "ER7212PC 6.2.14")
            self.assertEqual(wlan["live_support"], "unknown")

    def test_ipsec_failover_has_a_fixed_deprecated_registry_route(self):
        path = "/openapi/v1/{controller_id}/sites/{site_id}/vpn/ipsec_failovers"
        self.assertEqual(IMPLEMENTED[("GET", path)], "implemented_read")
        route, bindings = REGISTRY.match(
            "GET", "/v1/sites/" + "a" * 24 + "/ipsec-failovers/summary")
        self.assertEqual(route.operation_id, "site_ipsec_failover_summary")
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24})

    def test_ipsec_failover_is_documented_and_deprecated_in_all_exports(self):
        path = Path(__file__).resolve().parents[1] / "docs/CONTRACT_MATRIX.json"
        matrix = json.loads(path.read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_ipsec_failover_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertTrue(row["contract_review"]["deprecated"])

    def test_gateway_sim_sms_support_has_a_fixed_registry_and_matrix_route(self):
        path = "/openapi/v1/{controller_id}/sites/{site_id}/gateways/{gateway_mac}/sim/sms/support"
        self.assertEqual(IMPLEMENTED[("GET", path)], "implemented_read")
        route, bindings = REGISTRY.match(
            "GET", "/v1/sites/" + "a" * 24 + "/gateways/" + "b" * 24 +
            "/sim-capabilities-summary")
        self.assertEqual(route.operation_id, "site_gateway_sim_sms_support_summary")
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24, "gateway_ref": "b" * 24})

    def test_gateway_sim_sms_support_is_documented_in_all_exports(self):
        path = Path(__file__).resolve().parents[1] / "docs/CONTRACT_MATRIX.json"
        matrix = json.loads(path.read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_gateway_sim_sms_support_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertIn("getSupportSmsByMac", row["contract_review"]["operation_id"])

    def test_vlan_v2_opaque_topology_count_is_hardware_and_cbc_only(self):
        path = Path(__file__).resolve().parents[1] / "docs/CONTRACT_MATRIX.json"
        matrix = json.loads(path.read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_vlan_topology_reference_count"]
            self.assertEqual(row["documented"], source["label"] != "ER7212PC 6.2.14")
            self.assertEqual(row["live_support"], "unknown")

    def write_zip(self, name: str, value: dict[str, object]) -> Path:
        path = self.root / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("spec.json", json.dumps(value))
        return path

    def test_union_matrix_marks_documentation_source_match_and_live_unknown(self) -> None:
        first = self.write_zip("first.zip", document())
        second = self.write_zip("second.zip", {"openapi": "3.0.3", "info": {"title": "T", "version": "2"}, "paths": {}})
        report = build_matrix([("one", first), ("two", second)])
        self.assertFalse(report["live_verification_performed"])
        self.assertFalse(report["connector_source_mapping_is_automatic_verification"])
        self.assertIn("manually maintained partial source-review mapping",
                      report["connector_source_mapping_note"])
        self.assertEqual(report["operation_count_union"], 1)
        row = report["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")
        self.assertTrue(row["sources"][0]["documented"])
        self.assertFalse(row["sources"][1]["documented"])
        self.assertEqual(row["sources"][0]["variants"]["parameters"][0]["in"], "query")

    def test_site_remember_setting_is_covered_in_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_remember_setting_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/remember-device": {
                "get": {"operationId": "getSiteRememberSettingByOpenApi",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-remember-setting.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_gateway_qos_service_reference_inventory_is_distinct_and_documented(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        for source in matrix["sources"]:
            operation = source["operations"]["site_gateway_qos_service_reference_inventory"]
            self.assertTrue(operation["documented"])
            self.assertEqual(operation["live_support"], "unknown")
            self.assertEqual(operation["source_operation_id"], "getServiceTypeSummary")
            self.assertIn("unpaginated array", operation["response_contract"])
            self.assertIn("id:string and name:string", operation["response_contract"])
            self.assertIn("Omits IDs and names", operation["projection"])
            profiles = source["operations"]["site_gateway_qos_service_profiles_summary"]
            self.assertEqual(profiles["source_operation_id"], "listServiceType")
            self.assertNotEqual(operation["source_operation_id"], profiles["source_operation_id"])

    def test_site_ap_group_summary_contract_presence_and_live_state(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        expected = {
            "Hardware Controller 6.3.0": True,
            "CBC Standard 6.3.0": True,
            "ER7212PC 6.2.14": False,
        }
        for source in matrix["sources"]:
            row = source["operations"]["site_ap_group_summary"]
            self.assertEqual(row["documented"], expected[source["label"]])
            self.assertEqual(row["live_support"], "unknown")

    def test_wan_port_availability_contract_is_hardware_and_cbc_only(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        expected = {"Hardware Controller 6.3.0": True,
                    "CBC Standard 6.3.0": True,
                    "ER7212PC 6.2.14": False}
        for source in matrix["sources"]:
            row = source["operations"]["site_wan_port_availability_summary"]
            self.assertEqual(row["documented"], expected[source["label"]])
            self.assertEqual(row["live_support"], "unknown")
        op, bindings = REGISTRY.match(
            "GET", "/v1/sites/0123456789abcdef01234567/wan-ports/availability-summary")
        self.assertEqual(op.operation_id, "site_wan_port_availability_summary")
        self.assertEqual(bindings, (("site_ref", "0123456789abcdef01234567"),))
        tool = __import__("app.mcp", fromlist=["_tool"])._tool(op)
        self.assertEqual(tool["inputSchema"]["properties"]["function"]["enum"], list(range(16)))

    def test_wan_unsupported_function_contract_is_documented_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_wan_unsupported_function_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "obtainWanUnsupportedFunction")
            self.assertIn("filter=1", row["contract_review"]["projection"])

    def test_bonjour_profile_contract_is_documented_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_mdns_profile_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "listMdnsProfile")
            self.assertIn("serviceIds", row["contract_review"]["response"])

    def test_site_ap_oui_vlan_rules_contract_is_common_and_live_unknown(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_ap_oui_vlan_rules_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")

    def test_site_oui_profile_list_contract_records_er7212_pro_limit(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_oui_profile_list_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getOuiProfileList")
            self.assertIn("page 1", row["contract_review"]["connector_projection"])
        er7212 = matrix["sources"][2]["operations"]["site_oui_profile_list_summary"]
        self.assertIn("Omada Pro", er7212["contract_review"]["platform_limit"])

    def test_site_oui_profile_list_path_is_mapped_as_read(self) -> None:
        path = "/openapi/v1/{controller_id}/sites/{site_id}/oui-profiles"
        self.assertEqual(IMPLEMENTED[("GET", path)], "implemented_read")

    def test_site_vlan_ssid_usage_contract_is_common_and_live_unknown(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_vlan_ssid_usage_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")

    def test_site_vlan_device_usage_contract_is_common_and_live_unknown(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_vlan_device_usage_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")

    def test_site_wifi_calling_profiles_contract_is_common_and_live_unknown(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_wifi_calling_profiles_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")

    def test_client_filter_options_contract_is_common_and_live_unknown(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_client_filter_options_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")

    def test_client_detail_contract_records_wireless_ap_mapping_fields(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        self.assertEqual({source["label"] for source in matrix["sources"]}, {
            "Hardware Controller 6.3.0", "CBC Standard 6.3.0", "ER7212PC 6.2.14"})
        for source in matrix["sources"]:
            contract = source["operations"]["client_detail"]["contract_review"]
            self.assertEqual(contract["operation_id"], "getClientDetail")
            self.assertIn("apMac", contract["response"])
            self.assertIn("rssi", contract["response"])
            self.assertIn("same-site device inventory", contract["connector_projection"])
            self.assertEqual(contract["live_support"], "unknown")

    def test_eap_dot1x_candidates_contract_is_common_and_live_unknown(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_eap_dot1x_candidates_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")

    def test_switch_dot1x_candidates_contract_is_common_and_live_unknown(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_switch_dot1x_candidates_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")

    def test_different_documented_variants_are_counted(self) -> None:
        a = self.write_zip("a.zip", document())
        b = self.write_zip("b.zip", document(media="application/xml"))
        report = build_matrix([("a", a), ("b", b)])
        self.assertEqual(report["operations"][0]["variant_count"], 2)

    def test_placeholder_names_are_aligned_for_cross_source_comparison(self) -> None:
        a = self.write_zip("a.zip", document())
        alternate = document()
        alternate["paths"] = {
            route.replace("{omadacId}", "{controller_id}"): item
            for route, item in alternate["paths"].items()
        }
        b = self.write_zip("b.zip", alternate)
        report = build_matrix([("a", a), ("b", b)])
        self.assertEqual(report["operation_count_union"], 1)
        row = report["operations"][0]
        self.assertEqual(row["variant_count"], 1)
        self.assertEqual(row["sources"][0]["source_path"], "/openapi/v1/{omadacId}/sites")
        self.assertEqual(row["sources"][1]["source_path"], "/openapi/v1/{controller_id}/sites")

    def test_documented_write_is_not_claimed_as_implemented_read(self) -> None:
        p = self.write_zip("post.zip", document(method="post"))
        row = build_matrix([("post", p)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "unknown_not_reviewed")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_controller_system_port_reads_are_mapped_without_live_claim(self) -> None:
        spec = document()
        spec["paths"] = {
            f"/openapi/v1/{{omadacId}}/system/setting/{suffix}": {
                "get": {"operationId": operation, "responses": {"200": {}}},
            }
            for suffix, operation in (
                ("upgrade-port", "getUpgradePort"),
                ("portal-port", "getPortalPort"),
                ("controller-port", "getControllerPort"),
            )
        }
        path = self.write_zip("controller-system-ports.zip", spec)
        rows = build_matrix([("hardware", path)])["operations"]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["connector_source_status"] == "implemented_read" for row in rows))
        self.assertTrue(all(row["live_status"] == "unknown_not_checked_by_this_offline_tool"
                            for row in rows))

    def test_controller_status_logging_and_certificate_reads_are_mapped(self) -> None:
        spec = document()
        routes = {"controller-status": "getControllerStatus",
                  "logging": "getLogging", "certificate": "getCertificate"}
        spec["paths"] = {
            f"/openapi/v1/{{omadacId}}/system/setting/{suffix}": {
                "get": {"operationId": operation, "responses": {"200": {}}},
            }
            for suffix, operation in routes.items()
        }
        path = self.write_zip("controller-system-reads.zip", spec)
        rows = build_matrix([("hardware", path)])["operations"]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["connector_source_status"] == "implemented_read" for row in rows))
        self.assertTrue(all(row["live_status"] == "unknown_not_checked_by_this_offline_tool"
                            for row in rows))

    def test_controller_system_contract_matrix_keeps_all_three_sources_and_unknown_live(self):
        path = Path(__file__).resolve().parents[1] / "docs/CONTRACT_MATRIX.json"
        matrix = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        for source in matrix["sources"]:
            for operation in ("controller_status", "controller_logging", "controller_certificate"):
                row = source["operations"][operation]
                self.assertTrue(row["documented"])
                self.assertEqual(row["live_support"], "unknown")

    def test_msp_client_detail_setting_is_documented_only_in_msp_exports(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["msp_client_detail_info"]
            self.assertEqual(row["documented"],
                             source["label"] in ("CBC Standard 6.3.0", "ER7212PC 6.2.14"))
            self.assertEqual(row["live_support"], "unknown")

    def test_msp_audit_notification_is_cbc_only_and_live_unknown(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["msp_audit_notification"]
            self.assertEqual(row["documented"], source["label"] == "CBC Standard 6.3.0")
            self.assertEqual(row["live_support"], "unknown")

    def test_msp_device_link_topology_is_cbc_only_and_live_unknown(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["msp_device_link_topology"]
            self.assertEqual(row["documented"], source["label"] == "CBC Standard 6.3.0")
            self.assertEqual(row["live_support"], "unknown")

    def test_msp_device_tags_are_cbc_only_and_live_unknown(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["msp_device_tags"]
            self.assertEqual(row["documented"], source["label"] == "CBC Standard 6.3.0")
            self.assertEqual(row["live_support"], "unknown")

    def test_msp_mfa_status_is_cbc_only_and_live_unknown(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["msp_mfa_status"]
            self.assertEqual(row["documented"], source["label"] == "CBC Standard 6.3.0")
            self.assertEqual(row["live_support"], "unknown")

    def test_msp_license_auto_active_is_cbc_only_and_live_unknown(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["msp_license_auto_active"]
            self.assertEqual(row["documented"], source["label"] == "CBC Standard 6.3.0")
            self.assertEqual(row["live_support"], "unknown")

    def test_msp_customer_roles_are_cbc_only_and_live_unknown(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["msp_customer_roles"]
            self.assertEqual(row["documented"], source["label"] == "CBC Standard 6.3.0")
            self.assertEqual(row["live_support"], "unknown")

    def test_controller_client_history_retention_is_mapped_and_documented_in_all_sources(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        for source in matrix["sources"]:
            row = source["operations"]["controller_client_history_retention"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/controller/client/history-enable": {
                "get": {"operationId": "getClientHistoryDataEnable",
                        "responses": {"200": {}}}},
        }
        path = self.write_zip("controller-client-history-retention.zip", spec)
        rows = build_matrix([("hardware", path)])["operations"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["connector_source_status"], "implemented_read")
        self.assertEqual(rows[0]["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_backup_cloud_and_device_management_contracts_are_mapped_per_export(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            rows = source["operations"]
            is_er = source["label"] == "ER7212PC 6.2.14"
            self.assertEqual(rows["controller_backup_schedule"]["documented"], not is_er)
            for operation in ("controller_cloud_access", "controller_device_management"):
                self.assertTrue(rows[operation]["documented"])
                self.assertEqual(rows[operation]["live_support"], "unknown")

    def test_controller_remote_binding_and_maintenance_status_contracts(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            for operation in ("controller_remote_binding", "controller_backup_result",
                              "controller_restore_result"):
                self.assertTrue(source["operations"][operation]["documented"])
                self.assertEqual(source["operations"][operation]["live_support"], "unknown")

    def test_controller_privacy_policy_contract_is_present_with_live_unknown(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["controller_privacy_policy"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")

    def test_controller_mail_status_contract_is_present_with_live_unknown(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["controller_mail_status"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")

    def test_controller_global_mfa_status_contract_is_present_with_live_unknown(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["controller_global_mfa_status"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")

    def test_msp_status_contracts_keep_source_coverage_and_live_unknown(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            label = source["label"]
            self.assertEqual(source["operations"]["msp_cloud_access_status"]["documented"],
                             label != "Hardware Controller 6.3.0")
            self.assertEqual(source["operations"]["msp_privacy_policy"]["documented"],
                             label == "CBC Standard 6.3.0")
            self.assertEqual(source["operations"]["msp_dst_info"]["documented"],
                             label == "CBC Standard 6.3.0")
            self.assertEqual(source["operations"]["msp_remote_logging"]["documented"],
                             label == "CBC Standard 6.3.0")
            self.assertEqual(source["operations"]["msp_mail_server"]["documented"],
                             label == "CBC Standard 6.3.0")
            self.assertEqual(source["operations"]["msp_general_settings"]["documented"],
                             label == "CBC Standard 6.3.0")
            self.assertEqual(source["operations"]["msp_log_notification_settings"]["documented"],
                             label == "CBC Standard 6.3.0")
            self.assertEqual(source["operations"]["msp_data_retention"]["documented"],
                             label == "CBC Standard 6.3.0")
            self.assertEqual(source["operations"]["msp_ui_interface"]["documented"],
                             label == "CBC Standard 6.3.0")
            self.assertEqual(source["operations"]["msp_user_interface"]["documented"],
                             label == "CBC Standard 6.3.0")
            self.assertEqual(source["operations"]["msp_available_roles"]["documented"],
                             label == "CBC Standard 6.3.0")
            self.assertEqual(source["operations"]["msp_available_customer_roles"]["documented"],
                             label == "CBC Standard 6.3.0")
            self.assertEqual(source["operations"]["msp_dashboard_overall"]["documented"],
                             label == "CBC Standard 6.3.0")
            self.assertEqual(source["operations"]["msp_cluster_nodes"]["documented"],
                             label == "CBC Standard 6.3.0")
            self.assertEqual(source["operations"]["msp_cloud_access_status"]["live_support"], "unknown")
            self.assertEqual(source["operations"]["msp_privacy_policy"]["live_support"], "unknown")

    def test_controller_backup_cloud_and_device_management_paths_match_source_routes(self):
        contracts = (
            ("controller_backup_schedule", "/openapi/v1/{omadacId}/backupschedule/task"),
            ("controller_cloud_access", "/openapi/v1/{omadacId}/cloud/status"),
            ("controller_device_management", "/openapi/v1/{omadacId}/device-mgmt"),
        )
        for operation_id, path in contracts:
            with self.subTest(operation=operation_id):
                spec = document()
                spec["paths"] = {path: {"get": {"operationId": operation_id,
                                                   "responses": {"200": {}}}}}
                archive = self.write_zip(f"{operation_id}.zip", spec)
                row = build_matrix([("hardware", archive)])["operations"][0]
                self.assertEqual(row["connector_source_status"], "implemented_read")
                self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_controller_remote_binding_and_maintenance_routes_match_source_contracts(self):
        contracts = (
            ("controller_remote_binding", "/openapi/v1/{omadacId}/cloud/remote/bind/status"),
            ("controller_backup_result", "/openapi/v1/{omadacId}/maintenance/backup/result"),
            ("controller_restore_result", "/openapi/v1/{omadacId}/maintenance/restore/result"),
        )
        for operation_id, path in contracts:
            with self.subTest(operation=operation_id):
                spec = document()
                spec["paths"] = {path: {"get": {"operationId": operation_id,
                                                   "responses": {"200": {}}}}}
                archive = self.write_zip(f"{operation_id}.zip", spec)
                row = build_matrix([("hardware", archive)])["operations"][0]
                self.assertEqual(row["connector_source_status"], "implemented_read")
                self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_controller_privacy_policy_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/{omadacId}/privacy-policy"
        spec["paths"] = {path: {"get": {"operationId": "getPrivacyPolicy",
                                          "responses": {"200": {}}}}}
        archive = self.write_zip("controller_privacy_policy.zip", spec)
        row = build_matrix([("hardware", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_controller_mail_status_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/{omadacId}/mail/status"
        spec["paths"] = {path: {"get": {"operationId": "getMailServerStatus",
                                          "responses": {"200": {}}}}}
        archive = self.write_zip("controller_mail_status.zip", spec)
        row = build_matrix([("hardware", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_controller_global_mfa_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/{omadacId}/mfa/status"
        spec["paths"] = {path: {"get": {"operationId": "getGlobalMFAStatus",
                                          "responses": {"200": {}}}}}
        archive = self.write_zip("controller_global_mfa.zip", spec)
        row = build_matrix([("hardware", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_cloud_status_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/msp/{mspId}/cloud/status"
        spec["paths"] = {path: {"get": {"operationId": "getMspCloudAccessStatus",
                                          "responses": {"200": {}}}}}
        archive = self.write_zip("msp_cloud_access_status.zip", spec)
        row = build_matrix([("hardware", archive)]) ["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_privacy_policy_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/msp/{mspId}/privacy-policy"
        spec["paths"] = {path: {"get": {"operationId": "getPrivacyPolicyMsp",
                                          "responses": {"200": {}}}}}
        archive = self.write_zip("msp_privacy_policy.zip", spec)
        row = build_matrix([("hardware", archive)]) ["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_dst_info_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/msp/{mspId}/dst-info"
        spec["paths"] = {path: {"get": {"operationId": "getMspDstInfo",
                                          "responses": {"200": {}}}}}
        archive = self.write_zip("msp_dst_info.zip", spec)
        row = build_matrix([("cbc", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_remote_logging_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/msp/{mspId}/remote-logging"
        spec["paths"] = {path: {"get": {"operationId": "getRemoteLoggingSetting_1",
                                          "responses": {"200": {}}}}}
        archive = self.write_zip("msp_remote_logging.zip", spec)
        row = build_matrix([("cbc", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_mail_server_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/msp/{mspId}/settings/mail-server"
        spec["paths"] = {path: {"get": {"operationId": "getMspMailServer",
                                          "responses": {"200": {}}}}}
        archive = self.write_zip("msp_mail_server.zip", spec)
        row = build_matrix([("cbc", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_general_settings_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/msp/{mspId}/general-setting"
        spec["paths"] = {path: {"get": {"operationId": "getGeneralSetting",
                                          "responses": {"200": {}}}}}
        archive = self.write_zip("msp_general_settings.zip", spec)
        row = build_matrix([("cbc", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_log_notification_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/msp/{mspId}/log-notification"
        spec["paths"] = {path: {"get": {"operationId": "getLogSettingForMsp",
                                          "responses": {"200": {}}}}}
        archive = self.write_zip("msp_log_notification.zip", spec)
        row = build_matrix([("cbc", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_data_retention_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/msp/{mspId}/retention"
        spec["paths"] = {path: {"get": {"operationId": "getMspDataRetention",
                                          "responses": {"200": {}}}}}
        archive = self.write_zip("msp_data_retention.zip", spec)
        row = build_matrix([("cbc", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_ui_interface_route_matches_source_contract(self):
        contracts = (
            ("/openapi/v1/msp/{mspId}/ui-interface", "getUiInterface_1"),
            ("/openapi/v1/msp/{mspId}/settings/user-interface", "getMspUserInterface"),
        )
        for i, (path, operation_id) in enumerate(contracts):
            with self.subTest(operation=operation_id):
                spec = document()
                spec["paths"] = {path: {"get": {"operationId": operation_id,
                                                 "responses": {"200": {}}}}}
                archive = self.write_zip(f"msp_ui_interface_{i}.zip", spec)
                row = build_matrix([("cbc", archive)])["operations"][0]
                self.assertEqual(row["connector_source_status"], "implemented_read")
                self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_available_role_routes_match_source_contract(self):
        contracts = (
            ("/openapi/v1/msp/{mspId}/roles/available", "getAvailableMspRoles"),
            ("/openapi/v1/msp/{mspId}/roles/customer/roles/available",
             "getAvailableCustomerRoles"),
        )
        for i, (path, operation_id) in enumerate(contracts):
            with self.subTest(operation=operation_id):
                spec = document()
                spec["paths"] = {path: {"get": {"operationId": operation_id,
                                                 "responses": {"200": {}}}}}
                archive = self.write_zip(f"msp_available_roles_{i}.zip", spec)
                row = build_matrix([("cbc", archive)])["operations"][0]
                self.assertEqual(row["connector_source_status"], "implemented_read")
                self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_cluster_nodes_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/msp/{mspId}/cluster/nodes/info"
        spec["paths"] = {path: {"get": {"operationId": "getMspClusterNodesInfo",
                                         "responses": {"200": {}}}}}
        archive = self.write_zip("msp_cluster_nodes.zip", spec)
        row = build_matrix([("cbc", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_adopt_tip_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/msp/{mspId}/adopt-tip"
        spec["paths"] = {path: {"get": {"operationId": "getMspAdoptTip",
                                         "responses": {"200": {}}}}}
        archive = self.write_zip("msp_adopt_tip.zip", spec)
        row = build_matrix([("cbc", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_controller_adopt_tip_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/{omadacId}/adopt-tip"
        self.assertEqual(IMPLEMENTED[("GET", "/openapi/v1/{controller_id}/adopt-tip")],
                         "implemented_read")
        spec["paths"] = {path: {"get": {"operationId": "getAdoptTip",
                                         "responses": {"200": {}}}}}
        archive = self.write_zip("controller_adopt_tip.zip", spec)
        row = build_matrix([("hardware-controller", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")

    def test_controller_placed_site_position_contract_matrix_is_documented_and_redacted(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        self.assertEqual(
            IMPLEMENTED[("GET", "/openapi/v1/{controller_id}/placed-site-position")],
            "implemented_read")
        for source in matrix["sources"]:
            operation = source["operations"]["controller_placed_site_position_coverage"]
            review = operation["contract_review"]
            self.assertTrue(operation["documented"])
            self.assertEqual(review["operation_id"], "getPlacedSitePositions")
            self.assertEqual(review["method"], "GET")
            self.assertEqual(review["query"], {})
            self.assertFalse(review["request_body"])
            self.assertIn("No pagination/total", review["connector_projection"])
            self.assertIn("Never returns identifiers", review["connector_projection"])
        er = next(source for source in matrix["sources"]
                  if source["label"] == "ER7212PC 6.2.14")
        self.assertIn("object (opaque", er["operations"][
            "controller_placed_site_position_coverage"]["contract_review"]["response"])

    def test_controller_unplaced_site_position_contract_matrix_is_documented_and_redacted(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        self.assertEqual(
            IMPLEMENTED[("GET", "/openapi/v1/{controller_id}/unplaced-site-position")],
            "implemented_read")
        for source in matrix["sources"]:
            operation = source["operations"]["controller_unplaced_site_position_coverage"]
            review = operation["contract_review"]
            self.assertTrue(operation["documented"])
            self.assertEqual(review["operation_id"], "getUnplacedSitePositions")
            self.assertEqual(review["method"], "GET")
            self.assertIn("page", review["query"])
            self.assertIn("pageSize", review["query"])
            self.assertIn("totalRows", review["response"])
            self.assertIn("unplacedNum", review["response"])
            self.assertIn("string id/region/name", review["response"])
            self.assertIn("int32 type", review["response"])
            self.assertIn("never returns", review["connector_projection"].lower())

    def test_controller_client_correction_options_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/{omadacId}/correction-list"
        self.assertEqual(IMPLEMENTED[("GET", "/openapi/v1/{controller_id}/correction-list")],
                         "implemented_read")
        spec["paths"] = {path: {"get": {"operationId": "getClientCorrectionList",
                                         "responses": {"200": {}}}}}
        archive = self.write_zip("controller_client_correction_options.zip", spec)
        row = build_matrix([("hardware-controller", archive)])[
            "operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_session_limit_enable_state_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/{omadacId}/sites/{siteId}/session-limit"
        self.assertEqual(
            IMPLEMENTED[("GET", "/openapi/v1/{controller_id}/sites/{site_id}/session-limit")],
            "implemented_read")
        spec["paths"] = {path: {"get": {"operationId": "getSessionLimit",
                                         "responses": {"200": {}}}}}
        archive = self.write_zip("site_session_limit_enable_state.zip", spec)
        row = build_matrix([("hardware-controller", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_mac_filtering_general_state_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/{omadacId}/sites/{siteId}/mac-filter"
        self.assertEqual(
            IMPLEMENTED[("GET", "/openapi/v1/{controller_id}/sites/{site_id}/mac-filter")],
            "implemented_read")
        spec["paths"] = {path: {"get": {"operationId": "getMacFilteringGeneralSetting",
                                         "responses": {"200": {}}}}}
        archive = self.write_zip("site_mac_filtering_general_state.zip", spec)
        row = build_matrix([("hardware-controller", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_device_model_whitelist_coverage_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/{omadacId}/sites/{siteId}/device-white-list"
        self.assertEqual(
            IMPLEMENTED[("GET", "/openapi/v1/{controller_id}/sites/{site_id}/device-white-list")],
            "implemented_read")
        spec["paths"] = {path: {"get": {"operationId": "getDeviceWhiteList",
                                         "responses": {"200": {}}}}}
        archive = self.write_zip("site_device_model_whitelist_coverage.zip", spec)
        row = build_matrix([("hardware-controller", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_portal_inventory_coverage_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/{omadacId}/sites/{siteId}/portals"
        self.assertEqual(
            IMPLEMENTED[("GET", "/openapi/v1/{controller_id}/sites/{site_id}/portals")],
            "implemented_read")
        spec["paths"] = {path: {"get": {"operationId": "getPortalList",
                                         "responses": {"200": {}}}}}
        archive = self.write_zip("site_portal_inventory_coverage.zip", spec)
        row = build_matrix([("hardware-controller", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_access_control_policy_coverage_route_matches_source_contract(self):
        path = "/openapi/v1/{omadacId}/sites/{siteId}/setting/access-control"
        self.assertEqual(
            IMPLEMENTED[("GET", "/openapi/v1/{controller_id}/sites/{site_id}/setting/access-control")],
            "implemented_read")
        spec = document()
        spec["paths"] = {path: {"get": {"operationId": "getAccessControl",
                                          "responses": {"200": {}}}}}
        archive = self.write_zip("site_access_control_policy_coverage.zip", spec)
        row = build_matrix([("hardware-controller", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_rate_limit_profiles_summary_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/{omadacId}/sites/{siteId}/rate-limit-profiles"
        self.assertEqual(
            IMPLEMENTED[("GET", "/openapi/v1/{controller_id}/sites/{site_id}/rate-limit-profiles")],
            "implemented_read")
        spec["paths"] = {path: {"get": {"operationId": "getRateLimitProfileList",
                                         "responses": {"200": {}}}}}
        archive = self.write_zip("site_rate_limit_profiles_summary.zip", spec)
        row = build_matrix([("hardware-controller", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_role_summary_route_matches_source_contract(self):
        spec = document()
        path = "/openapi/v1/msp/{mspId}/roles"
        spec["paths"] = {path: {"get": {"operationId": "getAllMspRoles",
                                         "responses": {"200": {}}}}}
        archive = self.write_zip("msp_roles.zip", spec)
        row = build_matrix([("cbc", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_switch_qos_mode_is_documented_across_all_sources(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_switch_qos_mode"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")

        spec = document()
        path = "/openapi/v1/{omadacId}/sites/{siteId}/switch-qos/qos-mode"
        spec["paths"] = {path: {"get": {"operationId": "getOswQosMode",
                                         "responses": {"200": {}}}}}
        archive = self.write_zip("site_switch_qos_mode.zip", spec)
        row = build_matrix([("hardware", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_switch_qos_mapping_routes_match_all_source_contracts(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            for operation in ("site_switch_qos_scheduler_summary",
                              "site_switch_qos_dscp_summary"):
                self.assertTrue(source["operations"][operation]["documented"])
                self.assertEqual(source["operations"][operation]["live_support"], "unknown")
        contracts = (
            ("/openapi/v1/{omadacId}/sites/{siteId}/switch-qos/qos-rule/scheduler-mapping",
             "getSchedulerMapping"),
            ("/openapi/v1/{omadacId}/sites/{siteId}/switch-qos/qos-rule/dscp-mapping",
             "getDscpMapping"),
        )
        for i, (path, operation_id) in enumerate(contracts):
            with self.subTest(operation=operation_id):
                spec = document()
                spec["paths"] = {path: {"get": {"operationId": operation_id,
                                                 "responses": {"200": {}}}}}
                archive = self.write_zip(f"site_switch_qos_mapping_{i}.zip", spec)
                row = build_matrix([("hardware", archive)])["operations"][0]
                self.assertEqual(row["connector_source_status"], "implemented_read")
                self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_controller_role_reads_are_documented_in_all_sources_and_live_unknown(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            for operation in ("controller_roles", "controller_available_roles"):
                row = source["operations"][operation]
                self.assertTrue(row["documented"])
                self.assertEqual(row["live_support"], "unknown")

    def test_controller_role_paths_are_mapped_to_fixed_reads(self):
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/roles": {
                "get": {"operationId": "getAllRoles", "responses": {"200": {}}}},
            "/openapi/v1/{omadacId}/roles/available": {
                "get": {"operationId": "getAvailableRole", "responses": {"200": {}}}},
        }
        path = self.write_zip("controller-role-reads.zip", spec)
        rows = build_matrix([("hardware", path)])["operations"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["connector_source_status"] == "implemented_read" for row in rows))
        self.assertTrue(all(row["live_status"] == "unknown_not_checked_by_this_offline_tool"
                            for row in rows))

    def test_device_system_reads_are_mapped_with_documentation_scope(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            for operation in ("device_adopt_result", "device_mac_type"):
                row = source["operations"][operation]
                self.assertTrue(row["documented"])
                self.assertEqual(row["live_support"], "unknown")
            radsec = source["operations"]["device_radsec_support"]
            self.assertTrue(radsec["documented"])
            self.assertEqual(radsec["live_support"], "unknown")
            upgrade = source["operations"]["device_upgrade_result"]
            self.assertTrue(upgrade["documented"])
            self.assertEqual(upgrade["live_support"], "unknown")
            timeline = source["operations"]["device_timeline"]
            self.assertTrue(timeline["documented"])
            self.assertEqual(timeline["live_support"], "unknown")
            topology = source["operations"]["device_link_topology"]
            self.assertEqual(topology["live_support"], "unknown")
            self.assertEqual(topology["documented"], source["label"] != "ER7212PC 6.2.14")

    def test_olt_system_reads_are_documented_in_all_sources_and_live_unknown(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            for operation in ("olt_system_info", "olt_management_interfaces"):
                row = source["operations"][operation]
                self.assertTrue(row["documented"])
                self.assertEqual(row["live_support"], "unknown")

    def test_olt_detail_summary_matches_all_three_source_contracts(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        for source in matrix["sources"]:
            row = source["operations"]["olt_detail_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}": {
                "get": {"operationId": "getDetail", "responses": {"200": {}}}},
        }
        path = self.write_zip("olt-detail-summary.zip", spec)
        rows = build_matrix([("hardware", path)])['operations']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["connector_source_status"], "implemented_read")

    def test_olt_port_summary_matches_all_three_source_contracts(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        for source in matrix["sources"]:
            row = source["operations"]["olt_ports_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/eth-port/and/pon-port/list": {
                "get": {"operationId": "getEthAndPonList", "responses": {"200": {}}}},
        }
        path = self.write_zip("olt-port-summary.zip", spec)
        rows = build_matrix([("hardware", path)])["operations"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["connector_source_status"], "implemented_read")
        self.assertEqual(rows[0]["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_olt_onu_status_reads_match_all_three_source_contracts(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            for operation in ("olt_onu_global_status", "olt_onu_isolation_status"):
                row = source["operations"][operation]
                self.assertTrue(row["documented"])
                self.assertEqual(row["live_support"], "unknown")
        contracts = (
            ("/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/pon/onu-management/global-config/get",
             "getOnuGlobalConfigStatus"),
            ("/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/pon/onu-management/global-config/isolation/get",
             "getOnuIsolationStatus"),
        )
        for index, (route, operation_id) in enumerate(contracts):
            spec = document()
            spec["paths"] = {route: {"get": {"operationId": operation_id,
                                              "responses": {"200": {}}}}}
            archive = self.write_zip(f"olt-onu-status-{index}.zip", spec)
            row = build_matrix([("hardware", archive)])["operations"][0]
            self.assertEqual(row["connector_source_status"], "implemented_read")
            self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_olt_ethernet_configuration_reads_match_all_three_source_contracts(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            for operation in ("olt_eth_config_summary", "olt_lag_config_summary"):
                row = source["operations"][operation]
                self.assertTrue(row["documented"])
                self.assertEqual(row["live_support"], "unknown")
        contracts = (
            ("/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/l2-feature/eth-port/port/unit1/list",
             "getPortsConfigList"),
            ("/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/l2-feature/eth-port/port/lags/list",
             "getLagsConfigList"),
        )
        for index, (route, operation_id) in enumerate(contracts):
            spec = document()
            spec["paths"] = {route: {"get": {"operationId": operation_id,
                                              "responses": {"200": {}}}}}
            archive = self.write_zip(f"olt-eth-config-{index}.zip", spec)
            row = build_matrix([("hardware", archive)])["operations"][0]
            self.assertEqual(row["connector_source_status"], "implemented_read")
            self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_olt_pon_information_reads_match_all_three_source_contracts(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            for operation in ("olt_auto_refresh_summary", "olt_pon_information_summary"):
                row = source["operations"][operation]
                self.assertTrue(row["documented"])
                self.assertEqual(row["live_support"], "unknown")
        contracts = (
            ("/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/pon/service-port/statistic/configs",
             "getAutoRefreshConfig"),
            ("/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/pon/pon-port/informations/list",
             "getPonPortInformationList"),
        )
        for index, (route, operation_id) in enumerate(contracts):
            spec = document()
            spec["paths"] = {route: {"get": {"operationId": operation_id,
                                              "responses": {"200": {}}}}}
            archive = self.write_zip(f"olt-pon-info-{index}.zip", spec)
            row = build_matrix([("hardware", archive)])["operations"][0]
            self.assertEqual(row["connector_source_status"], "implemented_read")
            self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_olt_onu_registration_reads_match_all_three_source_contracts(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            for operation in ("olt_onu_auto_auth_status", "olt_onu_autofind_summary"):
                row = source["operations"][operation]
                self.assertTrue(row["documented"])
                self.assertEqual(row["live_support"], "unknown")
        contracts = (
            ("/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/pon/onu-register/auto-authentication/global/configs/get",
             "getOnuAutoAuthenticationConfig"),
            ("/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/pon/onu-register/autofind/configs/get",
             "getOnuRegisterAutofindConfig"),
        )
        for index, (route, operation_id) in enumerate(contracts):
            spec = document()
            spec["paths"] = {route: {"get": {"operationId": operation_id,
                                              "responses": {"200": {}}}}}
            archive = self.write_zip(f"olt-onu-registration-{index}.zip", spec)
            row = build_matrix([("hardware", archive)])["operations"][0]
            self.assertEqual(row["connector_source_status"], "implemented_read")
            self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")



    def test_olt_service_port_profiles_match_all_three_source_contracts(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["olt_service_port_profiles_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        route = "/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/pon/profile/service-port/profiles/list"
        spec = document()
        spec["paths"] = {route: {"get": {"operationId": "getServicePortProfileList",
                                             "responses": {"200": {}}}}}
        archive = self.write_zip("olt-service-port-profiles.zip", spec)
        row = build_matrix([("hardware", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")


    def test_olt_pon_port_config_page_matches_all_three_source_contracts(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["olt_pon_port_config_page_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        route = "/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/pon/pon-port/configs/page"
        spec = document()
        spec["paths"] = {route: {"get": {"operationId": "getPonPortPage",
                                             "parameters": [{"name": "queryParam", "in": "query",
                                                             "required": True, "schema": {"type": "object"}}],
                                             "responses": {"200": {}}}}}
        archive = self.write_zip("olt-pon-port-config-page.zip", spec)
        row = build_matrix([("hardware", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_olt_autofind_inventory_matches_all_three_source_contracts(self):
        contract_matrix = json.loads((Path(__file__).resolve().parents[1] /
                                      "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in contract_matrix["sources"]:
            row = source["operations"]["olt_onu_autofind_inventory_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        operation = REGISTRY.get("olt_onu_autofind_inventory_summary")
        self.assertEqual(operation.extra_arguments, ("pon_port", "page_number", "page_size"))
        route = "/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/pon/onu-register/autofinds/list"
        spec = document()
        spec["paths"] = {route: {"get": {"operationId": "getOnuAutofindConfigList",
                                             "parameters": [{"name": "queryParam", "in": "query",
                                                             "required": True,
                                                             "schema": {"type": "object"}}],
                                             "responses": {"200": {}}}}}
        archive = self.write_zip("olt-onu-autofind-inventory.zip", spec)
        row = build_matrix([("hardware", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_ap_mesh_statistics_matches_edge_and_cbc_sources(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        by_label = {source["label"]: source for source in matrix["sources"]}
        self.assertTrue(by_label["ER7212PC 6.2.14"]["operations"]["msp_ap_mesh_statistics"]["documented"])
        self.assertFalse(by_label["Hardware Controller 6.3.0"]["operations"]["msp_ap_mesh_statistics"]["documented"])
        self.assertTrue(by_label["CBC Standard 6.3.0"]["operations"]["msp_ap_mesh_statistics"]["documented"])
        route = "/openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/aps/{apMac}/mesh/statistics"
        spec = document()
        spec["paths"] = {route: {"get": {"operationId": "getMeshStatisticsForMsp",
                                             "responses": {"200": {}}}}}
        archive = self.write_zip("msp-ap-mesh-statistics.zip", spec)
        row = build_matrix([("edge", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_olt_read_family_matches_edge_and_cbc_sources(self):
        names = ("msp_olt_detail_summary", "msp_olt_eth_config_summary",
                 "msp_olt_site_ports_summary", "msp_olt_pon_port_config_summary")
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            for name in names:
                self.assertEqual(source["operations"][name]["documented"],
                                 source["label"] in {"ER7212PC 6.2.14", "CBC Standard 6.3.0"})
                self.assertEqual(source["operations"][name]["live_support"], "unknown")
        contracts = (
            ("getOltDetailForMsp", "/openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/olts/{deviceMac}"),
            ("getPortsConfigListForMsp", "/openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/olts/{deviceMac}/l2-feature/eth-port/port/unit1/list"),
            ("getEthAndPonListForMsp", "/openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/eth-port/and/pon-port/list"),
            ("getPonPortListMsp", "/openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/olts/{deviceMac}/pon/pon-port/configs/list"),
        )
        spec = document()
        spec["paths"] = {route: {"get": {"operationId": operation, "responses": {"200": {}}}}
                          for operation, route in contracts}
        archive = self.write_zip("msp-olt-read-family.zip", spec)
        for row in build_matrix([("edge", archive)])["operations"]:
            self.assertEqual(row["connector_source_status"], "implemented_read")
            self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_olt_pon_port_config_matches_all_three_source_contracts(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["olt_pon_port_config_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        route = "/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/pon/pon-port/configs/list"
        spec = document()
        spec["paths"] = {route: {"get": {"operationId": "getPonPortList",
                                             "responses": {"200": {}}}}}
        archive = self.write_zip("olt-pon-port-config.zip", spec)
        row = build_matrix([("hardware", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")


    def test_olt_onu_inventory_read_matches_three_sources_and_required_selector(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["olt_onu_inventory_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        route = "/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/pon/onu-management/informations/list"
        spec = document()
        spec["paths"] = {route: {"get": {
            "operationId": "getOnuInformationConfigList",
            "parameters": [{"name": "queryParam", "in": "query", "required": True,
                            "schema": {"type": "object", "required": ["ponPort"],
                                       "properties": {"ponPort": {"type": "string"}}}}],
            "responses": {"200": {}}}}}
        archive = self.write_zip("olt-onu-inventory-selector.zip", spec)
        row = build_matrix([("hardware", archive)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_olt_onu_reboot_status_reads_match_all_three_source_contracts(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            for operation in ("olt_onu_reboot_status_summary",):
                row = source["operations"][operation]
                self.assertTrue(row["documented"])
                self.assertEqual(row["live_support"], "unknown")
        contracts = (
            ("/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/pon/onu-management/informations/reboot-status/list",
             "getOnuRebootStatusConfigList"),
        )
        for index, (route, operation_id) in enumerate(contracts):
            spec = document()
            spec["paths"] = {route: {"get": {"operationId": operation_id,
                                              "responses": {"200": {}}}}}
            archive = self.write_zip(f"olt-onu-reboot-status-{index}.zip", spec)
            row = build_matrix([("hardware", archive)])["operations"][0]
            self.assertEqual(row["connector_source_status"], "implemented_read")
            self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_device_health_reads_match_cbc_and_er_source_contracts(self):
        source_matrix = json.loads((Path(__file__).resolve().parents[1] /
                                    "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in source_matrix["sources"]:
            documented = source["label"] != "Hardware Controller 6.3.0"
            for operation in ("msp_ap_health_detail", "msp_gateway_health_detail",
                              "msp_switch_health_detail", "msp_ap_health_timeline",
                              "msp_gateway_health_timeline", "msp_switch_health_timeline"):
                self.assertEqual(source["operations"][operation]["documented"], documented)
                self.assertEqual(source["operations"][operation]["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/eaps/{apMac}/health/detail": {
                "get": {"operationId": "getMspApHealthDetail", "responses": {"200": {}}}},
            "/openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/gateways/{gatewayMac}/health/detail": {
                "get": {"operationId": "getMspOsgHealthDetail", "responses": {"200": {}}}},
            "/openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/switches/{switchMac}/health/detail": {
                "get": {"operationId": "getMspOswHealthDetail", "responses": {"200": {}}}},
            "/openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/eaps/{apMac}/health/timeline": {
                "get": {"operationId": "getMspApHealthTimeList", "responses": {"200": {}}}},
            "/openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/gateways/{gatewayMac}/health/timeline": {
                "get": {"operationId": "getMspOsgHealthTimeList", "responses": {"200": {}}}},
            "/openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/switches/{switchMac}/health/timeline": {
                "get": {"operationId": "getMspOswHealthTimeList", "responses": {"200": {}}}},
        }
        path = self.write_zip("msp-health-timelines.zip", spec)
        rows = build_matrix([("cbc", path)])["operations"]
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row["connector_source_status"] == "implemented_read" for row in rows))

    def test_msp_olt_system_path_is_mapped_to_fixed_read(self):
        spec = document()
        spec["paths"] = {
            "/openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/olts/{deviceMac}/system/system-info/configs": {
                "get": {"operationId": "getConfigForMsp", "responses": {"200": {}}}},
        }
        path = self.write_zip("olt-system-info-msp.zip", spec)
        rows = build_matrix([("cbc", path)])['operations']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["connector_source_status"], "implemented_read")
        self.assertEqual(rows[0]["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_msp_olt_system_info_is_documented_only_in_msp_exports(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["olt_system_info_msp"]
            self.assertEqual(row["documented"], source["label"] != "Hardware Controller 6.3.0")
            self.assertEqual(row["live_support"], "unknown")

    def test_olt_system_paths_are_mapped_to_fixed_reads(self):
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/system/system-info/configs": {
                "get": {"operationId": "getConfig", "responses": {"200": {}}}},
            "/openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/system/management-system-interface/get": {
                "get": {"operationId": "getManagementSystemInterfaces", "responses": {"200": {}}}},
        }
        path = self.write_zip("olt-system-reads.zip", spec)
        rows = build_matrix([("hardware", path)])["operations"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["connector_source_status"] == "implemented_read" for row in rows))
        self.assertTrue(all(row["live_status"] == "unknown_not_checked_by_this_offline_tool"
                            for row in rows))

    def test_device_system_paths_are_mapped_to_fixed_reads(self):
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/devices/{deviceMac}/adopt-result": {
                "get": {"operationId": "getDeviceAdoptResult", "responses": {"200": {}}}},
            "/openapi/v1/{omadacId}/sites/{siteId}/devices/{deviceMac}/check-mac-type": {
                "get": {"operationId": "checkMacType", "responses": {"200": {}}}},
            "/openapi/v2/{omadacId}/sites/{siteId}/devices/{deviceMac}/device-link-topology": {
                "get": {"operationId": "getDeviceLinkTopology", "responses": {"200": {}}}},
            "/openapi/v1/{omadacId}/sites/{siteId}/devices/un-support-radsec": {
                "get": {"operationId": "existUnSupportRadSecDevice", "responses": {"200": {}}}},
            "/openapi/v1/{omadacId}/sites/{siteId}/devices/{deviceMac}/online-upgrade-result": {
                "get": {"operationId": "getOnlineUpgradeRes", "responses": {"200": {}}}},
            "/openapi/v1/{omadacId}/sites/{siteId}/devices/{deviceMac}/timeline": {
                "get": {"operationId": "getOnlineTimeline", "responses": {"200": {}}}},
            "/openapi/v1/{omadacId}/sites/{siteId}/devices/all": {
                "get": {"operationId": "getAllDevices", "responses": {"200": {}}}},
        }
        path = self.write_zip("device-system-reads.zip", spec)
        rows = build_matrix([("hardware", path)])["operations"]
        self.assertEqual(len(rows), 7)
        self.assertTrue(all(row["connector_source_status"] == "implemented_read" for row in rows))
        self.assertTrue(all(row["live_status"] == "unknown_not_checked_by_this_offline_tool"
                            for row in rows))

    def test_site_radius_user_summary_is_matched_to_its_documented_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/profiles/radius-server/users": {
                "get": {"operationId": "getRadiusUserList", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("radius-users.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_entity_summary_is_matched_to_its_documented_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}": {
                "get": {"operationId": "getSiteEntity", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-entity.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_iptv_summary_is_matched_to_its_documented_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/service/iptv": {
                "get": {"operationId": "getIptv", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-iptv.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_template_upnp_is_matched_to_its_documented_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sitetemplates/{siteTemplateId}/upnp": {
                "get": {"operationId": "getUpnpSettingTemplate", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-template-upnp.zip", spec)
        row = build_matrix([("cbc", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_template_igmp_is_matched_to_its_documented_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sitetemplates/{siteTemplateId}/setting/service/iptv/igmp": {
                "get": {"operationId": "getIgmpTemplate", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-template-igmp.zip", spec)
        row = build_matrix([("cbc", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_igmp_summary_is_matched_to_its_documented_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/service/igmp": {
                "get": {"operationId": "getIgmp", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-igmp.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_mld_summary_is_matched_to_its_documented_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/service/mld": {
                "get": {"operationId": "getMld", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-mld.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_ssh_summary_is_matched_to_its_documented_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/ssh": {
                "get": {"operationId": "getSshSetting", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-ssh.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_template_ssh_summary_is_matched_to_cbc_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sitetemplates/{siteTemplateId}/ssh": {
                "get": {"operationId": "getSshSettingTemplate", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-template-ssh.zip", spec)
        row = build_matrix([("cbc", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_template_iptv_summary_is_matched_to_cbc_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sitetemplates/{siteTemplateId}/setting/service/iptv/iptv": {
                "get": {"operationId": "getIptvTemplate", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-template-iptv.zip", spec)
        row = build_matrix([("cbc", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_template_iptv_settings_summary_is_matched_to_cbc_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sitetemplates/{siteTemplateId}/setting/service/iptv": {
                "get": {"operationId": "getIptvTemplateServerSetting",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-template-iptv-settings.zip", spec)
        row = build_matrix([("cbc", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_ssl_vpn_summary_is_matched_to_its_documented_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/vpn/ssl-vpn-server/setting": {
                "get": {"operationId": "getSslVpnServerSetting", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-ssl-vpn.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_gre_tunnel_summary_is_matched_to_its_documented_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/vpn/gre-tunnel": {
                "get": {"operationId": "getGreTunnelConfig", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-gre-tunnel.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_upnp_summary_is_matched_to_its_documented_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/upnp": {
                "get": {"operationId": "getUpnpSetting", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-upnp.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_iot_aging_time_is_covered_in_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_iot_aging_time"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")

    def test_site_iot_aging_time_route_matches_source_contract(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/iot/aging-time": {
                "get": {"operationId": "getIotBlueToothAgingTime",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-iot-aging-time.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_iot_radio_route_is_covered_in_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_iot_radio_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/iot/radio": {
                "get": {"operationId": "getIotRadioSetting", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-iot-radio.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_mesh_route_is_covered_in_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_mesh_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/mesh": {
                "get": {"operationId": "getMeshSetting", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-mesh.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_multicast_rate_limit_is_covered_in_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_multicast_rate_limit_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/multicast-rate-limit": {
                "get": {"operationId": "getMulticastRateLimitByOpenApi",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-multicast-rate-limit.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_iot_transmit_power_summary_is_covered_in_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_iot_transmit_power_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/iot/radio/transmit-power": {
                "get": {"operationId": "getIotDeviceTransmitPowerInfoList",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-iot-transmit-power.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_client_connection_summary_is_covered_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_client_connection_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/client-ssid-distribution": {
                "get": {"operationId": "getClientsSsidDistribution",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("client-ssid-distribution.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_poe_usage_summary_is_covered_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_poe_usage_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/poe-usage": {
                "get": {"operationId": "getPoeUsage", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-poe-usage.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_device_counts_summary_is_covered_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_device_counts_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/card/overview": {
                "get": {"operationId": "getCardTopology", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-device-counts.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_ipsec_tunnel_summary_is_covered_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_ipsec_tunnel_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/lpset-tunnel-stats": {
                "get": {"operationId": "getGridDashboardIpsecTunnelStats",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-ipsec-tunnel-stats.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_client_association_time_is_covered_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_client_association_time_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/client-association-time-distribution": {
                "get": {"operationId": "getClientsAssociationTimeDistribution",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("client-association-time.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_network_activity_is_covered_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_network_activity_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/allNetworkActivity": {
                "get": {"operationId": "getAllNetworkActivity", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("network-activity.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_client_rssi_distribution_is_covered_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_client_rssi_distribution_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/client-rssi-distribution": {
                "get": {"operationId": "getClientsRssiDistribution", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("client-rssi-distribution.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_ap_rssi_density_is_covered_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_ap_rssi_density_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/ap-density": {
                "get": {"operationId": "getApDensity", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("ap-density.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_client_attachment_distribution_is_covered_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_client_attachment_distribution_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/client-distribution": {
                "get": {"operationId": "getClientsDistribution", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("client-attachment-distribution.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_client_frequency_distribution_is_covered_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_client_frequency_distribution_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/client-freq-distribution": {
                "get": {"operationId": "getClientsFreqDistribution", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("client-frequency-distribution.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_device_traffic_is_covered_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_device_traffic_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/traffic-distribution": {
                "get": {"operationId": "getTrafficDistribution", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-device-traffic.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_past_client_counts_are_covered_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_past_client_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/past-client-num": {
                "get": {"operationId": "getPastClientNum", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-past-clients.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_current_client_counts_are_covered_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_current_client_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/current-client-num": {
                "get": {"operationId": "getCurrentClientNum", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-current-clients.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_gateway_isp_summary_is_covered_in_all_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_gateway_isp_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/gateway/isp/load": {
                "get": {"operationId": "getGatewayIspLoad", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("gateway-isp-load.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_top_ap_retry_drop_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_top_ap_retry_drop_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/top-aps": {
                "get": {"operationId": "getTop5Aps", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("top-aps.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_arp_detect_status_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_arp_detect_status_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getArpDetectStatus")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/arpDetects/status": {
                "get": {"operationId": "getArpDetectStatus", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("arp-detect-status.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_ap_retry_drop_is_reviewed_against_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["ap_retry_drop"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getRetryAndDroppedRate")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/retry-dropped-rate": {
                "get": {"operationId": "getRetryAndDroppedRate", "parameters": [
                    {"name": "start", "in": "query", "required": True,
                     "schema": {"type": "integer", "format": "int64"}},
                    {"name": "end", "in": "query", "required": True,
                     "schema": {"type": "integer", "format": "int64"}},
                ], "responses": {"200": {}}},
            },
        }
        path = self.write_zip("retry-drop-rate.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_arp_detect_list_remains_open_for_generic_response_schema(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["getGridArpDetects"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getGridArpDetects")
            self.assertIn("no documented result fields", row["contract_review"]["response"])
            self.assertEqual(row["implementation_status"], "deferred_schema_gap")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/arpDetects": {
                "get": {"operationId": "getGridArpDetects", "parameters": [
                    {"name": "page", "in": "query", "required": True,
                     "schema": {"type": "integer", "format": "int32"}},
                    {"name": "pageSize", "in": "query", "required": True,
                     "schema": {"type": "integer", "format": "int32"}},
                ], "responses": {"200": {}}},
            },
        }
        path = self.write_zip("arp-detect-list.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "unknown_not_reviewed")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_disaster_mode_status_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_disaster_mode_status"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getDisasterModeStatus")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/disaster": {
                "get": {"operationId": "getDisasterModeStatus",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-disaster-mode.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_specification_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_specification_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getSiteSpecification")
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/specification": {
                "get": {"operationId": "getSiteSpecification",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-specification.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_portal_logout_domain_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_portal_logout_domain"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getPortalLogoutDomainSetting")
            self.assertIn("domain as a string", row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/portal-logout": {
                "get": {"operationId": "getPortalLogoutDomainSetting",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-portal-logout-domain.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_wids_config_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_wids_config"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getWidsConfig")
            self.assertIn("disagree", row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/network-security/wireless-ids": {
                "get": {"operationId": "getWidsConfig",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-wids-config.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_wips_config_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_wips_config"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getWipsConfig")
            self.assertIn("300–36000", row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/network-security/wireless-ips": {
                "get": {"operationId": "getWipsConfig",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-wips-config.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_acl_config_mode_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_acl_config_mode"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getAclConfigTypeSetting")
            self.assertIn("0 means Through profiles", row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/acls/osg-config-mode": {
                "get": {"operationId": "getAclConfigTypeSetting",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-acl-config-mode.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_attack_defense_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_attack_defense_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getAttackDefenseSetting")
            self.assertIn("specifiedOption", row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/attack-defense": {
                "get": {"operationId": "getAttackDefenseSetting",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-attack-defense.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_alg_config_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_alg_config"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getAlg")
            self.assertIn("sipSignalingTimeout", row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/nat/alg": {
                "get": {"operationId": "getAlg", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-alg-config.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_firewall_settings_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_firewall_settings"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getFirewallSetting")
            self.assertIn("2097151", row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/firewall": {
                "get": {"operationId": "getFirewallSetting",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-firewall-settings.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_firewall_defaults_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_firewall_defaults"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getDefaultFirewallConfig")
            self.assertIn("Network Config Page View Only",
                          row["contract_review"]["permission"])
            self.assertIn("synCookies", row["contract_review"]["response"])
            self.assertIn("does not specify a timeout unit",
                          row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/firewall/timeout/default": {
                "get": {"operationId": "getDefaultFirewallConfig",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-firewall-defaults.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_bandwidth_control_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_bandwidth_control"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getBandwidthCtrl")
            self.assertIn("portUuid", row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/bandwidth-control": {
                "get": {"operationId": "getBandwidthCtrl",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-bandwidth-control.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_wan_ports_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_wan_ports_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getWanPortsConfig")
            self.assertIn("wanPortsConfig", row["contract_review"]["response"])
            self.assertIn("UsbPortsConfig", row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/internet/ports-config": {
                "get": {"operationId": "getWanPortsConfig", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-wan-ports-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_virtual_wan_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_virtual_wan_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getGridVirtualWan")
            self.assertEqual(row["contract_review"]["supporting_operation_id"],
                             "getAvailableVirtualWan")
            self.assertIn("physicalWanId", row["contract_review"]["response"])
            self.assertIn("physicalWanPortId", row["contract_review"]["response"])
            self.assertIn("joins config id", row["contract_review"]["projection"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/virtual-wans": {
                "get": {"operationId": "getGridVirtualWan", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/available-virtual-wans": {
                "get": {"operationId": "getAvailableVirtualWan", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-virtual-wan-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")
        rows = build_matrix([("hardware", path)])['operations']
        available = next(item for item in rows
                         if item["sources"][0].get("operation_id") == "getAvailableVirtualWan")
        self.assertEqual(available["connector_source_status"], "implemented_read")
        self.assertEqual(available["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_gateway_info_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        expected_ids = {
            "Hardware Controller 6.3.0": "getGatewayInfo_1",
            "CBC Standard 6.3.0": "getGatewayInfo_1",
            "ER7212PC 6.2.14": "getGatewayInfo",
        }
        for source in matrix["sources"]:
            row = source["operations"]["gateway_info_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             expected_ids[source["label"]])
            self.assertIn("GatewayInfo defines", row["contract_review"]["response"])
            self.assertIn("HTTP/MCP", row["contract_review"]["projection"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}": {
                "get": {"operationId": "getGatewayInfo_1", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("gateway-info-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_wan_max_speed_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        expected_ids = {
            "Hardware Controller 6.3.0": "getWanPortsMaxSpeed_1",
            "CBC Standard 6.3.0": "getWanPortsMaxSpeed_1",
            "ER7212PC 6.2.14": "getWanPortsMaxSpeed",
        }
        for source in matrix["sources"]:
            row = source["operations"]["site_wan_max_speed_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             expected_ids[source["label"]])
            self.assertIn("upstream", row["contract_review"]["response"])
            self.assertIn("does not specify units", row["contract_review"]["response"])
            self.assertIn("required wanId", row["contract_review"]["response"])
            self.assertIn("one opaque wan_port_ref", row["contract_review"]["projection"])
            self.assertIn("unit unspecified", row["contract_review"]["projection"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/wan-max-speed": {
                "get": {"operationId": "getWanPortsMaxSpeed_1", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-wan-max-speed-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_vlan_network_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_vlan_network_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getGridVlans")
            self.assertIn("purpose", row["contract_review"]["response"])
            self.assertIn("pageSize", row["contract_review"]["query"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/networks/vlans": {
                "get": {"operationId": "getGridVlans", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-vlan-network-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_static_route_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        expected_ids = {
            "Hardware Controller 6.3.0": "getGridStaticRouting_1",
            "CBC Standard 6.3.0": "getGridStaticRouting_1",
            "ER7212PC 6.2.14": "getGridStaticRouting",
        }
        for source in matrix["sources"]:
            row = source["operations"]["site_static_route_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            review = row["contract_review"]
            self.assertEqual(review["operation_id"], expected_ids[source["label"]])
            self.assertEqual(review["query"], {"page": "required int32", "pageSize": "required int32"})
            self.assertIn("routeType", review["response"])
            self.assertIn("interfaceId", review["response"])
            self.assertIn("destinations", review["response"])
            self.assertIn("destination addresses", review["projection"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/routing/static-routings": {
                "get": {"operationId": "getGridStaticRouting_1", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-static-route-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_static_route_interface_options_match_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_static_route_interface_options_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            review = row["contract_review"]
            self.assertEqual(review["operation_id"], "getStaticRoutingInterfaceList")
            self.assertEqual(review["query"], {})
            self.assertIn("interfaceType", review["response"])
            self.assertIn("needNextHop", review["response"])
            self.assertIn("selection options only", review["projection"])

    def test_wlan_group_ssid_config_operation_matches_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_wlan_group_ssid_config_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getSsidDetail")
            self.assertIn("wlanId", row["contract_review"]["path"])

    def test_lte_wan_config_operation_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_lte_wan_config_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getLteWanPortsConfig")
            self.assertIn("ports-config", row["contract_review"]["path"])

    def test_nat_exception_operation_is_hardware_and_cbc_only(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        expected = {"Hardware Controller 6.3.0": True,
                    "CBC Standard 6.3.0": True,
                    "ER7212PC 6.2.14": False}
        for source in matrix["sources"]:
            row = source["operations"]["site_nat_exception_summary"]
            self.assertEqual(row["documented"], expected[source["label"]])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getDisableNatGrid_1")

    def test_switch_dhcp_arp_capability_gap_has_no_safe_row_contract(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            review = source["operations"]["site_switch_dhcp_arp_capabilities_contract_gap"]["contract_review"]
            self.assertEqual(review["dhcp_operation_id"], "getOswsSupportDhcpSnoop")
            self.assertEqual(review["arp_operation_id"], "getOswsSupportArpDetect")
            self.assertIn("generic OperationResponse", review["response"])
            self.assertIn("open_contract_blocker", review["state"])

    def test_site_bridge_device_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            review = source["operations"]["site_bridge_device_summary"]["contract_review"]
            self.assertEqual(review["adopted_operation_id"], "getGridAdoptedBridgeDevicesBySite")
            self.assertEqual(review["pending_operation_id"], "getGridPendingBridgeDevicesBySite")
            self.assertIn("stackData", review["adopted_response"])
            self.assertIn("status", review["pending_response"])

    def test_site_upnp_template_comparison_source_coverage(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            review = source["operations"]["site_upnp_template_comparison"]["contract_review"]
            self.assertEqual(review["site_operation_id"], "getUpnpSetting")
            self.assertEqual(review["shared_fields"],
                             ["enable", "wanPortIds", "networkIds", "supportByDsLiteAndMapE"])
            if source["label"] == "CBC Standard 6.3.0":
                self.assertEqual(review["template_operation_id"], "getUpnpSettingTemplate")
            else:
                self.assertIsNone(review["template_operation_id"])

    def test_site_wan_qos_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            review = source["operations"]["site_wan_qos_summary"]["contract_review"]
            self.assertEqual(review["wan_operation_id"], "getQosWans")
            self.assertEqual(review["rules_operation_id"], "getBandwidthCtrlGrid")
            self.assertIn("configured", review["response"])
            self.assertIn("direction", review["response"])
            self.assertIn("unit is unspecified", review["projection"])

    def test_site_vpn_server_status_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            review = source["operations"]["site_vpn_server_status_summary"]["contract_review"]
            self.assertEqual(review["operation_id"], "getGridVpnServerStatus")
            self.assertEqual(review["query"]["pageSize"], "required int32")
            self.assertIn("filters.vpnType", review["query"])
            self.assertIn("no status-code semantics", review["response"])

    def test_site_ssid_client_count_summary_matches_documented_sources(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            operation = source["operations"]["site_ssid_client_count_summary"]
            if source["label"].startswith("ER7212PC"):
                self.assertFalse(operation["documented"])
                self.assertIsNone(operation["contract_review"]["path"])
                continue
            review = operation["contract_review"]
            self.assertEqual(review["operation_id"], "getGridSsidClients")
            self.assertEqual(review["permission"], "Network Config Page View Only")
            self.assertIn("style=form/explode=true", review["query"]["queryDataVO"])
            self.assertIn("totalRows", review["response"])
            self.assertIn("No online state is inferred", review["projection"])

    def test_controller_upgrade_log_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            review = source["operations"]["controller_upgrade_log_summary"]["contract_review"]
            self.assertEqual(review["operation_id"], "getGridUpgradeLogs")
            self.assertEqual(review["permission"], "Site Manual Firmware Upgrade View Only")
            self.assertIn("pageSize", review["query"])
            self.assertIn("no timestamps, names, ids, versions", review["projection"].lower())

    def test_site_remote_logging_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            review = source["operations"]["site_remote_logging_summary"]["contract_review"]
            self.assertEqual(review["operation_id"], "getRemoteLoggingSetting")
            self.assertIn("Site Settings Manager View Only", review["permission"])
            self.assertIn("remoteLog.enable", review["response"])
            self.assertIn("host and port", review["projection"])

    def test_site_vpn_client_status_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            review = source["operations"]["site_vpn_client_status_summary"]["contract_review"]
            self.assertEqual(review["operation_id"], "getGridVpnClientStatus")
            self.assertIn("0 L2TP, 1 PPTP, 3 OpenVPN, 4 WireGuard", review["query"]["filters.vpnType"])
            self.assertIn("no status-code semantics", review["response"])

    def test_site_ipsec_sa_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            review = source["operations"]["site_ipsec_sa_summary"]["contract_review"]
            self.assertEqual(review["operation_id"], "getGridVpnIpSec")
            self.assertEqual(review["query"], {"page": "required int32", "pageSize": "required int32"})
            self.assertIn("direction", review["response"])
            self.assertIn("connectivity is unknown", review["projection"])

    def test_site_policy_route_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        expected_ids = {"Hardware Controller 6.3.0": "getGridPolicyRouting",
                        "CBC Standard 6.3.0": "getGridPolicyRouting",
                        "ER7212PC 6.2.14": "getGridPolicyRouting"}
        for source in matrix["sources"]:
            review = source["operations"]["site_policy_route_summary"]["contract_review"]
            self.assertEqual(review["operation_id"], expected_ids[source["label"]])
            self.assertEqual(review["query"], {"page": "required int32", "pageSize": "required int32"})
            self.assertIn("sourceType", review["response"])
            self.assertIn("index", review["response"])
            self.assertIn("precedence", review["projection"])

    def test_site_internet_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_internet_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getInternet")
            self.assertIn("credentials", row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/internet": {
                "get": {"operationId": "getInternet", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-internet-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_vpn_session_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_vpn_session_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getGridVpnTunnel")
            self.assertIn("pageSize", row["contract_review"]["query"])
            self.assertIn("downBytes", row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/vpn/stats/tunnel": {
                "get": {"operationId": "getGridVpnTunnel", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-vpn-session-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_dhcp_candidate_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_dhcp_candidate_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getGridSupportVlanNetworkDevicesBySite")
            self.assertIn("DeviceVO", row["contract_review"]["response"])
            self.assertIn("pageSize", row["contract_review"]["query"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/networks/devices": {
                "get": {"operationId": "getGridSupportVlanNetworkDevicesBySite",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-dhcp-candidate-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_network_reservation_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_network_reservation_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getNetworksWithServersForReservation")
            self.assertIn("Site Settings Manager View Only",
                          row["contract_review"]["permission"])
            self.assertIn("serverDevices", row["contract_review"]["response"])
            self.assertIn("ranges", row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/networks/server-for-reservation": {
                "get": {"operationId": "getNetworksWithServersForReservation",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-network-reservation-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_dhcp_reservation_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_dhcp_reservation_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getDhcpReservationGrid")
            self.assertIn("Site Device Manager View Only",
                          row["contract_review"]["permission"])
            self.assertIn("pageSize", row["contract_review"]["query"])
            self.assertIn("MAC/IP", row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/service/dhcp": {
                "get": {"operationId": "getDhcpReservationGrid", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-dhcp-reservation-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_dhcp_snooping_status_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_dhcp_snooping_status"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getDhcpSnoopStatus")
            self.assertIn("dhcpSnoopEnable", row["contract_review"]["response"])
            self.assertIn("Site Settings Manager View Only",
                          row["contract_review"]["permission"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dhcpSnoops/status": {
                "get": {"operationId": "getDhcpSnoopStatus", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-dhcp-snooping-status.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_dhcp_snoops_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_dhcp_snoops_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getGridDhcpSnoops")
            self.assertIn("pageSize", row["contract_review"]["query"])
            self.assertIn("deviceType", row["contract_review"]["response"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/dhcpSnoops": {
                "get": {"operationId": "getGridDhcpSnoops", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-dhcp-snoops-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_snmp_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_snmp_settings_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getSnmpSetting")
            self.assertIn("Network Config Page View Only",
                          row["contract_review"]["permission"])
            self.assertIn("privacyPassword", row["contract_review"]["response"])
            self.assertIn("never returned", row["contract_review"]["projection"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/service/snmp": {
                "get": {"operationId": "getSnmpSetting", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-snmp-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_lan_network_config_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_lan_network_config_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getLanNetworkListV3")
            self.assertIn("deviceType", row["contract_review"]["response"])
            self.assertIn("never returned", row["contract_review"]["projection"])
        spec = document()
        spec["paths"] = {
            "/openapi/v3/{omadacId}/sites/{siteId}/lan-networks": {
                "get": {"operationId": "getLanNetworkListV3", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-lan-network-config-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_internet_load_balance_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        expected_ids = {"Hardware Controller 6.3.0": "getInternetLoadBalance_1",
                        "CBC Standard 6.3.0": "getInternetLoadBalance_1",
                        "ER7212PC 6.2.14": "getInternetLoadBalance"}
        for source in matrix["sources"]:
            row = source["operations"]["site_internet_load_balance_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             expected_ids[source["label"]])
            self.assertIn("virtualWanWeights", row["contract_review"]["response"])
            self.assertIn("IDs", row["contract_review"]["projection"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/internet/load-balance": {
                "get": {"operationId": "getInternetLoadBalance_1", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-internet-load-balance-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_internet_basic_port_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        expected_ids = {"Hardware Controller 6.3.0": "getInternetBasicPortInfo_1",
                        "CBC Standard 6.3.0": "getInternetBasicPortInfo_1",
                        "ER7212PC 6.2.14": "getInternetBasicPortInfo"}
        for source in matrix["sources"]:
            row = source["operations"]["site_internet_basic_port_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             expected_ids[source["label"]])
            self.assertIn("portMode", row["contract_review"]["response"])
            self.assertIn("Port IDs", row["contract_review"]["projection"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/internet/basic-info": {
                "get": {"operationId": "getInternetBasicPortInfo_1", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-internet-basic-port-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_wlan_group_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_wlan_group_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getWlanGroupList")
            self.assertIn("deprecated", row["contract_review"]["response"])
            self.assertIn("IDs", row["contract_review"]["projection"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/wireless-network/wlans": {
                "get": {"operationId": "getWlanGroupList", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-wlan-group-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_wlan_group_ssids_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_wlan_group_ssids_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getSsidList")
            self.assertIn("vlanPoolIds", row["contract_review"]["response"])
            self.assertIn("SSID names", row["contract_review"]["projection"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/wireless-network/wlans/{wlanId}/ssids": {
                "get": {"operationId": "getSsidList", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-wlan-group-ssids-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_mdns_rule_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_mdns_rule_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getMdnsGrid")
            self.assertIn("Site Settings Manager View Only",
                          row["contract_review"]["permission"])
            self.assertIn("OSG", row["contract_review"]["response"])
            self.assertIn("does not infer", row["contract_review"]["projection"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/service/mdns": {
                "get": {"operationId": "getMdnsGrid", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-mdns-rule-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_ddns_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_ddns_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getDdnsGrid")
            self.assertIn("Device Config Page View Only", row["contract_review"]["permission"])
            self.assertIn("supportTpLinkddns:int32", row["contract_review"]["response"])
            self.assertIn("password", row["contract_review"]["response"])
            self.assertIn("Credentials", row["contract_review"]["projection"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/service/ddns": {
                "get": {"operationId": "getDdnsGrid", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-ddns-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_active_ap_and_switch_summaries_match_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        routes = {
            "site_active_ap_summary": ("/openapi/v1/{omadacId}/sites/{siteId}/dashboard/most-active-eaps", "getActiveAps"),
            "site_active_switch_summary": ("/openapi/v1/{omadacId}/sites/{siteId}/dashboard/most-active-switches", "getActiveSwitches"),
        }
        for operation_id, (path_template, source_id) in routes.items():
            for source in matrix["sources"]:
                row = source["operations"][operation_id]
                self.assertTrue(row["documented"])
                self.assertEqual(row["live_support"], "unknown")
            spec = document()
            spec["paths"] = {path_template: {"get": {"operationId": source_id,
                                                        "responses": {"200": {}}}}}
            path = self.write_zip(f"{operation_id}.zip", spec)
            row = build_matrix([("hardware", path)])["operations"][0]
            self.assertEqual(row["connector_source_status"], "implemented_read")
            self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_device_memory_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_device_memory_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        path_template = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/top-device-memory-usage"
        spec["paths"] = {path_template: {"get": {
            "operationId": "getTopMemoryUsageWithTimeRange", "responses": {"200": {}}
        }}}
        path = self.write_zip("device-memory-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_switch_dashboard_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_switch_dashboard_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/switch-summary"
        spec["paths"] = {route: {"get": {
            "operationId": "getSwitchSummary", "responses": {"200": {}}
        }}}
        path = self.write_zip("switch-dashboard-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_ap_interference_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_ap_interference_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/top-interference"
        spec["paths"] = {route: {"get": {
            "operationId": "getInterference", "responses": {"200": {}}
        }}}
        path = self.write_zip("ap-interference-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_application_category_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_application_category_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/categoryInfo"
        spec["paths"] = {route: {"get": {
            "operationId": "getCategoryInfo", "responses": {"200": {}}
        }}}
        path = self.write_zip("application-category-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_category_application_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_category_application_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["permission"],
                             "Site Dashboard Manager View Only")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/categoryAppInfo/{familyId}"
        spec["paths"] = {route: {"get": {
            "operationId": "getCategoryAppInfo", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-category-applications.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_category_client_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_category_client_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["permission"],
                             "Site Dashboard Manager View Only")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/categoryUserInfo/{familyId}"
        spec["paths"] = {route: {"get": {
            "operationId": "getCategoryUserInfo", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-category-clients.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_active_application_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_active_application_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["permission"],
                             "Site Dashboard Manager View Only")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/mostActiveAppTraffic"
        spec["paths"] = {route: {"get": {
            "operationId": "getMostActiveApplications", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-active-applications.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_active_client_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_active_client_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getMostActiveClients")
            self.assertEqual(row["contract_review"]["permission"],
                             "Site Dashboard Manager View Only")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/active-clients"
        spec["paths"] = {route: {"get": {
            "operationId": "getMostActiveClients", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-active-clients.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_cpu_usage_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_cpu_usage_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getTopCpuUsageWithTimeRange")
            self.assertEqual(row["contract_review"]["permission"],
                             "Site Dashboard Manager View Only")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/top-device-cpu-usage"
        spec["paths"] = {route: {"get": {
            "operationId": "getTopCpuUsageWithTimeRange", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-cpu-usage.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_client_bubble_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_client_bubble_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getClientsBubble")
            self.assertEqual(row["contract_review"]["permission"],
                             "Site Dashboard Manager View Only")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/clients-bubble"
        spec["paths"] = {route: {"get": {
            "operationId": "getClientsBubble", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-client-bubble.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_traffic_activity_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_traffic_activity_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getTrafficActivities")
            self.assertEqual(row["contract_review"]["permission"],
                             "Site Dashboard Manager View Only")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/traffic-activities"
        spec["paths"] = {route: {"get": {
            "operationId": "getTrafficActivities", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-traffic-activities.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_isp_load_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_isp_load_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getIspLoad")
            self.assertEqual(row["contract_review"]["permission"],
                             "Site Dashboard Manager View Only")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/isp-load"
        spec["paths"] = {route: {"get": {
            "operationId": "getIspLoad", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-isp-load.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_vpn_tunnel_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_vpn_tunnel_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getGridDashboardTunnelStats")
            self.assertEqual(row["contract_review"]["permission"],
                             "Site Dashboard Manager View Only")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/vpn-tunnel-stats"
        spec["paths"] = {route: {"get": {
            "operationId": "getGridDashboardTunnelStats", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-vpn-tunnel-stats.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_open_vpn_tunnel_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_open_vpn_tunnel_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getGridDashboardOpenVpnTunnelStats")
            self.assertEqual(row["contract_review"]["permission"],
                             "Site Dashboard Manager View Only")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/open-vpn-tunnel-stats"
        spec["paths"] = {route: {"get": {
            "operationId": "getGridDashboardOpenVpnTunnelStats",
            "responses": {"200": {}}
        }}}
        path = self.write_zip("site-open-vpn-tunnel-stats.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_client_activity_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_client_activity_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getClientActivity")
            self.assertEqual(row["contract_review"]["permission"],
                             "Site Dashboard Manager View Only")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/client-activity"
        spec["paths"] = {route: {"get": {
            "operationId": "getClientActivity", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-client-activity.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_client_association_activity_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_client_association_activity_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getClientsAssociationActivities")
            self.assertEqual(row["contract_review"]["permission"],
                             "Site Dashboard Manager View Only")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/client-association-activities"
        spec["paths"] = {route: {"get": {
            "operationId": "getClientsAssociationActivities", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-client-association-activities.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_client_traffic_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_client_traffic_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getClientTraffic")
            self.assertEqual(row["contract_review"]["permission"], "not stated by these exports")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/clientTraffic"
        spec["paths"] = {route: {"get": {
            "operationId": "getClientTraffic", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-client-traffic.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_active_ap_v2_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_active_ap_v2_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getActiveApsV2")
            self.assertEqual(row["contract_review"]["permission"],
                             "not stated by these exports")
        spec = document()
        route = "/openapi/v2/{omadacId}/sites/{siteId}/dashboard/most-active-eaps"
        spec["paths"] = {route: {"get": {
            "operationId": "getActiveApsV2", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-active-aps-v2.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_hotspot_statistics_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_hotspot_statistics_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getHotspotStatistic")
            self.assertEqual(row["contract_review"]["permission"],
                             "not stated by these exports")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/hotspot/dashboard/statistics"
        spec["paths"] = {route: {"get": {
            "operationId": "getHotspotStatistic", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-hotspot-statistics.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_application_access_summaries_match_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            for operation, operation_id in (
                    ("site_allowed_application_summary", "getAllowApp"),
                    ("site_blocked_application_summary", "getBlockApp")):
                row = source["operations"][operation]
                self.assertTrue(row["documented"])
                self.assertEqual(row["live_support"], "unknown")
                self.assertEqual(row["contract_review"]["operation_id"], operation_id)
                self.assertEqual(row["contract_review"]["permission"],
                                 "Site Dashboard Manager View Only")
                self.assertEqual(row["contract_review"]["query"]["start"], "required int64 seconds")
                self.assertIn("100", row["contract_review"]["connector_projection"])
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/allowApp"
        spec["paths"] = {route: {"get": {
            "operationId": "getAllowApp", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-allowed-applications.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_dashboard_tab_summaries_match_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        expected = {
            "site_dashboard_all_tabs_summary": "listAllTabs",
            "site_dashboard_non_overall_tabs_summary": "listTabs",
        }
        for source in matrix["sources"]:
            for key, operation_id in expected.items():
                row = source["operations"][key]
                self.assertTrue(row["documented"])
                self.assertEqual(row["live_support"], "unknown")
                self.assertEqual(row["contract_review"]["operation_id"], operation_id)
                self.assertEqual(row["contract_review"]["permission"],
                                 "Site Dashboard Manager View Only")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/tabs"
        spec["paths"] = {route: {"get": {
            "operationId": "listAllTabs", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-dashboard-tabs.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_specific_app_traffic_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_specific_app_traffic_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getSpecificAppInfo")
            self.assertEqual(row["contract_review"]["permission"],
                             "Site Dashboard Manager View Only")
            self.assertEqual(row["contract_review"]["query"]["applicationId"],
                             "required string; connector allows safe path characters only")
        spec = document()
        route = ("/openapi/v1/{omadacId}/sites/{siteId}/dashboard/"
                 "specificAppInfo/{applicationId}")
        spec["paths"] = {route: {"get": {
            "operationId": "getSpecificAppInfo", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-specific-app-info.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_specific_client_traffic_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_specific_client_traffic_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"], "getSpecificClientInfo")
            self.assertEqual(row["contract_review"]["permission"],
                             "Site Dashboard Manager View Only")
            self.assertEqual(row["contract_review"]["query"]["clientMac"],
                             "required MAC; connector resolves only a fresh opaque client_ref")
        spec = document()
        route = ("/openapi/v1/{omadacId}/sites/{siteId}/dashboard/"
                 "specificClientInfo/{clientMac}")
        spec["paths"] = {route: {"get": {
            "operationId": "getSpecificClientInfo", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-specific-client-info.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_application_traffic_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        for source in matrix["sources"]:
            operation = source["operations"]["site_application_traffic_summary"]
            self.assertTrue(operation["documented"])
            self.assertEqual(operation["live_support"], "unknown")
            self.assertEqual(operation["contract_review"]["operation_id"],
                             "getApplicationControlTraffics")
            self.assertEqual(operation["contract_review"]["tag"], "Application Control")
            self.assertIn("trailing 24-hour", operation["contract_review"]["query"]["dateEnd"])

    def test_site_wifi_calling_top_ssid_reader_has_common_bounded_seconds_contract(self) -> None:
        self.assertEqual(
            IMPLEMENTED[("GET", "/openapi/v1/{controller_id}/sites/{site_id}/profiles/wifi-calling/grid/summary")],
            "implemented_read",
        )
        path = Path(__file__).resolve().parents[1] / "docs/CONTRACT_MATRIX.json"
        matrix = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        for source in matrix["sources"]:
            operation = source["operations"]["site_wifi_calling_top_ssid_summary"]
            self.assertTrue(operation["documented"])
            self.assertEqual(operation["live_support"], "unknown")
            review = operation["contract_review"]
            self.assertEqual(review["operation_id"], "getGridWifiCallingTrafficResult")
            self.assertEqual(review["query"]["queryTopSsid"], True)
            self.assertEqual(review["query"]["queryTopEPDG"], False)
            self.assertEqual(review["query"]["queryClients"], False)
            self.assertEqual(review["query"]["queryClientsByMac"], False)
            self.assertIn("int64 Unix seconds", review["query"]["filters.timeStart"])
            self.assertIn("topKSsids", review["response"])
            self.assertIn("no unit stated", review["response"])
            self.assertIn("No server-completeness", review["connector_projection"])

    def test_site_wan_lan_status_summary_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        expected_ids = {
            "Hardware Controller 6.3.0": "checkWanLanStatus_1",
            "ER7212PC 6.2.14": "checkWanLanStatus",
            "CBC Standard 6.3.0": "checkWanLanStatus_1",
        }
        for source in matrix["sources"]:
            operation = source["operations"]["site_wan_lan_status_summary"]
            self.assertTrue(operation["documented"])
            self.assertEqual(operation["live_support"], "unknown")
            self.assertEqual(operation["contract_review"]["operation_id"],
                             expected_ids[source["label"]])
            self.assertEqual(operation["contract_review"]["tag"], "Wired Network")
        spec = document()
        route = "/openapi/v1/{omadacId}/sites/{siteId}/wan-lan-status"
        spec["paths"] = {route: {"get": {
            "operationId": "checkWanLanStatus_1", "responses": {"200": {}}
        }}}
        path = self.write_zip("site-wan-lan-status.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_controller_gateway_wan_status_matches_all_source_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        for source in matrix["sources"]:
            operation = source["operations"]["controller_gateway_wan_status_summary"]
            self.assertTrue(operation["documented"])
            self.assertEqual(operation["live_support"], "unknown")
            self.assertEqual(operation["contract_review"]["operation_id"],
                             "getSpecifiedGatewayInfos")
            self.assertEqual(operation["contract_review"]["tag"], "Gateway")
        spec = document()
        route = "/openapi/v1/{omadacId}/global/gateways/wan-status"
        spec["paths"] = {route: {"get": {
            "operationId": "getSpecifiedGatewayInfos",
            "parameters": [
                {"name": "page", "in": "query", "required": True,
                 "schema": {"type": "integer", "format": "int32"}},
                {"name": "pageSize", "in": "query", "required": True,
                 "schema": {"type": "integer", "format": "int32"}},
            ], "responses": {"200": {}}
        }}}
        path = self.write_zip("controller-gateway-wan-status.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_device_tag_summary_is_matched_to_its_documented_get(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/devices/tag": {
                "get": {"operationId": "getTags", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("site-device-tags.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_global_device_summaries_match_documented_gets_and_keep_live_unknown(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/devices/known-devices": {
                "get": {"operationId": "getGlobalKnownDeviceList", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/devices/unknown-devices": {
                "get": {"operationId": "getGlobalUnknownDeviceList", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/devices/batch/info": {
                "get": {"operationId": "getAdoptAbleDevicesForGlobalBatchAdopt", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/grid/devices/pending": {
                "get": {"operationId": "getGridPendingDevicesBySite", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("global-device-summaries.zip", spec)
        rows = build_matrix([("hardware", path)])["operations"]
        self.assertEqual([row["connector_source_status"] for row in rows],
                         ["implemented_read"] * 4)
        self.assertTrue(all(row["live_status"] == "unknown_not_checked_by_this_offline_tool"
                            for row in rows))
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            for operation in ("controller_known_devices", "controller_unknown_devices",
                              "controller_device_batch_adopt_summary", "site_pending_devices_summary"):
                self.assertTrue(source["operations"][operation]["documented"])
                self.assertEqual(source["operations"][operation]["live_support"], "unknown")

    def test_site_device_tag_read_is_documented_in_all_sources_and_live_unknown(self):
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_device_tag_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")

    def test_site_unresolved_incident_count_is_a_mapped_read_without_live_claim(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/anomaly/unresolved-incidents": {
                "get": {"operationId": "getUnresolvedIncidentCount", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("incident-count.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_incident_overview_is_a_mapped_read_without_live_claim(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/anomaly/overview/statistics": {
                "get": {"operationId": "getOverviewStatistics", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("incident-overview.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_incident_distribution_is_a_mapped_read_without_live_claim(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/anomaly/overview/incident-distribution": {
                "get": {"operationId": "getIncidentDistribution", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("incident-distribution.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_incident_category_counts_are_a_mapped_read_without_live_claim(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/anomaly/category": {
                "get": {"operationId": "getCategoryEventCount", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("incident-categories.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_incident_notification_is_a_mapped_read_without_live_claim(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/anomaly/notification": {
                "get": {"operationId": "getNotificationTemplate", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("incident-notification.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_anomaly_event_settings_is_a_mapped_read_without_live_claim(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/anomaly/setting": {
                "get": {"operationId": "getAnomalyEventSettingForSite",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("anomaly-settings.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_incident_influences_are_documented_reads_without_live_claim(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/anomaly/{mac}/influencing-clients": {
                "get": {"operationId": "getInfluencingClients", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/anomaly/{mac}/influencing-devices": {
                "get": {"operationId": "getInfluencingDevices", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("incident-influences.zip", spec)
        rows = build_matrix([("hardware", path)])["operations"]
        self.assertEqual([row["connector_source_status"] for row in rows],
                         ["implemented_read", "implemented_read"])
        self.assertTrue(all(row["live_status"] == "unknown_not_checked_by_this_offline_tool"
                            for row in rows))

    def test_site_wireless_group_capacity_reads_are_mapped(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/wireless-network/cmd/countWlans": {
                "get": {"operationId": "countWlans", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/count-ap-groups": {
                "get": {"operationId": "countApGroups", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("wireless-group-capacity.zip", spec)
        rows = build_matrix([("hardware", path)])['operations']
        self.assertEqual([row["connector_source_status"] for row in rows],
                         ["implemented_read", "implemented_read"])
        self.assertTrue(all(row["live_status"] == "unknown_not_checked_by_this_offline_tool"
                            for row in rows))

    def test_site_incident_list_is_a_mapped_read_without_live_claim(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/anomaly/incidents": {
                "get": {"operationId": "getGridIncidentList", "responses": {"200": {}}},
            },
        }
        path = self.write_zip("incident-list.zip", spec)
        row = build_matrix([("hardware", path)])['operations'][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_batch_interference_history_is_a_mapped_read_without_live_claim(self) -> None:
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/full-channel-detect/grid/scan-history": {
                "get": {"operationId": "getGridFullChannelDetectHistory",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("batch-interference-history.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_ap_ssid_override_audit_is_present_only_in_hardware_and_cbc_exports(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["ap_ssid_override_audit_summary"]
            expected = source["label"] != "ER7212PC 6.2.14"
            self.assertEqual(row["documented"], expected)
            self.assertEqual(row["live_support"], "unknown")
            if expected:
                self.assertEqual(row["contract_review"]["operation_id"],
                                 "getApSsidOverridesAuditLogs")
                self.assertIn("default", row["contract_review"]["query"])
                self.assertIn("no timestamp", row["contract_review"]["response"])
                self.assertIn("omits SSID names, VLAN values",
                              row["contract_review"]["projection"])
        spec = document()
        spec["paths"] = {
            "/openapi/v1/{omadacId}/sites/{siteId}/audit-logs/{apMac}/ssid-overrides": {
                "get": {"operationId": "getApSsidOverridesAuditLogs",
                        "responses": {"200": {}}},
            },
        }
        path = self.write_zip("ap-ssid-override-audit-summary.zip", spec)
        row = build_matrix([("hardware", path)])["operations"][0]
        self.assertEqual(row["connector_source_status"], "implemented_read")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")

    def test_site_stack_dhcp_user_contract_is_common_and_live_unknown(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_stack_dhcp_user_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getGridStackDhcpUserList")
            self.assertIn("0=Device", row["contract_review"]["response"])
            self.assertIn("1=Static Binding", row["contract_review"]["response"])

    def test_switch_oui_vlan_contract_documents_er7212_platform_limit(self) -> None:
        matrix = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/CONTRACT_MATRIX.json").read_text(encoding="utf-8"))
        for source in matrix["sources"]:
            row = source["operations"]["site_switch_oui_vlan_summary"]
            self.assertTrue(row["documented"])
            self.assertEqual(row["live_support"], "unknown")
            self.assertEqual(row["contract_review"]["operation_id"],
                             "getGridSwitchOuiBasedVlan")
        er7212 = matrix["sources"][2]["operations"]["site_switch_oui_vlan_summary"]
        self.assertIn("Omada Pro", er7212["contract_review"]["platform_limit"])

    def test_new_explicit_adapter_examples_are_mapped_without_live_claims(self) -> None:
        paths = {
            "/openapi/v1/{omadacId}/sites/{siteId}/wifi/sub/health/timeline": {
                "get": {"operationId": "wifiSubhealth", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/antenna-gain": {
                "get": {"operationId": "antennaGain", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/power-saving": {
                "get": {"operationId": "powerSaving", "responses": {"200": {}}},
            },
            "/openapi/v2/{omadacId}/sites/{siteId}/aps/{apMac}/vlan": {
                "get": {"operationId": "apVlan", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/port-vlans": {
                "get": {"operationId": "getApPortVlans", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/bridge": {
                "get": {"operationId": "getApBridgeInfo", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/grid/mesh/candiParents": {
                "get": {"operationId": "getGridMeshCandiParentsForAdopt", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/general-config": {
                "get": {"operationId": "getGeneralConfig_2", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/ip-setting": {
                "get": {"operationId": "getIpSettingConfig", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/ipv6-setting": {
                "get": {"operationId": "getIpv6SettingConfig", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/p2pInfo": {
                "get": {"operationId": "getApP2pInfo", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/paring-window-result": {
                "get": {"tags": ["Access Point"], "operationId": "getParingWindowResult"}
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/management-wlan": {
                "get": {"tags": ["Ap"], "operationId": "getApManagementSsidConfig"}
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/snmp": {
                "get": {"tags": ["Ap"], "operationId": "getApSnmpConfig"}
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/vlan": {
                "get": {"tags": ["Ap"], "operationId": "getApVlanConfig"}
            },
            "/openapi/v2/{omadacId}/sites/{siteId}/aps/{apMac}/override": {
                "get": {"tags": ["Ap"], "operationId": "getWlansConfigV2"}
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/lag": {
                "get": {"tags": ["Ap"], "operationId": "getApLagConfig"}
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/rf-scan-result": {
                "get": {"operationId": "getRFScanResult", "responses": {"200": {}}}
            },
            "/openapi/v2/{omadacId}/sites/{siteId}/aps/{apMac}/rf-scan-result": {
                "get": {"operationId": "getRFScanResultV2", "responses": {"200": {}}}
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/l3access": {
                "get": {"operationId": "getApL3AccessConfig", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/wired-uplink": {
                "get": {"operationId": "apWiredUplink", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/wired-downlink": {
                "get": {"operationId": "getDownlinkWiredDevices", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/available-channel": {
                "get": {"operationId": "getAvailableChannel", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}/lan-status": {
                "get": {"operationId": "getLanStatus", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}/ports": {
                "get": {"operationId": "getPorts", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}/speedTestResult": {
                "get": {"operationId": "getSpeedTestV2Result", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}/dhcp/user-list": {
                "get": {"operationId": "getGridDhcpUserList_1", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}/internet": {
                "get": {"operationId": "getIpptInternet", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switches/ports/counters": {
                "get": {"operationId": "switchPortCounters", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switches/ports/poe-info": {
                "get": {"operationId": "switchPortPoeInfo", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}/health/timeline": {
                "get": {"operationId": "gatewayHealthTimeline", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switches/{switchMac}/health/timeline": {
                "get": {"operationId": "switchHealthTimeline", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switches/{switchMac}/sdm-used": {
                "get": {"operationId": "getSwitchUsedSdmNum", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/cable-test/switches/{switchMac}/logs": {
                "get": {"operationId": "getCableTestLogs", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/cable-test/switches/{switchMac}/full-results": {
                "get": {"operationId": "getCableTestFullResults", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/cable-test/switches/{switchMac}/increment-results": {
                "get": {"operationId": "getCableTestIncrementResults", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/cable-test/switches/{switchMac}/ports": {
                "get": {"operationId": "getCableTestOswPorts", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switches/{switchMac}/dhcp/user-list": {
                "get": {"operationId": "getSwitchDhcpUserList", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switches/{switchMac}/ospf-neighbors": {
                "get": {"operationId": "getSwitchOspfNeighborList", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switches/{switchMac}/port-lag-networks": {
                "get": {"operationId": "getSwitchPortLagNetworks", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switches/{switchMac}/exist-network": {
                "get": {"operationId": "getSwitchExistNetworks", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switches/{switchMac}/networks": {
                "get": {"operationId": "listSwitchNetworks", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switches/{switchMac}/interfaces/brief": {
                "get": {"operationId": "listSwitchBriefInterfaces", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switches/{switchMac}/routingTable": {
                "get": {"operationId": "getGridOswRoutingTable", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switches/{switchMac}/staticRoutings": {
                "get": {"operationId": "getGridStaticRouting", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/setting/speedTest": {
                "get": {"operationId": "getSpeedTestV2Setting", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/uplink-config": {
                "get": {"operationId": "getApUplinkConfig", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/eaps/{apMac}/health/timeline": {
                "get": {"operationId": "apHealthTimeline", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switches/{switchMac}/ports/{port}/name": {
                "put": {"operationId": "switchPortName", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/applicationControl/status": {
                "get": {"operationId": "dpiStatus", "responses": {"200": {}}},
                "put": {"operationId": "dpiStatusUpdate", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/qos/gateway/voip-prioritization": {
                "get": {"operationId": "gatewayVoip", "responses": {"200": {}}},
                "put": {"operationId": "gatewayVoipUpdate", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/qos/gateway/tag-outbound-traffic": {
                "get": {"operationId": "gatewayTagQos", "responses": {"200": {}}},
                "put": {"operationId": "gatewayTagQosUpdate", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/clients/{clientMac}/health/timeline": {
                "get": {"operationId": "clientHealthTimeline", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/health/client/timeline": {
                "get": {"operationId": "siteClientHealthTimeline", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/dashboard/wifi-summary": {
                "get": {"operationId": "getWifiSummary", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/controller/setting/client-recognition": {
                "get": {"operationId": "getClientRecognitionEnable", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/devices/stat": {
                "get": {"operationId": "getGridAdoptedDevicesStatByGlobal", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/controller/setting/active-timeout": {
                "get": {"operationId": "getClientActiveTimeout", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/controller/setting/ui-interface": {
                "get": {"operationId": "getUiInterface", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/controller/setting/retention": {
                "get": {"operationId": "getRetention", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/dst-info": {
                "get": {"operationId": "getOmadacDstInfo", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/global/controller/setting/exp-improve": {
                "get": {"operationId": "getExpImprove", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/client-detail-information": {
                "get": {"operationId": "getClientDetailInformationSetting", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/global/controller/setting/general": {
                "get": {"operationId": "getGernalSettings", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switch-support": {
                "get": {"operationId": "getSiteSupportSwitchInfo", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/networks/{networkId}/dhcp-server/capabilities": {
                "get": {"operationId": "getDhcpServerDevCapForNetwork", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/networks/{networkId}/dhcp-server-info": {
                "get": {"operationId": "getDhcpServerInfoForNetwork", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/speed-test-result": {
                "get": {"operationId": "getSpeedTestResults", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/ports": {
                "get": {"operationId": "getApPortList", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/lldp": {
                "get": {"operationId": "getApLldpConfig", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/insight/rogueaps": {
                "get": {"operationId": "getRogueApResults", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/clients/{clientMac}/client-history": {
                "get": {"operationId": "clientHistory", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/lan-traffic-info": {
                "get": {"operationId": "apLanTraffic", "responses": {"200": {}}},
            },
            "/openapi/v1/{omadacId}/sites/{siteId}/switches/{switchMac}/ports/{port}/status": {
                "put": {"operationId": "switchPortStatus", "responses": {"200": {}}},
            },
        }
        spec = self.write_zip("new-adapters.zip", {
            "openapi": "3.0.3", "info": {"title": "Synthetic", "version": "1"},
            "paths": paths,
        })
        report = build_matrix([("synthetic", spec)])
        rows = {(row["method"], row["canonical_path"]): row for row in report["operations"]}
        expected = {
            ("GET", "/openapi/v1/{}/controller/setting/client-recognition"): "implemented_read",
            ("GET", "/openapi/v1/{}/devices/stat"): "implemented_read",
            ("GET", "/openapi/v1/{}/controller/setting/active-timeout"): "implemented_read",
            ("GET", "/openapi/v1/{}/controller/setting/ui-interface"): "implemented_read",
            ("GET", "/openapi/v1/{}/controller/setting/retention"): "implemented_read",
            ("GET", "/openapi/v1/{}/dst-info"): "implemented_read",
            ("GET", "/openapi/v1/{}/global/controller/setting/exp-improve"): "implemented_read",
            ("GET", "/openapi/v1/{}/client-detail-information"): "implemented_read",
            ("GET", "/openapi/v1/{}/global/controller/setting/general"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/wifi/sub/health/timeline"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/aps/{}/antenna-gain"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/aps/{}/power-saving"): "implemented_read",
            ("GET", "/openapi/v2/{}/sites/{}/aps/{}/vlan"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/aps/{}/wired-uplink"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/aps/{}/wired-downlink"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/aps/{}/ports"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/aps/{}/lldp"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/insight/rogueaps"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/aps/{}/available-channel"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/gateways/{}/lan-status"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/gateways/{}/ports"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/gateways/{}/speedTestResult"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/gateways/{}/dhcp/user-list"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/gateways/{}/internet"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/switches/ports/counters"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/switches/ports/poe-info"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/gateways/{}/health/timeline"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/setting/speedTest"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/aps/{}/uplink-config"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/eaps/{}/health/timeline"): "implemented_read",
            ("PUT", "/openapi/v1/{}/sites/{}/switches/{}/ports/{}/name"):
                "implemented_controlled_write_unverified_live",
            ("GET", "/openapi/v1/{}/sites/{}/applicationControl/status"): "implemented_read",
            ("PUT", "/openapi/v1/{}/sites/{}/applicationControl/status"):
                "implemented_controlled_write_unverified_live",
            ("GET", "/openapi/v1/{}/sites/{}/qos/gateway/voip-prioritization"): "implemented_read",
            ("PUT", "/openapi/v1/{}/sites/{}/qos/gateway/voip-prioritization"):
                "implemented_controlled_write_unverified_live",
            ("GET", "/openapi/v1/{}/sites/{}/qos/gateway/tag-outbound-traffic"): "implemented_read",
            ("PUT", "/openapi/v1/{}/sites/{}/qos/gateway/tag-outbound-traffic"):
                "implemented_controlled_write_unverified_live",
            ("GET", "/openapi/v1/{}/sites/{}/clients/{}/health/timeline"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/health/client/timeline"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/dashboard/wifi-summary"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/switch-support"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/networks/{}/dhcp-server/capabilities"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/networks/{}/dhcp-server-info"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/aps/{}/speed-test-result"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/clients/{}/client-history"): "implemented_read",
            ("GET", "/openapi/v1/{}/sites/{}/aps/{}/lan-traffic-info"): "implemented_read",
            ("PUT", "/openapi/v1/{}/sites/{}/switches/{}/ports/{}/status"):
                "implemented_controlled_write_unverified_live",
        }
        for key, status in expected.items():
            with self.subTest(key=key):
                self.assertEqual(rows[key]["connector_source_status"], status)
                self.assertEqual(rows[key]["live_status"],
                                 "unknown_not_checked_by_this_offline_tool")

    def test_unmapped_route_is_unknown_not_reviewed_not_not_implemented(self) -> None:
        spec = self.write_zip("unknown.zip", {
            "openapi": "3.0.3", "info": {"title": "Synthetic", "version": "1"},
            "paths": {"/openapi/v1/{omadacId}/novel-route": {
                "get": {"operationId": "novel", "responses": {"200": {}}},
            }},
        })
        report = build_matrix([("synthetic", spec)])
        row = report["operations"][0]
        self.assertEqual(row["connector_source_status"], "unknown_not_reviewed")
        self.assertEqual(row["live_status"], "unknown_not_checked_by_this_offline_tool")


if __name__ == "__main__":
    unittest.main()
