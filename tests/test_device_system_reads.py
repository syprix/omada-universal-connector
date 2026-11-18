from __future__ import annotations

import unittest
from unittest.mock import patch

from app.device_adopt_result import project_device_adopt_result
from app.device_link_topology import project_device_link_topology
from app.device_mac_type import project_device_mac_type
from app.device_radsec_support import project_device_radsec_support
from app.device_upgrade_result import project_device_upgrade_result
from app.device_timeline import project_device_timeline
from app.olt_detail import OltDetailError, project_olt_detail
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class DeviceSystemProjectionTests(unittest.TestCase):
    def test_adopt_result_redacts_mac_and_checks_documented_codes(self) -> None:
        result = project_device_adopt_result({
            "deviceMac": "00:11:22:33:44:55", "adoptErrorCode": -39003,
            "adoptFailedType": -2,
        }, "00-11-22-33-44-55")
        self.assertEqual(result["data"], {
            "adopt_error_code": -39003, "credentials_required": True,
            "present_count": 3, "missing_count": 0, "invalid_count": 0,
            "unknown_field_count": 0,
        })
        self.assertNotIn("00:11:22:33:44:55", str(result))
        invalid = project_device_adopt_result({
            "deviceMac": "00:11:22:33:44:55", "adoptErrorCode": 7,
            "adoptFailedType": -2,
        }, "00:11:22:33:44:55")
        self.assertEqual(invalid["data"]["present_count"], 2)
        self.assertEqual(invalid["data"]["invalid_count"], 1)
        self.assertTrue(invalid["partial"])

    def test_mac_type_has_only_boolean_and_known_type(self) -> None:
        self.assertEqual(project_device_mac_type({"device": True, "deviceType": "AP"}), {
            "data": {"is_device": True, "device_type": "ap", "present_count": 2,
                     "missing_count": 0, "invalid_count": 0, "unknown_field_count": 0},
            "partial": False,
        })
        bad = project_device_mac_type({"device": 1, "deviceType": "private"})
        self.assertEqual(bad["data"]["invalid_count"], 2)
        self.assertTrue(bad["partial"])

    def test_topology_projects_bounded_aggregates_only(self) -> None:
        result = project_device_link_topology([{
            "mac": "00:11:22:33:44:55", "name": "private ap", "ip": "192.0.2.1",
            "clientCount": 2, "ipcCount": 1, "disconnected": False,
            "healthScore": 90,
            "clientHealth": {"good": 2, "fair": 0, "poor": 0, "noData": 0},
            "successors": [{"mac": "00:11:22:33:44:66", "clientCount": 1,
                            "ipcCount": 0, "disconnected": True,
                            "clientHealth": {"good": 1, "fair": 0, "poor": 0, "noData": 0},
                            "successors": []}],
        }])
        self.assertEqual(result["data"]["node_count"], 2)
        self.assertEqual(result["data"]["edge_count"], 1)
        self.assertEqual(result["data"]["direct_client_count"], 3)
        self.assertEqual(result["data"]["disconnected_device_count"], 1)
        self.assertNotIn("00:11:22", str(result))
        self.assertNotIn("private ap", str(result))
        self.assertNotIn("192.0.2.1", str(result))

    def test_topology_enforces_node_limit(self) -> None:
        with self.assertRaises(ValueError):
            project_device_link_topology([{} for _ in range(257)])

    def test_radsec_projection_returns_only_the_documented_boolean(self) -> None:
        self.assertEqual(project_device_radsec_support({"exist": True}), {
            "data": {"unsupported_devices_exist": True, "present_count": 1,
                     "missing_count": 0, "invalid_count": 0,
                     "unknown_field_count": 0}, "partial": False,
        })
        self.assertTrue(project_device_radsec_support({"exist": 1})["partial"])
        with self.assertRaises(ValueError):
            project_device_radsec_support({"exist": True, "devices": ["private"]})

    def test_upgrade_result_requires_strict_booleans(self) -> None:
        result = project_device_upgrade_result({"finished": True, "success": False})
        self.assertEqual(result["data"]["finished"], True)
        self.assertEqual(result["data"]["success"], False)
        self.assertFalse(result["partial"])
        self.assertTrue(project_device_upgrade_result({"finished": "yes"})["partial"])

    def test_device_timeline_returns_only_bounded_duration_aggregates(self) -> None:
        result = project_device_timeline({"connections": [
            {"start": 100, "end": 200, "duration": 5_000},
            {"start": 200, "end": 300, "duration": 7_000},
        ]})
        self.assertEqual(result["data"], {"interval_count": 2, "online_duration_ms": 12_000,
                                          "missing_duration_count": 0, "invalid_count": 0,
                                          "unknown_field_count": 0})
        self.assertNotIn("start", str(result))
        self.assertTrue(project_device_timeline({"connections": [{"start": 1}]})["partial"])
        unknown = project_device_timeline({"connections": [{"duration": 5, "newField": "private"}]})
        self.assertTrue(unknown["partial"])
        self.assertNotIn("private", str(unknown))
        with self.assertRaises(ValueError):
            project_device_timeline({"connections": [
                {} for _ in range(501)]})

    def test_olt_detail_summary_keeps_diagnostics_and_redacts_identifiers(self) -> None:
        result = project_olt_detail({
            "type": "olt", "model": "OLT-Model", "firmwareVersion": "v1",
            "hwVersion": "v2", "status": 14, "statusCategory": 1,
            "cpuUtil": 20, "memUtil": 30, "uptimeLong": 1000, "onuCount": 12,
            "down": 100, "up": 200, "downlinkList": [{"mac": "private-mac"}],
            "name": "private-name", "sn": "private-serial", "ip": "192.0.2.8",
            "siteName": "private-site", "location": {"address": "private-address"},
        })
        self.assertEqual(result["data"], {
            "status_code": 14, "status_category_code": 1, "cpu_percent": 20,
            "memory_percent": 30, "uptime_seconds": 1000, "onu_count": 12,
            "traffic_down_bytes": 100, "traffic_up_bytes": 200, "model": "OLT-Model",
            "firmware_version_present": True, "hardware_version_present": True,
            "downlink_count": 1,
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["redacted_field_count"], 5)
        for private in ("private-mac", "private-name", "private-serial", "192.0.2.8",
                        "private-site", "private-address", "v1", "v2"):
            self.assertNotIn(private, repr(result))

    def test_olt_detail_summary_checks_bounds_codes_and_unknown_fields(self) -> None:
        with self.assertRaises(OltDetailError):
            project_olt_detail([])
        result = project_olt_detail({"type": "olt", "model": "x", "status": 99,
                                     "statusCategory": 1, "cpuUtil": True, "memUtil": 0,
                                     "uptimeLong": 1, "onuCount": 1, "down": 1, "up": 2,
                                     "firmwareVersion": "v", "hwVersion": "v",
                                     "downlinkList": [], "privateExtra": "discard"})
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("discard", repr(result))


class DeviceSystemReadAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.device_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._inventory_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00-11-22-33-44-55"}
        self.client._olt_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00:11:22:33:44:55"}

    def test_each_read_uses_inventory_mac_and_fixed_path(self) -> None:
        cases = (
            (self.client.read_device_adopt_result,
             "/openapi/v1/ctrl/sites/site_1/devices/00-11-22-33-44-55/adopt-result",
             {"deviceMac": "00-11-22-33-44-55", "adoptErrorCode": 0, "adoptFailedType": -1},
             "device_adopt_result"),
            (self.client.read_device_mac_type,
             "/openapi/v1/ctrl/sites/site_1/devices/00-11-22-33-44-55/check-mac-type",
             {"device": True, "deviceType": "switch"}, "device_mac_type"),
            (self.client.read_device_link_topology,
             "/openapi/v2/ctrl/sites/site_1/devices/00-11-22-33-44-55/device-link-topology",
             [{"clientCount": 1, "ipcCount": 0, "disconnected": False,
               "clientHealth": {"good": 1, "fair": 0, "poor": 0, "noData": 0},
               "successors": []}], "device_link_topology"),
            (self.client.read_device_upgrade_result,
             "/openapi/v1/ctrl/sites/site_1/devices/00-11-22-33-44-55/online-upgrade-result",
             {"finished": True, "success": False}, "device_upgrade_result"),
            (self.client.read_device_timeline,
             "/openapi/v1/ctrl/sites/site_1/devices/00-11-22-33-44-55/timeline?start=1699913600&end=1700000000",
             {"connections": [{"start": 1699913600000, "end": 1700000000000,
                               "duration": 86_400_000}]}, "device_timeline"),
            (self.client.read_olt_system_info,
             "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/system/system-info/configs",
             {"deviceName": "private-olt", "mac": "00:11:22:33:44:55",
              "runningTime": 10, "sshStatus": 1}, "olt_system_info"),
            (self.client.read_olt_detail_summary,
             "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55",
             {"type": "olt", "model": "OLT-Model", "firmwareVersion": "v1",
              "hwVersion": "v2", "status": 14, "statusCategory": 1,
              "cpuUtil": 20, "memUtil": 30, "uptimeLong": 1000, "onuCount": 12,
              "down": 100, "up": 200, "downlinkList": []}, "olt_detail_summary"),
            (self.client.read_olt_management_interfaces,
             "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/system/management-system-interface/get",
             {"systemInterfaces": [{"interfaceId": 0, "interfaceType": "MANAGEMENT",
                                     "interfaceValue": "192.0.2.1"}]},
             "olt_management_interfaces"),
        )
        for method, expected_path, upstream_result, resource in cases:
            calls = []
            def request(verb, path, **_kwargs):
                calls.append((verb, path))
                return {"result": upstream_result}
            time_patch = patch("app.openapi.time.time", return_value=1_700_000_000)
            with self.subTest(resource=resource), time_patch, \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", side_effect=request):
                response = method(self.site_ref, self.device_ref)
            self.assertEqual(calls, [("GET", expected_path)])
            self.assertEqual(response["resource"], resource)
            self.assertEqual(response["device_ref"], self.device_ref)

    def test_msp_olt_system_info_uses_fixed_msp_customer_path_and_redacted_projection(self) -> None:
        calls = []
        def request(verb, path, **_kwargs):
            calls.append((verb, path))
            return {"result": {"deviceName": "private-olt", "mac": "00:11:22:33:44:55",
                               "runningTime": 12, "sshStatus": 1}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.read_olt_system_info_msp(
                "msp-1", "customer-2", self.site_ref, self.device_ref)
        self.assertEqual(calls, [("GET", "/openapi/v1/msp/msp-1/customers/customer-2/"
                                  "sites/site_1/olts/00-11-22-33-44-55/system/system-info/configs")])
        self.assertEqual(result["resource"], "olt_system_info_msp")
        self.assertEqual(result["data"]["deviceName_present"], True)
        self.assertNotIn("private-olt", str(result))
        self.assertNotIn("00:11:22:33:44:55", str(result))
        for invalid in ("../escape", "customer/1", "", "x" * 129):
            with self.subTest(invalid=invalid), patch.object(self.client, "_request_json") as request:
                with self.assertRaises(OpenApiError):
                    self.client.read_olt_system_info_msp(invalid, "customer-2", self.site_ref, self.device_ref)
                request.assert_not_called()

    def test_olt_reads_require_an_inventoried_olt_type(self) -> None:
        self.client._olt_macs_by_site_ref[self.site_ref] = {}
        with patch.object(self.client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "device_type_unsupported"):
                self.client.read_olt_system_info(self.site_ref, self.device_ref)
            with self.assertRaisesRegex(OpenApiError, "device_type_unsupported"):
                self.client.read_olt_detail_summary(self.site_ref, self.device_ref)
        request.assert_not_called()

    def test_olt_upstream_paths_are_fixed_and_controller_bound(self) -> None:
        info = ("/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
                "system/system-info/configs")
        interfaces = ("/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
                      "system/management-system-interface/get")
        self.assertTrue(self.client._olt_system_info_request_valid(info))
        detail = "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55"
        self.assertTrue(self.client._olt_detail_request_valid(detail))
        self.assertFalse(self.client._olt_detail_request_valid(detail.replace("ctrl", "other")))
        self.assertFalse(self.client._olt_detail_request_valid(detail + "?path=/private"))
        msp_info = ("/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/olts/"
                    "00-11-22-33-44-55/system/system-info/configs")
        self.assertTrue(self.client._olt_system_info_msp_request_valid(msp_info))
        self.assertFalse(self.client._olt_system_info_msp_request_valid(msp_info.replace("msp-1", "../msp")))
        self.assertTrue(self.client._olt_management_interfaces_request_valid(interfaces))
        self.assertFalse(self.client._olt_system_info_request_valid(info.replace("ctrl", "other")))
        self.assertFalse(self.client._olt_system_info_request_valid(info + "?path=/private"))

    def test_olt_runtime_evidence_is_bound_to_site_and_device_refs(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"sshStatus": 1}}):
            self.client.read_olt_system_info(self.site_ref, self.device_ref)
        self.assertIn(("olt_system_info", self.site_ref + ":" + self.device_ref),
                      self.client._capability_evidence)
    def test_reads_reject_unknown_refs_before_request(self) -> None:
        for method in (self.client.read_device_adopt_result,
                       self.client.read_device_mac_type,
                       self.client.read_device_link_topology):
            with self.subTest(method=method.__name__), \
                    patch.object(self.client, "_request_json") as request, \
                    self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
                method(self.site_ref, "c" * 24)
            request.assert_not_called()

    def test_request_allowlist_binds_controller_and_rejects_other_methods(self) -> None:
        allowed = (
            "/openapi/v1/ctrl/sites/site_1/devices/00-11-22-33-44-55/adopt-result",
            "/openapi/v1/ctrl/sites/site_1/devices/00-11-22-33-44-55/check-mac-type",
            "/openapi/v2/ctrl/sites/site_1/devices/00-11-22-33-44-55/device-link-topology",
            "/openapi/v1/ctrl/sites/site_1/devices/un-support-radsec",
            "/openapi/v1/ctrl/sites/site_1/devices/00-11-22-33-44-55/online-upgrade-result",
            "/openapi/v1/ctrl/sites/site_1/devices/00-11-22-33-44-55/timeline?start=1699913600&end=1700000000",
            "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55",
            "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/system/system-info/configs",
            "/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/system/management-system-interface/get",
        )
        allowed = allowed + ("/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/olts/00-11-22-33-44-55/system/system-info/configs",)
        for path in allowed:
            with self.subTest(path=path), patch.object(
                    self.client, "_connection", side_effect=OpenApiError("connection_reached")):
                with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                    self.client._request_json("GET", path)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("POST", allowed[0])
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", allowed[0].replace("/ctrl/", "/other/"))

    def test_radsec_site_read_uses_exact_controller_bound_path(self) -> None:
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"exist": False}}) as request:
            result = self.client.read_device_radsec_support(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/devices/un-support-radsec", token="token")
        self.assertEqual(result["data"]["unsupported_devices_exist"], False)


if __name__ == "__main__":
    unittest.main()
