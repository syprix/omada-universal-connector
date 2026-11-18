from __future__ import annotations

import unittest

from app.switch_health_timeline import (
    SwitchHealthTimelineError,
    project_switch_health_timeline,
)


START = 1_700_000_000_000
END = START + 86_400_000


class SwitchHealthTimelineTests(unittest.TestCase):
    def test_projects_documented_pairs_and_drops_unknown_values(self) -> None:
        result = project_switch_health_timeline({
            "scores": [{"time": START, "score": 78}, {"time": END, "score": -1}],
            "switchMac": "private-mac",
        }, START, END)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"], {"scores": [
            {"time_ms": START, "score": 78}, {"time_ms": END, "score": -1}]})
        self.assertNotIn("private-mac", repr(result))

    def test_missing_invalid_and_out_of_window_values_are_partial(self) -> None:
        result = project_switch_health_timeline({"scores": [
            {"time": START}, {"score": 4}, {"time": START - 1, "score": 2},
            {"time": True, "score": 3}, {"time": END, "score": 2**31}]}, START, END)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["scores"], [
            {"time_ms": START}, {"time_ms": END}])

    def test_invalid_bounds_and_oversized_responses_fail_closed(self) -> None:
        for value, start, end in (
            (None, START, END), ({"scores": [None] * 257}, START, END),
            ({"scores": []}, True, END), ({"scores": []}, END, START),
        ):
            with self.subTest(value=type(value).__name__), self.assertRaises(SwitchHealthTimelineError):
                project_switch_health_timeline(value, start, end)


if __name__ == "__main__":
    unittest.main()
