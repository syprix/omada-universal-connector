from __future__ import annotations

import unittest

from app.client_health_timeline import (
    ClientHealthTimelineError,
    project_client_health_timeline,
)


START = 1_700_000_000_000
END = START + 86_400_000


class ClientHealthTimelineProjectionTests(unittest.TestCase):
    def test_projects_only_documented_time_score_pairs_without_scale_claim(self) -> None:
        result = project_client_health_timeline({"scores": [
            {"time": START, "score": -(2**31)},
            {"time": END, "score": 2**31 - 1},
        ]}, START, END)
        self.assertFalse(result["partial"])
        self.assertEqual(result["resource"], "client_health_timeline")
        self.assertEqual(result["data"], {"scores": [
            {"time_ms": START, "score": -(2**31)},
            {"time_ms": END, "score": 2**31 - 1},
        ]})
        self.assertNotIn("score_scale", result)

    def test_empty_scores_is_a_valid_empty_observation(self) -> None:
        result = project_client_health_timeline({"scores": []}, START, END)
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"], {"scores": []})

    def test_missing_scores_does_not_invent_empty_series(self) -> None:
        result = project_client_health_timeline({}, START, END)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"], {})
        self.assertEqual(result["missing_fields"], ["scores"])

    def test_null_score_is_not_coerced_and_marks_partial(self) -> None:
        result = project_client_health_timeline(
            {"scores": [{"time": START, "score": None}]}, START, END)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["scores"], [{"time_ms": START}])
        self.assertIn("scores[0].score", result["omitted_fields"])

    def test_missing_invalid_and_out_of_window_values_are_partial(self) -> None:
        raw = {"scores": [
            {"time": START},
            {"score": 5},
            {"time": True, "score": 6},
            {"time": START - 1, "score": 7},
            {"time": END + 1, "score": 8},
            {"time": START, "score": 2**31},
            "private-malformed-row",
        ]}
        result = project_client_health_timeline(raw, START, END)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["scores"], [
            {"time_ms": START},
            {"time_ms": START},
        ])
        self.assertTrue(all("score" not in point for point in result["data"]["scores"]))
        self.assertNotIn("private-malformed-row", repr(result))

    def test_unknown_and_identity_fields_mark_partial_without_disclosure(self) -> None:
        result = project_client_health_timeline({
            "scores": [{"time": START, "score": 1, "clientName": "private-client"}],
            "clientMac": "AA:BB:CC:DD:EE:FF",
            "clientIp": "192.0.2.77",
        }, START, END)
        self.assertTrue(result["partial"])
        self.assertIn("unknown_fields", result["omitted_fields"])
        for private in ("clientName", "private-client", "clientMac", "AA:BB:CC:DD:EE:FF",
                        "clientIp", "192.0.2.77"):
            self.assertNotIn(private, repr(result))

    def test_boolean_and_numeric_bounds_are_strict(self) -> None:
        for point in (
            {"time": START, "score": True},
            {"time": 2**63, "score": 1},
            {"time": START, "score": 2**31},
            {"time": START, "score": -(2**31) - 1},
            {"time": END, "score": 1.0},
        ):
            with self.subTest(point=point):
                result = project_client_health_timeline({"scores": [point]}, START, END)
                self.assertTrue(result["partial"])
                for projected in result["data"]["scores"]:
                    self.assertTrue("time_ms" not in projected or
                                    START <= projected["time_ms"] <= END)
                    self.assertTrue("score" not in projected or
                                    -(2**31) <= projected["score"] <= 2**31 - 1)

    def test_invalid_windows_and_size_limits_fail_closed(self) -> None:
        invalid_inputs = (
            (None, START, END),
            ([], START, END),
            ({"scores": ["x"] * 257}, START, END),
            ({"scores": [], **{f"x{i}": i for i in range(32)}}, START, END),
            ({"scores": [{"time": START, "score": 1,
                           **{f"x{i}": i for i in range(32)}}]}, START, END),
            ({"scores": []}, True, END),
            ({"scores": []}, END, START),
            ({"scores": []}, 0, 2**63),
        )
        for raw, start, end in invalid_inputs:
            with self.subTest(raw=type(raw).__name__), self.assertRaises(ClientHealthTimelineError):
                project_client_health_timeline(raw, start, end)

    def test_bounded_subday_window_is_valid(self) -> None:
        result = project_client_health_timeline(
            {"scores": [{"time": START + 1, "score": 7}]}, START, START + 10_000)
        self.assertEqual(result["data"]["scores"], [{"time_ms": START + 1, "score": 7}])


if __name__ == "__main__":
    unittest.main()
