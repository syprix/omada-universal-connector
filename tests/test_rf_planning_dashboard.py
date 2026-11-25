from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig
from app.rf_planning_dashboard import (
    RfPlanningDashboardError,
    project_rf_planning_dashboard,
)


def band_fixture():
    return {
        "cciTrendDetail": {"cciTrendItemList": [{
            "time": 1_800_000_000_000,
            "strongInterferenceApNum": 2, "strongInterferenceApPercent": 20,
            "moderateInterferenceApNum": 3, "moderateInterferenceApPercent": 30,
            "weakInterferenceApNum": 5, "weakInterferenceApPercent": 50,
        }]},
        "cciCurrentDetail": {
            "currentHighCciInfoList": [{"name": "private-ap", "mac": "AA:BB:CC:DD:EE:FF"}],
            "currentMediumCciInfoList": [], "currentLowCciInfoList": [],
            "noDataList": [],
        },
        "apDensityTrendDetail": {"apDensityItemList": [{
            "time": 1_800_000_000_000,
            "denseApNum": 1, "denseApPercent": 10,
            "moderateApNum": 4, "moderateApPercent": 40,
            "sparseApNum": 5, "sparseApPercent": 50,
        }]},
        "apDensityCurrentDetail": {
            "currentApDensityHighInfo": [], "currentApDensityMediumInfo": [],
            "currentApDensityLowInfo": [{"name": "private-ap", "mac": "AA:BB:CC:DD:EE:FF"}],
            "noDataList": [],
        },
    }


