from __future__ import annotations

import unittest

from app.ap_health import ApHealthProjectionError, project_ap_health_detail
from tools.wifi_diagnose import CliError, _ap_health_data


class ApHealthProjectionTests(unittest.TestCase):
    def test_projects_documented_values_and_redacts_incident_details(self) -> None:
        start, end = 1_700_000_000_000, 1_700_086_400_000
        private = "00:11:22:33:44:55"
        source = {
            "score": 91,
            "cpu": {"summaryScore": 88, "support": True, "averageNum": 12,
                    "pastNums": [{"time": start + 5, "pastNum": 14}],
                    "incidents": [{"incidentId": "secret", "macs": [private],
                                   "titleParams": {"name": "private"}}]},
            "memory": {"averageNum": -1},
            "incident": {"summaryScore": 75, "support": True, "incidentNum": 3,
                         "incidents": [{"incidentId": "private-id"}]},
            "channelUtil": {"averageNum2g": 25, "averageNum5g": -1,
                            "pastNums2g": [{"time": start - 1, "pastNum": 7},
                                           {"time": start - 2, "pastNum": 8},
                                           {"time": end, "pastNum": 10}]},
            "supportedChannelInterf": {"averageNoiseFloor": -95,
                                       "pastNoiseFloor": [{"time": end + 1, "pastNum": -90}]},
            "transmission": {"averageNumTxRetry": 2,
                             "pastNumsTxRetry": [{"time": start + 10, "pastNum": -1},
                                                 {"time": start + 20, "pastNum": 4}],
                             "pastNumsTxDrop": []},
            "name": "private AP", "ip": "192.0.2.1", "rawText": "secret text",
        }

        projected = project_ap_health_detail(source, start, end)

        self.assertEqual(projected["score"], 91)
        self.assertEqual(projected["cpu"]["average"], 12)
        self.assertEqual(projected["cpu"]["values"], [{"time_ms": start + 5, "value": 14}])
        self.assertEqual(projected["cpu"]["incidents_count"], 1)
        self.assertEqual(projected["incident"]["incident_count"], 3)
        self.assertEqual(projected["channel_utilization"]["values_2g"],
                         [{"time_ms": end, "value": 10}])
        self.assertEqual(projected["channel_utilization"]["discarded_out_of_window_points"], 2)
        self.assertNotIn("average_5g", projected["channel_utilization"])
        self.assertEqual(projected["supported_channel_interference"]["average_noise_floor"], -95)
        self.assertEqual(projected["supported_channel_interference"]["noise_floor_values"], [])
        self.assertEqual(projected["supported_channel_interference"]["discarded_out_of_window_points"], 1)
        self.assertEqual(projected["transmission"]["tx_retry_values"],
                         [{"time_ms": start + 20, "value": 4}])
        self.assertEqual(projected["unclassified_minus_one_fields"],
                         ["memory.average", "channel_utilization.average_5g",
                          "transmission.tx_retry_values[0]"])
        rendered = str(projected)
        for forbidden in (private, "secret", "private-id", "private AP", "192.0.2.1", "rawText"):
            self.assertNotIn(forbidden, rendered)

    def test_rejects_bad_shapes_and_bounds_arrays(self) -> None:
        with self.assertRaises(ApHealthProjectionError):
            project_ap_health_detail({"cpu": {"pastNums": [
                {"time": 100, "pastNum": 0}] * 257}}, 0, 100)
        with self.assertRaises(ApHealthProjectionError):
            project_ap_health_detail({"score": True}, 0, 100)
        with self.assertRaises(ApHealthProjectionError):
            project_ap_health_detail({"cpu": {"support": 1}}, 0, 100)
        outside = project_ap_health_detail(
            {"cpu": {"pastNums": [{"time": 101, "pastNum": 5}]}}, 0, 100)
        self.assertEqual(outside["cpu"]["values"], [])

    def test_accepts_controller_144_point_daily_series_and_keeps_upper_bound(self) -> None:
        start, end = 1_700_000_000_000, 1_700_086_400_000
        source = {"cpu": {"pastNums": [
            {"time": start + index * 600_000, "pastNum": index}
            for index in range(144)
        ]}}
        projected = project_ap_health_detail(source, start, end)
        self.assertEqual(len(projected["cpu"]["values"]), 144)
        oversized = {"cpu": {"pastNums": [
            {"time": start, "pastNum": 1} for _ in range(257)
        ]}}
        with self.assertRaises(ApHealthProjectionError):
            project_ap_health_detail(oversized, start, end)

        cli_data = {"cpu": {"values": [
            {"time_ms": start + index * 600_000, "value": index}
            for index in range(144)
        ]}}
        self.assertEqual(len(_ap_health_data(cli_data, start, end)["data"]["cpu"]["values"]), 144)
        cli_data["cpu"]["values"] *= 2
        with self.assertRaises(CliError):
            _ap_health_data(cli_data, start, end)

        # Fifteen populated 24-hour series can produce 2,160 -1 markers.
        markers = [f"series[{index}]" for index in range(144 * 15)]
        marker_data = {"unclassified_minus_one_fields": markers}
        self.assertTrue(_ap_health_data(marker_data, start, end)["partial"])
        marker_data["unclassified_minus_one_fields"] *= 5
        with self.assertRaises(CliError):
            _ap_health_data(marker_data, start, end)

    def test_null_series_values_are_counted_as_missing_through_cli(self) -> None:
        start, end = 1_700_000_000_000, 1_700_086_400_000
        null_points = [{"time": start + index * 600_000, "pastNum": None}
                       for index in range(144)]
        projected = project_ap_health_detail({"cpu": {"pastNums": null_points}}, start, end)
        self.assertEqual(projected["cpu"]["values"], [])
        self.assertEqual(projected["cpu"]["missing_value_points"], 144)

        mixed = [{"time": start, "pastNum": 27},
                 {"time": start + 1, "pastNum": None},
                 {"time": start + 2, "pastNum": 31}]
        projected = project_ap_health_detail({"cpu": {"pastNums": mixed}}, start, end)
        self.assertEqual(projected["cpu"]["values"], [
            {"time_ms": start, "value": 27}, {"time_ms": start + 2, "value": 31}])
        self.assertEqual(projected["cpu"]["missing_value_points"], 1)

        cli_data = {"cpu": {"values": [], "missing_value_points": 144}}
        cli_result = _ap_health_data(cli_data, start, end)
        self.assertTrue(cli_result["partial"])
        self.assertEqual(cli_result["data"]["cpu"]["missing_value_points"], 144)

        for invalid in (True, "7", 2**31):
            with self.assertRaises(ApHealthProjectionError):
                project_ap_health_detail(
                    {"cpu": {"pastNums": [{"time": start, "pastNum": invalid}]}},
                    start, end)


if __name__ == "__main__":
    unittest.main()
