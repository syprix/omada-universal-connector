from __future__ import annotations

import math
import unittest

from app.gateway_health import (
    GatewayHealthProjectionError,
    project_gateway_health_detail,
)


class GatewayHealthProjectionTests(unittest.TestCase):
    def test_projects_common_and_optional_family_values_safely(self) -> None:
        start, end = 1_700_000_000_000, 1_700_086_400_000
        secret_mac = "AA-BB-CC-DD-EE-FF"
        private_name = "private gateway"
        result = {
            "score": 86,
            "cpu": {"summaryScore": 90, "support": True, "averageNum": 14,
                    "pastNums": [{"time": start + 1, "pastNum": 15}],
                    "incidents": [{"macs": [secret_mac], "titleParams": {"name": private_name}}]},
            "wanLatency": {"averageNum": 18,
                           "pastNums": [{"time": start - 1, "pastNum": 99},
                                        {"time": end + 1, "pastNum": 100}]},
            "wanStatus": {"averageLatency": 25, "averageJitter": 3,
                          "averagePktLoss": 0.2, "averageMos": 4.1,
                          "latency": [{"time": end, "pastNum": 22}],
                          "pktLoss": [{"time": start, "pastNum": 0.1}],
                          "incidents": [{"incidentId": "hidden", "message": private_name}]},
            "linkError": {"averageNum": 2, "portNum": 5,
                           "pastNums": [{"time": start + 8, "pastNum": 1}]},
            "incident": {"incidentNum": 3, "incidents": [{"id": "hidden"}]},
            "gatewayName": private_name,
            "mac": secret_mac,
            "ip": "192.0.2.14",
        }
        projected = project_gateway_health_detail(result, start, end)

        self.assertEqual(projected["score"], 86)
        self.assertEqual(projected["cpu"]["summary_score"], 90)
        self.assertEqual(projected["cpu"]["values"], [{"time_ms": start + 1, "value": 15}])
        self.assertEqual(projected["cpu"]["omitted_incident_count"], 1)
        self.assertEqual(projected["wan_latency"]["omitted_out_of_window_sample_count"], 2)
        self.assertEqual(projected["wan_status"]["average_packet_loss"], 0.2)
        self.assertEqual(projected["wan_status"]["latency_values"],
                         [{"time_ms": end, "value": 22}])
        self.assertEqual(projected["link_error"]["port_count"], 5)
        self.assertEqual(projected["incident"]["incident_count"], 3)
        self.assertTrue(projected["partial"])
        rendered = str(projected)
        for forbidden in (secret_mac, private_name, "192.0.2.14", "hidden", "message", "gatewayName"):
            self.assertNotIn(forbidden, rendered)

    def test_older_er7212_shape_works_without_new_family_fields(self) -> None:
        projected = project_gateway_health_detail(
            {"score": 80, "cpu": {"support": True, "averageNum": 10},
             "channelUtil": {"averageNum2g": 20}, "transmission": {"averageNumTxRetry": 3}},
            100, 200)
        self.assertEqual(projected["cpu"]["average"], 10)
        self.assertEqual(projected["channel_utilization"]["average_2g"], 20)
        self.assertEqual(projected["transmission"]["average_tx_retry"], 3)
        self.assertNotIn("wan_status", projected)
        self.assertNotIn("link_error", projected)
        self.assertNotIn("incident", projected)
        self.assertFalse(projected["partial"])

    def test_counts_known_fields_omitted_from_the_wrong_dimension_kind(self) -> None:
        projected = project_gateway_health_detail(
            {"cpu": {"averageNum": 12, "averageNum2g": 23}}, 0, 100)
        self.assertEqual(projected["cpu"]["average"], 12)
        self.assertEqual(projected["cpu"]["omitted_field_count"], 1)
        self.assertTrue(projected["partial"])

    def test_null_gateway_samples_and_larger_source_series_are_partial(self) -> None:
        start, end = 1_700_000_000_000, 1_700_086_400_000
        empty_samples = [{"time": start + index * 600_000, "pastNum": None}
                         for index in range(144)]
        projected = project_gateway_health_detail(
            {"cpu": {"support": True, "pastNums": empty_samples},
             "wanStatus": {"pastLatency": empty_samples}}, start, end)
        self.assertTrue(projected["partial"])
        self.assertEqual(projected["cpu"]["values"], [])
        self.assertEqual(projected["cpu"]["omitted_missing_sample_count"], 144)
        self.assertEqual(projected["wan_status"]["latency_values"], [])
        self.assertEqual(projected["wan_status"]["omitted_missing_sample_count"], 144)

    def test_output_series_keeps_latest_bounded_points(self) -> None:
        start, end = 1_700_000_000_000, 1_700_086_400_000
        samples = [{"time": start + index, "pastNum": index} for index in range(100)]
        projected = project_gateway_health_detail(
            {"cpu": {"pastNums": samples}}, start, end)
        values = projected["cpu"]["values"]
        self.assertEqual(len(values), 64)
        self.assertEqual(values[0]["value"], 36)
        self.assertEqual(values[-1]["value"], 99)
        self.assertEqual(projected["cpu"]["omitted_point_count"], 36)

    def test_rejects_bad_shapes_unbounded_arrays_and_nonfinite_or_huge_numbers(self) -> None:
        invalid = [
            ({"score": True}, 0, 10),
            ({"cpu": {"support": 1}}, 0, 10),
            ({"cpu": {"pastNums": [{"time": 0, "pastNum": 1}] * 513}}, 0, 10),
            ({"wanStatus": {"averageMos": math.inf}}, 0, 10),
            ({"wanStatus": {"averagePktLoss": 10**1000}}, 0, 10),
        ]
        for result, start, end in invalid:
            with self.subTest(result=list(result)):
                with self.assertRaises(GatewayHealthProjectionError):
                    project_gateway_health_detail(result, start, end)
        with self.assertRaises(GatewayHealthProjectionError):
            project_gateway_health_detail({}, 10, 9)


if __name__ == "__main__":
    unittest.main()
