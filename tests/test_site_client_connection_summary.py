import unittest

from app.site_client_connection_summary import (
    SiteClientConnectionSummaryError, project_site_client_connection_summary,
)


class SiteClientConnectionSummaryTests(unittest.TestCase):
    def test_projects_only_the_documented_counts(self):
        result = project_site_client_connection_summary({
            "total": 42, "wiredClient": 8, "wirelessClient": 34,
        })
        self.assertEqual(result["data"], {
            "total_client_count": 42, "wired_client_count": 8,
            "wireless_client_count": 34,
        })
        self.assertFalse(result["partial"])

    def test_counts_missing_invalid_and_unknown_values_without_echo(self):
        result = project_site_client_connection_summary({
            "total": -1, "wiredClient": True, "private": "hidden",
        })
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["missing_field_count"], 1)
        self.assertNotIn("hidden", repr(result))
        with self.assertRaises(SiteClientConnectionSummaryError):
            project_site_client_connection_summary({str(i): i for i in range(7)})


if __name__ == "__main__":
    unittest.main()
