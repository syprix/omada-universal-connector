from __future__ import annotations

import unittest

from app.ap_health_timeline import ApHealthTimelineError, project_ap_health_timeline


START = 1_700_000_000_000
END = START + 86_400_000


class ApHealthTimelineProjectionTests(unittest.TestCase):
    def test_projects_documented_score_pairs(self) -> None:
        result = project_ap_health_timeline({"scores": [
            {"time": START, "score": -7},
            {"time": END, "score": 0},
        ]}, START, END)
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"], {"scores": [
            {"time_ms": START, "score": -7},
            {"time_ms": END, "score": 0},
        ]})
        self.assertNotIn("score_scale", result)

    def test_null_is_omitted_not_interpreted_as_zero_and_marks_partial(self) -> None:
        result = project_ap_health_timeline({
            "scores": [{"time": START, "score": None}],
        }, START, END)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["scores"], [{"time_ms": START}])
        self.assertNotIn("score", result["data"]["scores"][0])

    def test_missing_scores_is_partial_without_synthetic_empty_series(self) -> None:
        result = project_ap_health_timeline({}, START, END)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"], {})
        self.assertEqual(result["missing_fields"], ["scores"])

    def test_valid_empty_scores_is_complete_empty_observation(self) -> None:
        result = project_ap_health_timeline({"scores": []}, START, END)
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"], {"scores": []})

    def test_missing_invalid_and_unknown_fields_are_partial_and_redacted(self) -> None:
        result = project_ap_health_timeline({
            "scores": [
                {"time": START},
                {"time": True, "score": 5, "clientName": "private"},
                {"time": END + 1, "score": 6},
                "malformed-private-row",
            ],
            "deviceMac": "aa:bb:cc:dd:ee:ff",
        }, START, END)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["scores"], [
            {"time_ms": START},
            {"score": 5},
            {"score": 6},
        ])
        rendered = repr(result)
        for secret in ("private", "clientName", "deviceMac", "aa:bb:cc:dd:ee:ff",
                       "malformed-private-row"):
            self.assertNotIn(secret, rendered)
        self.assertIn("unknown_fields", result["omitted_fields"])

    def test_type_and_numeric_bounds_are_strict_without_bool_coercion(self) -> None:
        for point in (
            {"time": START, "score": True},
            {"time": 2**63, "score": 1},
            {"time": START - 1, "score": 1},
            {"time": END + 1, "score": 1},
            {"time": START, "score": 2**31},
            {"time": START, "score": -(2**31) - 1},
        ):
            with self.subTest(point=point):
                result = project_ap_health_timeline({"scores": [point]}, START, END)
                self.assertTrue(result["partial"])
                row = result["data"]["scores"][0]
                self.assertTrue("time_ms" not in row or START <= row["time_ms"] <= END)
                self.assertTrue("score" not in row or row["score"] is None or
                                -(2**31) <= row["score"] <= 2**31 - 1)

    def test_size_bounds_and_invalid_window_fail_closed(self) -> None:
        invalid_inputs = (
            (None, START, END),
            ([], START, END),
            ({"scores": ["x"] * 257}, START, END),
            ({"scores": [], **{f"x{i}": i for i in range(32)}}, START, END),
            ({"scores": [{"time": START, "score": 1,
                           **{f"x{i}": i for i in range(32)}}]}, START, END),
            ({"scores": []}, True, END),
            ({"scores": []}, END, START),
        )
        for raw, start, end in invalid_inputs:
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ApHealthTimelineError):
                project_ap_health_timeline(raw, start, end)


if __name__ == "__main__":
    unittest.main()
