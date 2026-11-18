import unittest

from app.site_client_association_time import (
    SiteClientAssociationTimeError, project_site_client_association_time,
)


class SiteClientAssociationTimeTests(unittest.TestCase):
    def test_projects_bounded_association_time_bins(self):
        result = project_site_client_association_time({
            "lessThan2sNum": 12, "from2To4sNum": 4, "from4To6sNum": 2,
            "from6To8sNum": 1, "from8To10sNum": 1,
            "moreThan10sNum": 3, "fails": 2, "lessThan10sPercent": 80,
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["under_2_seconds_count"], 12)
        self.assertEqual(result["data"]["failed_association_count"], 2)
        self.assertEqual(result["data"]["under_10_seconds_percent"], 80)

    def test_counts_invalid_missing_and_unknown_fields(self):
        result = project_site_client_association_time({
            "lessThan2sNum": True, "lessThan10sPercent": 101, "private": "hidden",
        })
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["missing_field_count"], 6)
        self.assertNotIn("hidden", repr(result))
        with self.assertRaises(SiteClientAssociationTimeError):
            project_site_client_association_time({str(i): i for i in range(13)})


if __name__ == "__main__":
    unittest.main()
