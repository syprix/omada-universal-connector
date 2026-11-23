import unittest

from app.site_wan_unsupported_function_summary import (
    MAX_FUNCTION_ENTRIES,
    summarize_wan_unsupported_functions,
)


class WanUnsupportedFunctionSummaryTests(unittest.TestCase):
    def test_counts_string_entries_without_returning_their_text(self):
        result = summarize_wan_unsupported_functions({
            "result": {"functions": ["private capability label", "another label"]}
        })
        self.assertEqual(result, {
            "result_state": "ok",
            "reported_limitation_entry_count": 2,
            "truncated": False,
        })
        self.assertNotIn("private capability label", repr(result))

    def test_empty_list_is_distinct_from_missing(self):
        self.assertEqual(
            summarize_wan_unsupported_functions({"result": {"functions": []}}),
            {"result_state": "empty", "reported_limitation_entry_count": 0,
             "truncated": False},
        )
        self.assertEqual(
            summarize_wan_unsupported_functions({"result": {}}),
            {"result_state": "missing", "missing_field": "functions",
             "reported_limitation_entry_count": None, "truncated": False},
        )

    def test_invalid_shape_and_non_string_rows_are_not_counted(self):
        for payload in ({"result": {"functions": "free text"}},
                        {"result": {"functions": ["sensitive label", 5]}}):
            result = summarize_wan_unsupported_functions(payload)
            self.assertEqual(result["result_state"], "invalid")
            self.assertIsNone(result["reported_limitation_entry_count"])
            self.assertNotIn("sensitive label", repr(result))

    def test_list_is_bounded_and_truncation_is_explicit(self):
        result = summarize_wan_unsupported_functions({
            "result": {"functions": ["label"] * (MAX_FUNCTION_ENTRIES + 1)}
        })
        self.assertEqual(result["result_state"], "truncated")
        self.assertEqual(result["reported_limitation_entry_count"], MAX_FUNCTION_ENTRIES)
        self.assertTrue(result["truncated"])


if __name__ == "__main__":
    unittest.main()
