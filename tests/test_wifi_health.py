from __future__ import annotations

import unittest

from app.wifi_health import WifiHealthProjectionError, project_wifi_health


class WifiHealthProjectionTests(unittest.TestCase):
    def test_projects_only_documented_integer_fields_in_millisecond_window(self) -> None:
        result = project_wifi_health({"scores": [
            {"time": 2_000, "score": 84, "siteName": "private"},
            {"time": 1_000, "score": 0},
            {"time": 4_000, "score": 100},
            {"time": 3_000, "score": -1},
        ], "private": "must-not-escape"}, 1_500, 3_500)
        self.assertEqual(result["scores"], [
            {"time_ms": 2_000, "score": 84},
            {"time_ms": 3_000, "score": -1},
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["counts"]["outside_window_points"], 2)
        self.assertEqual(result["counts"]["unknown_fields"], 2)
        self.assertNotIn("private", str(result))
        self.assertNotIn("siteName", str(result))

    def test_empty_list_is_complete_and_preserves_explicit_window(self) -> None:
        result = project_wifi_health({"scores": []}, 0, 1_700_000_000_000)
        self.assertEqual(result["window"], {"start_ms": 0, "end_ms": 1_700_000_000_000})
        self.assertEqual(result["scores"], [])
        self.assertFalse(result["partial"])
        self.assertEqual(result["counts"]["received_points"], 0)

    def test_duplicate_timestamps_are_all_omitted_and_counted(self) -> None:
        result = project_wifi_health({"scores": [
            {"time": 5, "score": 10}, {"time": 5, "score": 20},
            {"time": 5, "score": 30}, {"time": 6, "score": 40},
        ]}, 0, 10)
        self.assertEqual(result["scores"], [{"time_ms": 6, "score": 40}])
        self.assertEqual(result["counts"]["duplicate_timestamp_points"], 3)
        self.assertTrue(result["partial"])

    def test_output_truncation_and_input_examining_bound_are_explicit(self) -> None:
        rows = [{"time": index, "score": index} for index in range(600)]
        result = project_wifi_health({"scores": rows}, 0, 1000)
        self.assertEqual(len(result["scores"]), 512)
        self.assertEqual(result["counts"]["truncated_points"], 88)
        self.assertTrue(result["partial"])

        rows = [{"time": index, "score": 1} for index in range(10_003)]
        result = project_wifi_health({"scores": rows}, 0, 20_000)
        self.assertEqual(result["counts"]["examined_points"], 10_000)
        self.assertEqual(result["counts"]["unexamined_points"], 3)
        self.assertEqual(result["counts"]["truncated_points"], 9_488)
        self.assertTrue(result["partial"])

    def test_invalid_window_result_rows_and_schema_values_fail_closed(self) -> None:
        for start, end in ((True, 1), (0, False), (0, 2**63), (2, 1)):
            with self.subTest(window=(start, end)), self.assertRaisesRegex(
                    WifiHealthProjectionError, "window_invalid"):
                project_wifi_health({"scores": []}, start, end)
        for value, code in ((None, "result_invalid"), ({}, "result_invalid"),
                            ({"scores": None}, "scores_invalid"),
                            ({"scores": [{"time": 1}]}, "score_invalid"),
                            ({"scores": [{"time": True, "score": 1}]}, "score_invalid"),
                            ({"scores": [{"time": 1, "score": False}]}, "score_invalid"),
                            ({"scores": [{"time": 2**63, "score": 1}]}, "score_invalid"),
                            ({"scores": [{"time": 1, "score": 2**31}]}, "score_invalid"),
                            ({"scores": [{"time": 1.0, "score": 1}]}, "score_invalid")):
            with self.subTest(value=value), self.assertRaisesRegex(WifiHealthProjectionError, code):
                project_wifi_health(value, 0, 10)


if __name__ == "__main__":
    unittest.main()
