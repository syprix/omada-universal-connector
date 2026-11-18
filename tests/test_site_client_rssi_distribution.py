import unittest

from app.site_client_rssi_distribution import (
    SiteClientRssiDistributionError, project_site_client_rssi_distribution,
)


class SiteClientRssiDistributionTests(unittest.TestCase):
    def test_projects_overall_and_three_band_counts_only(self):
        buckets = {"lessThan72": 1, "from71To65": 2, "from65To55": 3,
                   "from55To45": 4, "moreThan45": 5}
        source = {**buckets, "distribution2G": dict(buckets),
                  "distribution5G": dict(buckets), "distribution6G": dict(buckets),
                  "private": "client-name"}
        result = project_site_client_rssi_distribution(source)
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["data"]["less_than_72"], 1)
        self.assertEqual(result["data"]["band_6_ghz"]["more_than_45"], 5)
        self.assertNotIn("client-name", repr(result))

    def test_rejects_oversized_objects_and_counts_invalid_values(self):
        result = project_site_client_rssi_distribution({
            "lessThan72": True, "distribution2G": {"lessThan72": -1},
        })
        self.assertEqual(result["invalid_field_count"], 2)
        with self.assertRaises(SiteClientRssiDistributionError):
            project_site_client_rssi_distribution({str(i): i for i in range(13)})
        with self.assertRaises(SiteClientRssiDistributionError):
            project_site_client_rssi_distribution({"distribution2G": [1]})


if __name__ == "__main__":
    unittest.main()