class RfPlanningDashboardTests(unittest.TestCase):
    def test_projects_bounded_trends_and_aggregate_counts(self) -> None:
        result = project_rf_planning_dashboard({"wlanOptDashBoardDetail2g": band_fixture()})
        self.assertTrue(result["partial"])  # 5 GHz and 6 GHz details were absent.
        band = result["data"]["bands"]["2g"]
        self.assertEqual(band["cci_trend"][0]["strong_interference_ap_num"], 2)
        self.assertEqual(band["cci_current_ap_counts"], {
            "high": 1, "medium": 0, "low": 0, "no_data": 0,
        })
        self.assertEqual(band["ap_density_current_counts"], {
            "high": 0, "medium": 0, "low": 1, "no_data": 0,
        })
        self.assertNotIn("private-ap", repr(result))
        self.assertNotIn("AA:BB:CC:DD:EE:FF", repr(result))

    def test_invalid_trend_values_and_unknown_fields_mark_partial(self) -> None:
        raw = band_fixture()
        raw["cciTrendDetail"]["cciTrendItemList"][0]["strongInterferenceApNum"] = True
        raw["cciCurrentDetail"]["currentHighCciInfoList"][0]["unknown"] = "secret"
        result = project_rf_planning_dashboard({"wlanOptDashBoardDetail2g": raw})
        self.assertTrue(result["partial"])
        self.assertIn("unknown_fields", result["omitted_fields"])
        self.assertGreaterEqual(result["omitted_field_count"], 2)
        self.assertNotIn("secret", repr(result))

    def test_size_limits_fail_closed(self) -> None:
        raw = {"wlanOptDashBoardDetail2g": band_fixture()}
        raw["wlanOptDashBoardDetail2g"]["cciTrendDetail"]["cciTrendItemList"] = [{}] * 257
        with self.assertRaises(RfPlanningDashboardError):
            project_rf_planning_dashboard(raw)
        with self.assertRaises(RfPlanningDashboardError):
            project_rf_planning_dashboard({f"extra{i}": i for i in range(25)})

    def test_history_window_filters_trend_points_and_redacts_current_rows(self) -> None:
        raw = {"wlanOptDashBoardDetail2g": band_fixture()}
        raw["wlanOptDashBoardDetail2g"]["cciTrendDetail"]["cciTrendItemList"][0]["time"] = 100
        raw["wlanOptDashBoardDetail2g"]["cciTrendDetail"]["cciTrendItemList"].append({
            "time": 50, "strongInterferenceApNum": 0, "strongInterferenceApPercent": 0,
            "moderateInterferenceApNum": 0, "moderateInterferenceApPercent": 0,
            "weakInterferenceApNum": 0, "weakInterferenceApPercent": 0,
        })
        result = project_rf_planning_dashboard(raw, start_ms=90, end_ms=110)
        band = result["data"]["bands"]["2g"]
        self.assertEqual(len(band["cci_trend"]), 1)
        self.assertEqual(band["cci_trend"][0]["time_ms"], 100)
        self.assertTrue(result["partial"])
        self.assertIn("out_of_window_trend_points", result["omitted_fields"])
        self.assertNotIn("private-ap", repr(result))
        self.assertNotIn("AA:BB:CC:DD:EE:FF", repr(result))

    def test_window_coverage_excludes_measurement_fields_from_dropped_points(self) -> None:
        raw = {"wlanOptDashBoardDetail2g": band_fixture()}
        cci = raw["wlanOptDashBoardDetail2g"]["cciTrendDetail"]["cciTrendItemList"]
        cci[0] = {"time": 99}
        cci.append({"time": 200, "strongInterferenceApNum": 1,
                    "strongInterferenceApPercent": 10,
                    "moderateInterferenceApNum": 2, "moderateInterferenceApPercent": 20,
                    "weakInterferenceApNum": 7, "weakInterferenceApPercent": 70})
        density = raw["wlanOptDashBoardDetail2g"]["apDensityTrendDetail"]["apDensityItemList"]
        density[0]["time"] = 201

        bounded = project_rf_planning_dashboard(raw, start_ms=100, end_ms=200)
        band = bounded["data"]["bands"]["2g"]
        self.assertEqual([p["time_ms"] for p in band["cci_trend"]], [200])
        self.assertEqual(band["ap_density_trend"], [])
        self.assertFalse(any("cciTrendItemList[0]." in field
                             for field in bounded["missing_fields"]))
        self.assertEqual(bounded["omitted_field_count"], 2)
        self.assertIn("out_of_window_trend_points", bounded["omitted_fields"])

        unbounded = project_rf_planning_dashboard(raw)
        self.assertEqual(len(unbounded["data"]["bands"]["2g"]["cci_trend"]), 2)
        self.assertTrue(any("cciTrendItemList[0].strongInterferenceApNum" in field
                            for field in unbounded["missing_fields"]))

    def test_window_keeps_missing_and_invalid_timestamp_handling(self) -> None:
        raw = {"wlanOptDashBoardDetail2g": band_fixture()}
        points = raw["wlanOptDashBoardDetail2g"]["cciTrendDetail"]["cciTrendItemList"]
        valid = points[0]
        points[:] = [{k: v for k, v in valid.items() if k != "time"},
                     {**valid, "time": True}, {**valid, "time": 99},
                     {**valid, "time": 100}]

        result = project_rf_planning_dashboard(raw, start_ms=100, end_ms=200)
        self.assertEqual([p["time_ms"] for p in
                          result["data"]["bands"]["2g"]["cci_trend"]], [100])
        self.assertEqual(result["omitted_field_count"], 5)
        self.assertIn("missing_trend_time", result["omitted_fields"])
        self.assertIn("invalid_trend_values", result["omitted_fields"])

    def test_current_dashboard_uses_fixed_24_hour_query_and_guard(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref = "a" * 24
        client._site_ids_by_ref[site_ref] = "site_1"
        current = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
        end_ms = int(current.timestamp() * 1000)
        start_ms = end_ms - 86_400_000
        expected_path = (
            "/openapi/v1/ctrl/sites/site_1/rfPlanning/dashboard"
            f"?start={start_ms}&end={end_ms}")
        with patch("app.openapi.datetime") as mocked_datetime, \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json",
                             return_value={"result": {"wlanOptDashBoardDetail2g": band_fixture()}}) as request:
            mocked_datetime.now.return_value = current
            result = client.read_rf_planning_dashboard_current(site_ref)
        request.assert_called_once_with("GET", expected_path, token="token")
        self.assertTrue(client._rf_planning_dashboard_current_request_valid(expected_path))
        self.assertFalse(client._rf_planning_dashboard_current_request_valid(
            expected_path.replace(f"end={end_ms}", f"end={end_ms + 1}")))
        self.assertEqual(result["window_start_ms"], start_ms)
        self.assertEqual(result["window_end_ms"], end_ms)


if __name__ == "__main__":
    unittest.main()
