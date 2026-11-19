import unittest

from app.audit_log_window_summary import (
    AuditLogWindowError, summarize_audit_log_window,
)


class AuditLogWindowSummaryTests(unittest.TestCase):
    def test_projects_only_categories_level_result_and_timestamp(self):
        rows = [{
            "time": 1_700_000_000_100,
            "auditType": "User Interface",
            "level": "Information",
            "result": "Failed",
            "operator": "private-user",
            "ip": "192.0.2.20",
            "content": "secret setting value",
            "label": "/private/path",
            "oldValue": {"private": "old"},
            "newValue": {"private": "new"},
        }]
        summary = summarize_audit_log_window(
            rows, 1_700_000_000_000, 1_700_000_001_000, 1)
        self.assertEqual(summary["entries"], [{
            "time_ms": 1_700_000_000_100,
            "category": "User Interface",
            "level": "Information",
            "result": "Failed",
        }])
        self.assertNotIn("private-user", repr(summary))
        self.assertNotIn("secret setting value", repr(summary))

    def test_unknown_labels_are_aggregated_without_echo(self):
        summary = summarize_audit_log_window([{
            "time": 1_700_000_000_100,
            "auditType": "arbitrary-private-category",
            "level": "unrecognized-private-level",
            "result": "unexpected-private-result",
        }], 1_700_000_000_000, 1_700_000_001_000, 1)
        self.assertEqual(summary["entries"][0]["category"], "other")
        self.assertEqual(summary["entries"][0]["level"], "other")
        self.assertEqual(summary["entries"][0]["result"], "other")
        self.assertNotIn("arbitrary-private-category", repr(summary))

    def test_non_string_categories_do_not_escape_projection(self):
        summary = summarize_audit_log_window([{
            "time": 1_700_000_000_100,
            "auditType": {"private": "category"},
            "level": ["private"],
            "result": None,
        }], 1_700_000_000_000, 1_700_000_001_000, 1)
        self.assertEqual(summary["entries"][0]["category"], "other")
        self.assertEqual(summary["entries"][0]["level"], "other")
        self.assertEqual(summary["entries"][0]["result"], "other")

    def test_window_and_timestamp_are_checked(self):
        with self.assertRaises(AuditLogWindowError):
            summarize_audit_log_window([], 1_700_000_000_000,
                                       1_700_086_400_001, 0)
        with self.assertRaises(AuditLogWindowError):
            summarize_audit_log_window([{"time": True}],
                                       1_700_000_000_000,
                                       1_700_000_001_000, 1)


if __name__ == "__main__":
    unittest.main()
