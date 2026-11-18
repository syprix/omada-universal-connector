from __future__ import annotations

import math
import unittest

from app.switch_health import (
    MAX_INCIDENTS_PER_DIMENSION,
    MAX_POINTS_PER_SERIES,
    SwitchHealthProjectionError,
    project_switch_health_detail,
)


class SwitchHealthProjectionTests(unittest.TestCase):
    def test_projects_documented_integer_metrics_and_drops_incident_details(self) -> None:
        start, end = 1_700_000_000_000, 1_700_086_400_000
        private_mac = "AA-BB-CC-DD-EE-FF"
        private_name = "private switch"
        result = {
            "score": 83,
            "cpu": {"summaryScore": 91, "support": True, "averageNum": 19,
                    "pastNums": [{"time": start + 10, "pastNum": 22}],
                    "incidents": [{"incidentId": "secret", "macs": [private_mac],
                                   "titleParams": {"name": private_name}}]},
            "memory": {"summaryScore": 80, "support": False,
                       "averageNum": -1, "pastNums": []},
            "temperature": {"summaryScore": 75, "support": True,
                            "averageNum": 40, "pastNums": [
                                {"time": start - 1, "pastNum": 35},
                                {"time": end, "pastNum": 40}]},
            "packetLoss": {"summaryScore": 77, "support": True,
                           "averageNum": 3, "pastNums": [{"time": end, "pastNum": 2}]},
            "errorFrame": {"averageNum": 4, "pastNums": []},
            "incident": {"summaryScore": 90, "support": True, "incidentNum": 2,
                         "incidents": [{"incidentId": "hidden", "mac": private_mac}]},
            "linkError": {"summaryScore": 88, "support": True, "averageNum": 1,
                          "portNum": 48, "pastNums": []},
            "switchName": private_name, "mac": private_mac, "ip": "192.0.2.10",
        }
        projected = project_switch_health_detail(result, start, end)

        self.assertEqual(projected["score"], 83)
        self.assertEqual(projected["cpu"]["average"], 19)
        self.assertEqual(projected["cpu"]["values"], [{"time_ms": start + 10, "value": 22}])
        self.assertEqual(projected["cpu"]["omitted_incident_count"], 1)
        self.assertEqual(projected["temperature"]["values"], [{"time_ms": end, "value": 40}])
        self.assertEqual(projected["temperature"]["omitted_out_of_window_sample_count"], 1)
        self.assertEqual(projected["incident"]["incident_count"], 2)
        self.assertEqual(projected["link_error"]["port_count"], 48)
        self.assertEqual(projected["unclassified_minus_one_fields"], ["memory.average"])
        self.assertTrue(projected["partial"])
        rendered = str(projected)
        for forbidden in (private_mac, private_name, "192.0.2.10", "secret", "hidden", "switchName"):
            self.assertNotIn(forbidden, rendered)

    def test_projects_float_variants_documented_by_newer_export_families(self) -> None:
        result = {
            "score": 80,
            "cpu": {"summaryScore": 80, "support": True, "averageNum": 10,
                    "pastNums": []},
            "memory": {"summaryScore": 80, "support": True, "averageNum": 20,
                       "pastNums": []},
            "temperature": {"summaryScore": 80, "support": True, "averageNum": 30,
                             "pastNums": []},
            "packetLoss": {"summaryScore": 70, "support": True, "averageNum": 0,
                           "pastNums": [], "averageFloat": 0.25,
                           "pastFloats": [{"time": 100, "pastNum": 0.5}]},
            "errorFrame": {"summaryScore": 60, "support": True, "averageNum": 1,
                           "pastNums": [], "averageFloat": 1.5,
                           "pastFloats": [{"time": 100, "pastNum": 2.25}]},
        }
        projected = project_switch_health_detail(result, 0, 200)
        self.assertEqual(projected["packet_loss"]["average_float"], 0.25)
        self.assertEqual(projected["packet_loss"]["float_values"],
                         [{"time_ms": 100, "value": 0.5}])
        self.assertEqual(projected["error_frame"]["average_float"], 1.5)
        self.assertFalse(projected["partial"])

    def test_missing_core_values_are_named_without_copying_unknown_keys(self) -> None:
        projected = project_switch_health_detail({"private-key": "secret"}, 0, 10)
        self.assertEqual(projected["missing_fields"], [
            "score", "cpu", "memory", "temperature", "packet_loss", "error_frame",
        ])
        self.assertEqual(projected["omitted_field_count"], 1)
        self.assertTrue(projected["partial"])
        self.assertNotIn("private-key", str(projected))
        self.assertNotIn("secret", str(projected))

    def test_dimension_marks_missing_measurements_and_support(self) -> None:
        projected = project_switch_health_detail({"cpu": {"averageNum": 1}}, 0, 10)
        self.assertEqual(projected["cpu"]["missing_fields"], [
            "summary_score", "supported", "values",
        ])
        self.assertTrue(projected["partial"])

    def test_nonprojected_fields_make_dimension_partial_without_leaking_values(self) -> None:
        result = {"cpu": {"summaryScore": 90, "support": True, "averageNum": 10,
                          "pastNums": [{"time": 5, "pastNum": 8, "secret": "hidden"}],
                          "averageFloat": 1.5}}
        projected = project_switch_health_detail(result, 0, 10)
        self.assertEqual(projected["cpu"]["omitted_field_count"], 2)
        self.assertTrue(projected["cpu"]["partial"])
        self.assertNotIn("hidden", str(projected))

    def test_rejects_invalid_values_and_bounds_arrays(self) -> None:
        invalid_results = [
            {"score": True},
            {"cpu": {"support": 1}},
            {"cpu": {"pastNums": [{"time": 0, "pastNum": 0}] * (MAX_POINTS_PER_SERIES + 1)}},
            {"cpu": {"incidents": [{}] * (MAX_INCIDENTS_PER_DIMENSION + 1)}},
            {"packetLoss": {"averageFloat": math.inf}},
            {"errorFrame": {"pastFloats": [{"time": 0, "pastNum": "bad"}]}},
            {"temperature": {"pastNums": [{"time": -1, "pastNum": 2}]}},
        ]
        for result in invalid_results:
            with self.subTest(result=list(result)):
                with self.assertRaises(SwitchHealthProjectionError):
                    project_switch_health_detail(result, 0, 100)
        for start, end in ((-1, 0), (10, 9), (0, 2**63)):
            with self.subTest(start=start, end=end), self.assertRaises(SwitchHealthProjectionError):
                project_switch_health_detail({}, start, end)


if __name__ == "__main__":
    unittest.main()
