from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
