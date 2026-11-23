from __future__ import annotations

import unittest

from app.site_stack_cable_test_log_summary import (
    StackCableTestLogSummaryError, summarize_stack_cable_test_logs,
)


class SiteStackCableTestLogSummaryTests(unittest.TestCase):
    def test_counts_documented_events_and_port_lists_without_identifiers(self):
        raw = [
            {"type": 0, "timeStamp": 123456789,
             "testPortList": [{"port": 1, "standardPort": 10}],
             "completePortList": [], "cancelPortList": [], "timeoutPortList": []},
            {"type": 1, "timeStamp": 987654321,
             "testPortList": [], "completePortList": [{"port": 1}],
             "cancelPortList": [], "timeoutPortList": []},
            {"type": 2, "testPortList": [], "completePortList": [{"port": 2}],
             "cancelPortList": [{"port": 3}], "timeoutPortList": []},
            {"type": 3, "testPortList": [], "completePortList": [{"port": 4}],
             "cancelPortList": [], "timeoutPortList": [{"port": 5}]},
        ]
        result = summarize_stack_cable_test_logs(raw)
        self.assertEqual(result["log_type_counts"],
                         {"start": 1, "completed": 1, "interrupted": 1,
                          "timed_out": 1, "unknown": 0})
        self.assertEqual(result["port_entry_counts"],
                         {"tested_port_entries": 1, "completed_port_entries": 3,
                          "cancelled_port_entries": 1, "timed_out_port_entries": 1})
        self.assertTrue(result["timestamps_returned"] is False)
        self.assertTrue(result["port_identifiers_returned"] is False)
        self.assertNotIn("123456789", str(result))
        self.assertNotIn('"port":', str(result))

    def test_unknown_type_or_missing_lists_are_partial(self):
        result = summarize_stack_cable_test_logs([{"type": 8, "testPortList": []}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["log_type_counts"]["unknown"], 1)
        self.assertGreater(result["omitted_field_count"], 0)

    def test_rejects_unbounded_and_marks_malformed_entries_partial(self):
        with self.assertRaises(StackCableTestLogSummaryError):
            summarize_stack_cable_test_logs([{}] * 65)
        result = summarize_stack_cable_test_logs([
            {"type": 0, "testPortList": [{"port": "1"}]},
        ])
        self.assertTrue(result["partial"])
        self.assertEqual(result["port_entry_counts"]["tested_port_entries"], 1)


if __name__ == "__main__":
    unittest.main()
