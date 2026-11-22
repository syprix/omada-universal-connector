import unittest

from app.site_ssid_client_count_summary import (
    SiteSsidClientCountSummaryError, project_ssid_client_count,
)


class SiteSsidClientCountSummaryTests(unittest.TestCase):
    def test_uses_documented_total_and_marks_page_coverage(self):
        complete = project_ssid_client_count(
            {"totalRows": 2, "currentPage": 1, "currentSize": 2},
            [{"mac": "00:11:22:33:44:55", "name": "private"}, {"id": "secret"}],
        )
        self.assertEqual(complete["client_count"], 2)
        self.assertTrue(complete["coverage_complete"])
        self.assertFalse(complete["online_status_provided"])
        self.assertNotIn("private", str(complete))
        partial = project_ssid_client_count(
            {"totalRows": 101, "currentPage": 1, "currentSize": 100}, [{}] * 100)
        self.assertEqual(partial["client_count"], 101)
        self.assertFalse(partial["coverage_complete"])

    def test_rejects_bad_page_envelopes(self):
        for result, rows in (
            ({"totalRows": True, "currentPage": 1, "currentSize": 0}, []),
            ({"totalRows": 2, "currentPage": 2, "currentSize": 1}, [{}]),
            ({"totalRows": 0, "currentPage": 1, "currentSize": 0}, [{}]),
            ({"totalRows": 101, "currentPage": 1, "currentSize": 101}, [{}] * 101),
        ):
            with self.assertRaises(SiteSsidClientCountSummaryError):
                project_ssid_client_count(result, rows)


if __name__ == "__main__":
    unittest.main()
