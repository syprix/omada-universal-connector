from __future__ import annotations

import unittest
from datetime import datetime as RealDateTime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_controller_overview_returns_only_aggregates_and_safe_status(self) -> None:
        payload = {"result": {"totalGatewayNum": 2, "connectedGatewayNum": 1,
            "disconnectedGatewayNum": 1, "totalSwitchNum": 3, "connectedSwitchNum": 3,
            "totalApNum": 5, "connectedApNum": 4, "isolatedApNum": 1,
            "totalClientNum": 40, "wirelessClientNum": 35, "wiredClientNum": 5,
            "siteNum": 2, "cloudAccessStatus": 1, "privateName": "secret"}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_controller_health()
        request.assert_called_once_with("GET", "/openapi/v1/ctrl/dashboard/overview-without-client", token="token")
        self.assertEqual(result["data"]["cloud_access"], "connected")
        self.assertEqual(result["data"]["gateways_disconnected"], 1)
        self.assertEqual(result["data"]["clients_total"], 40)
        self.assertEqual(len(result["controller_ref"]), 24)
        self.assertNotIn("privateName", str(result))
        self.assertEqual(next(x for x in self.client.capabilities()["items"]
                              if x["operation"] == "controller_health")["runtime_evidence"][0]["result"],
                         "success")

    def test_site_summary_and_24h_score_timeline(self) -> None:
        overview = {"result": {"totalApNum": 4, "connectedApNum": 3, "totalSwitchNum": 2,
            "totalClientNum": 25, "wirelessClientNum": 20, "wiredClientNum": 5,
            "netCapacity": 1000, "netUsage": 65.5, "powerConsumption": 22.2,
            "name": "private", "ip": "192.0.2.1"}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=overview):
            summary = self.client.read_site_overview(self.site_ref)
        self.assertEqual(summary["data"]["network_usage_percent"], 65.5)
        self.assertEqual(summary["data"]["aps_connected"], 3)
        self.assertNotIn("192.0.2.1", str(summary))
        now = 1_800_000_000_000
        timeline_payload = {"result": {"scores": [{"time": now - 1000,
            "siteHealthScore": 95, "deviceHealthScore": 90, "clientHealthScore": 80,
            "wifiHealthScore": 85, "wanHealthScore": 99,
            "scoreDetail": {"secret": "not exposed"}}]}}
        calls = []
        def request(method, path, **kwargs):
            calls.append(path)
            return timeline_payload
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = RealDateTime.fromtimestamp(now / 1000, timezone.utc)
            timeline = self.client.read_site_health_timeline(self.site_ref)
        self.assertTrue(OmadaOpenApiClient._SITE_HEALTH_TIMELINE_REQUEST.fullmatch(calls[0]))
        self.assertEqual(timeline["window_end_ms"] - timeline["window_start_ms"], 86_400_000)
        self.assertEqual(timeline["items"][0]["site_health_score"], 95)
        self.assertNotIn("scoreDetail", str(timeline))
        self.assertEqual(next(x for x in self.client.capabilities()["items"]
                              if x["operation"] == "site_health_timeline")["runtime_evidence"][0]["result"],
                         "success")

    def test_invalid_status_and_score_rejected(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"cloudAccessStatus": 3}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_controller_health()
        now = 1_800_000_000_000
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"scores": [
                    {"time": now, "siteHealthScore": 101}]}}), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = RealDateTime.fromtimestamp(now / 1000, timezone.utc)
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_health_timeline(self.site_ref)

    def test_live_observed_minus_one_and_boundary_are_explicit(self) -> None:
        now = 1_800_000_000_000
        payload = {"result": {"scores": [
            {"time": now - 86_400_001, "siteHealthScore": -1},
            {"time": now - 1000, "siteHealthScore": -1, "wifiHealthScore": 80},
        ]}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = RealDateTime.fromtimestamp(now / 1000, timezone.utc)
            result = self.client.read_site_health_timeline(self.site_ref)
        self.assertEqual(result["discarded_outside_window"], 1)
        self.assertEqual(result["count"], 1)
        self.assertIsNone(result["items"][0]["site_health_score"])
        self.assertEqual(result["items"][0]["unclassified_minus_one_fields"], ["site_health_score"])
        self.assertEqual(result["items"][0]["wifi_health_score"], 80)

    def test_site_client_health_timeline_uses_fixed_window_and_projects_categories(self) -> None:
        now = 1_800_000_000_000
        payload = {"result": {"scores": [{
            "time": now - 1_000,
            "scoreDetail": {"goodCount": 12, "averageCount": 3,
                            "poorCount": 2, "noDataCount": 1},
        }]}}
        calls = []

        def request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return payload

        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = RealDateTime.fromtimestamp(now / 1000, timezone.utc)
            result = self.client.read_site_client_health_timeline(self.site_ref)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "GET")
        self.assertTrue(OmadaOpenApiClient._SITE_CLIENT_HEALTH_TIMELINE_REQUEST.fullmatch(
            calls[0][1]))
        self.assertEqual(result["data"]["scores"][0]["score_detail"], {
            "good_count": 12, "average_count": 3, "poor_count": 2, "no_data_count": 1,
        })
        self.assertEqual(result["window_end_ms"] - result["window_start_ms"], 86_400_000)

    def test_site_client_health_timeline_rejects_invalid_count_shape(self) -> None:
        now = 1_800_000_000_000
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "scores": [{"time": now, "scoreDetail": {"goodCount": "2"}}]}}), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = RealDateTime.fromtimestamp(now / 1000, timezone.utc)
            result = self.client.read_site_client_health_timeline(self.site_ref)
        self.assertTrue(result["partial"])
        self.assertNotIn("score_detail", result["data"]["scores"][0])

    def test_site_client_health_timeline_is_fixed_to_exact_read_path(self) -> None:
        allowed = "/openapi/v1/ctrl/sites/site_1/health/client/timeline?start=1&end=86400001"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        for path in (allowed + "&extra=1",
                     allowed.replace("ctrl", "other"),
                     allowed.replace("86400001", "86400002")):
            with self.subTest(path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)

    def test_experience_index_uses_fixed_path_and_projects_existing_scan(self) -> None:
        payload = {"result": {"lastScan": [{
            "time": 1_800_000_000_000, "beforeIndex": 60, "afterIndex": 82,
            "isAppliedSuccess": True, "apNum": 9, "length": 31, "mode": 0,
        }]}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_experience_index(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/experienceIndex", token="token")
        self.assertEqual(result["data"]["last_scan"][0]["after_index"], 82)

    def test_experience_index_upstream_path_is_exact_and_controller_bound(self) -> None:
        allowed = "/openapi/v1/ctrl/sites/site_1/experienceIndex"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        for path in (allowed + "?extra=1", allowed.replace("ctrl", "other"),
                     allowed + "/extra"):
            with self.subTest(path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)

    def test_rf_planning_result_reads_status_without_returning_planning_id(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "planningHistroyId": "private-plan", "status": 0,
                    "beforeIndex": 61, "afterIndex": 80, "failType": 0,
                }}) as request:
            result = self.client.read_rf_planning_result(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/rfPlanning/result", token="token")
        self.assertEqual(result["data"]["after_index"], 80)
        self.assertNotIn("private-plan", repr(result))

    def test_rf_planning_result_upstream_path_is_fixed(self) -> None:
        allowed = "/openapi/v1/ctrl/sites/site_1/rfPlanning/result"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        for path in (allowed + "?extra=1", allowed.replace("ctrl", "other"),
                     allowed + "/extra"):
            with self.subTest(path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)

    def test_rf_planning_dashboard_uses_fixed_path_and_redacts_ap_identity(self) -> None:
        dashboard = {"wlanOptDashBoardDetail2g": {
            "cciCurrentDetail": {
                "currentHighCciInfoList": [{"name": "private-ap"}],
                "currentMediumCciInfoList": [], "currentLowCciInfoList": [],
                "noDataList": [],
            }}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": dashboard}) as request:
            result = self.client.read_rf_planning_dashboard(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/rfPlanning/dashboard/status", token="token")
        counts = result["data"]["bands"]["2g"]["cci_current_ap_counts"]
        self.assertEqual(counts["high"], 1)
        self.assertNotIn("private-ap", repr(result))

    def test_rf_planning_dashboard_upstream_path_is_fixed(self) -> None:
        allowed = "/openapi/v1/ctrl/sites/site_1/rfPlanning/dashboard/status"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        for path in (allowed + "?extra=1", allowed.replace("ctrl", "other"),
                     allowed + "/extra"):
            with self.subTest(path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)

    def test_rf_planning_detail_reads_stored_result_and_redacts_device_names(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "time": 1_800_000_000_000, "successDevices": 1, "failDevices": 0,
                    "data": [{"name": "private-ap", "optimizeSuccess": True,
                              "radio2g": {"origChan": "1", "rcmdChan": "6"}}],
                }}) as request:
            result = self.client.read_rf_planning_detail(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/rfPlanning", token="token")
        self.assertEqual(result["data"]["success_device_count"], 1)
        self.assertNotIn("private-ap", repr(result))

    def test_rf_planning_detail_upstream_path_is_fixed(self) -> None:
        allowed = "/openapi/v1/ctrl/sites/site_1/rfPlanning"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        for path in (allowed + "?extra=1", allowed.replace("ctrl", "other"),
                     allowed + "/extra"):
            with self.subTest(path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)

    def test_rf_planning_history_requests_one_fixed_redacted_page(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 1, "currentPage": 1, "currentSize": 100,
                    "data": [{"planningHistroyId": "private-id", "afterIndex": 78}],
                }}) as request:
            result = self.client.read_rf_planning_history(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/planningHistory?page=1&pageSize=100",
            token="token")
        self.assertEqual(result["data"]["items"][0]["after_index"], 78)
        self.assertRegex(result["data"]["items"][0]["history_ref"], r"^[0-9a-f]{24}$")
        self.assertNotIn("private-id", repr(result))

    def test_rf_planning_history_upstream_path_is_fixed(self) -> None:
        allowed = "/openapi/v1/ctrl/sites/site_1/planningHistory?page=1&pageSize=100"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        for path in (allowed + "&extra=1", allowed.replace("ctrl", "other"),
                     allowed.replace("pageSize=100", "pageSize=101")):
            with self.subTest(path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)

    def test_rf_planning_history_detail_requires_list_reference_and_redacts_ap_identity(self) -> None:
        radio = {"origChan": "36", "rcmdChan": "40", "origChanWidth": "80",
                 "rcmdChanWidth": "40", "origPower": 18, "rcmdPower": 15,
                 "origBand": 1, "rcmdBand": 1, "errCode": 0}
        detail = {"channelDeployEnable": True, "channelWidthDeployEnable": True,
                  "bandDeployEnable": False, "powerAdjustEnable": True,
                  "time": 1_800_000_000_000, "currentConfig": 1,
                  "successDevices": 1, "failDevices": 0,
                  "data": [{"name": "private-ap", "ip": "192.0.2.4",
                            "optimizeSuccess": True, "support5g2": False,
                            "radio2g": radio, "radio5g": radio, "radio5g2": radio,
                            "radio6g": radio, "failMsg": "private message",
                            "failMsgType": -1, "triggerReason": 0}]}
        list_result = {"result": {"totalRows": 1, "currentPage": 1, "currentSize": 100,
                                   "data": [{"planningHistroyId": "history_1", "time": 100}]}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json",
                             side_effect=[list_result, {"result": detail}]) as request:
            listed = self.client.read_rf_planning_history(self.site_ref)
            history_ref = listed["data"]["items"][0]["history_ref"]
            result = self.client.read_rf_planning_history_detail(self.site_ref, history_ref)
        self.assertEqual(request.call_args_list[1].args,
                         ("GET", "/openapi/v1/ctrl/sites/site_1/planningHistory/history_1"))
        self.assertEqual(result["resource"], "rf_planning_history_detail")
        self.assertEqual(result["data"]["aps"][0]["radio5g"]["rcmd_chan"], "40")
        for private in ("history_1", "private-ap", "192.0.2.4", "private message"):
            self.assertNotIn(private, repr(result))
        with self.assertRaisesRegex(OpenApiError, "history_ref_unknown"):
            other = OmadaOpenApiClient(OpenApiConfig(
                "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
            other._site_ids_by_ref[self.site_ref] = "site_1"
            other.read_rf_planning_history_detail(self.site_ref, history_ref)

    def test_rf_planning_history_detail_path_accepts_only_safe_ids(self) -> None:
        allowed = "/openapi/v1/ctrl/sites/site_1/planningHistory/history_1"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        for path in (allowed + "?extra=1", allowed.replace("ctrl", "other"),
                     allowed + "/nested", allowed.replace("history_1", "bad%2fid")):
            with self.subTest(path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)

    def test_rf_planning_recent_history_uses_fixed_thirty_day_window(self) -> None:
        now_ms = int(RealDateTime.now(timezone.utc).timestamp() * 1000)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "totalRows": 1, "currentPage": 1, "currentSize": 100,
                    "data": [{"time": now_ms - 1000, "afterIndex": 75}],
                }}) as request:
            result = self.client.read_rf_planning_recent_history(self.site_ref)
        method, path = request.call_args.args
        self.assertEqual(method, "GET")
        self.assertEqual(path.split("?", 1)[0],
                         "/openapi/v1/ctrl/sites/site_1/planningHistoryByTime")
        query = dict(part.split("=", 1) for part in path.split("?", 1)[1].split("&"))
        self.assertEqual(query["currentPage"], "1")
        self.assertEqual(query["currentPageSize"], "100")
        self.assertEqual(int(query["end"]) - int(query["start"]), 30 * 86_400_000)
        self.assertEqual(request.call_args.kwargs, {"token": "token"})
        self.assertEqual(result["data"]["items"][0]["after_index"], 75)
        self.assertEqual(result["window_start_ms"], int(query["start"]))
        self.assertEqual(result["window_end_ms"], int(query["end"]))

    def test_rf_planning_recent_history_upstream_query_is_fixed(self) -> None:
        base = "/openapi/v1/ctrl/sites/site_1/planningHistoryByTime"
        end_ms = 1_800_000_000_000
        start_ms = end_ms - 30 * 86_400_000
        allowed = (f"{base}?currentPage=1&currentPageSize=100&start={start_ms}&end={end_ms}")
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        for path in (allowed + "&extra=1", allowed.replace("ctrl", "other"),
                     allowed.replace("currentPageSize=100", "currentPageSize=1000"),
                     allowed.replace(f"start={start_ms}", f"start={start_ms + 1}")):
            with self.subTest(path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)

    def test_rf_planning_dashboard_history_uses_fixed_redacted_day(self) -> None:
        end = int(RealDateTime.now(timezone.utc).timestamp() * 1000)
        payload = {"wlanOptDashBoardDetail2g": {
            "cciTrendDetail": {"cciTrendItemList": [{
                "time": end - 1000, "strongInterferenceApNum": 1,
                "strongInterferenceApPercent": 10, "moderateInterferenceApNum": 2,
                "moderateInterferenceApPercent": 20, "weakInterferenceApNum": 3,
                "weakInterferenceApPercent": 30,
            }]},
            "cciCurrentDetail": {"currentHighCciInfoList": [{"name": "private", "mac": "secret"}],
                                 "currentMediumCciInfoList": [], "currentLowCciInfoList": [],
                                 "noDataList": []},
            "apDensityTrendDetail": {"apDensityItemList": []},
            "apDensityCurrentDetail": {"currentApDensityHighInfo": [],
                                        "currentApDensityMediumInfo": [],
                                        "currentApDensityLowInfo": [], "noDataList": []},
        }}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": payload}) as request:
            result = self.client.read_rf_planning_dashboard_history(self.site_ref)
        method, path = request.call_args.args
        self.assertEqual(method, "GET")
        base, query_string = path.split("?", 1)
        self.assertEqual(base, "/openapi/v1/ctrl/sites/site_1/rfPlanning/dashboard/history")
        query = dict(part.split("=", 1) for part in query_string.split("&"))
        self.assertEqual(int(query["end"]) - int(query["start"]), 86_400_000)
        self.assertEqual(result["window_start_ms"], int(query["start"]))
        self.assertEqual(result["window_end_ms"], int(query["end"]))
        self.assertNotIn("private", repr(result))
        self.assertNotIn("secret", repr(result))

    def test_rf_planning_dashboard_history_rejects_unbounded_query(self) -> None:
        end = 1_800_000_000_000
        start = end - 86_400_000
        allowed = (f"/openapi/v1/ctrl/sites/site_1/rfPlanning/dashboard/history"
                   f"?start={start}&end={end}")
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        for path in (allowed + "&extra=1", allowed.replace("ctrl", "other"),
                     allowed.replace(f"start={start}", f"start={start + 1}")):
            with self.subTest(path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)

    def test_rf_planning_dashboard_current_uses_legacy_fixed_path(self) -> None:
        payload = {"wlanOptDashBoardDetail2g": {
            "cciTrendDetail": {"cciTrendItemList": []},
            "cciCurrentDetail": {"currentHighCciInfoList": [],
                                 "currentMediumCciInfoList": [], "currentLowCciInfoList": [],
                                 "noDataList": []},
            "apDensityTrendDetail": {"apDensityItemList": []},
            "apDensityCurrentDetail": {"currentApDensityHighInfo": [],
                                        "currentApDensityMediumInfo": [],
                                        "currentApDensityLowInfo": [], "noDataList": []},
        }}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": payload}) as request:
            result = self.client.read_rf_planning_dashboard_current(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/rfPlanning/dashboard", token="token")
        self.assertEqual(result["resource"], "rf_planning_dashboard_current")

    def test_rf_planning_dashboard_current_path_is_controller_bound(self) -> None:
        allowed = "/openapi/v1/ctrl/sites/site_1/rfPlanning/dashboard"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        for path in (allowed + "?extra=1", allowed.replace("ctrl", "other"),
                     allowed + "/unknown"):
            with self.subTest(path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)

    def test_rf_deploy_history_reads_the_documented_boolean(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"firstDeploy": False}}) as request:
            result = self.client.read_rf_deploy_history(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/rfplanning/history", token="token")
        self.assertEqual(result["data"], {"first_deployment": False})

    def test_rf_deploy_history_path_is_exact_and_controller_bound(self) -> None:
        allowed = "/openapi/v1/ctrl/sites/site_1/rfplanning/history"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        for path in (allowed + "?extra=1", allowed.replace("ctrl", "other"), allowed + "/more"):
            with self.subTest(path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)

    def test_rf_excluded_aps_refreshes_inventory_and_returns_opaque_refs(self) -> None:
        ap_ref = "b" * 24

        def inventory(site_ref):
            self.client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA:BB:CC:DD:EE:FF"}
            return {"status": "ok", "resource": "devices", "count": 1, "items": []}

        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "list_devices", side_effect=inventory) as inventory_call, \
                patch.object(self.client, "_request_json", return_value={"result": [{
                    "mac": "AA:BB:CC:DD:EE:FF", "name": "private", "ip": "192.0.2.1",
                    "unsupportType": 1, "statusCategory": 0, "addedInAdvanced": False,
                }]}) as request:
            result = self.client.read_rf_excluded_aps(self.site_ref)
        inventory_call.assert_called_once_with(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/rfPlanning/excludeAps", token="token")
        self.assertEqual(result["items"][0]["ap_ref"], ap_ref)
        for private in ("AA:BB:CC:DD:EE:FF", "private", "192.0.2.1"):
            self.assertNotIn(private, repr(result))

    def test_rf_excluded_aps_path_is_exact_and_controller_bound(self) -> None:
        allowed = "/openapi/v1/ctrl/sites/site_1/rfPlanning/excludeAps"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", allowed)
        for path in (allowed + "?extra=1", allowed.replace("ctrl", "other"),
                     allowed + "/extra"):
            with self.subTest(path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)

    def test_exact_documented_get_paths_only(self) -> None:
        allowed = ["/openapi/v1/ctrl/dashboard/overview-without-client",
                   "/openapi/v1/ctrl/sites/site_1/dashboard/overview-diagram",
                   "/openapi/v1/ctrl/sites/site_1/health/timeline?start=1&end=2",
                   "/openapi/v1/ctrl/sites/site_1/health/client/timeline?start=1&end=86400001"]
        for path in allowed:
            with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
                with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                    self.client._request_json("GET", path)
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("POST", path)
        for path in (allowed[-1] + "&secret=1", allowed[-1].replace("86400001", "2")):
            with self.subTest(path=path), self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path)


if __name__ == "__main__":
    unittest.main()
