import unittest

from app.site_client_attachment_distribution import (
    SiteClientAttachmentDistributionError, project_site_client_attachment_distribution,
)


class SiteClientAttachmentDistributionTests(unittest.TestCase):
    def test_projects_totals_and_discards_named_client_rows(self):
        result = project_site_client_attachment_distribution({
            "eapDistribution": {"totalEapClients": 12, "totalEapDistribution": 75.0,
                                "eaps": [{"name": "private-ap"}] * 4,
                                "others": {"name": "hidden"}},
            "switchDistribution": {"totalSwitchClients": 4,
                                   "totalSwitchDistribution": 25.0,
                                   "switches": [{"name": "private-switch"}],
                                   "others": {"name": "hidden"}},
        })
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["access_point_attached_client_count"], 12)
        self.assertEqual(result["data"]["switch_attached_client_count"], 4)
        self.assertNotIn("private-ap", repr(result))
        self.assertNotIn("private-switch", repr(result))

    def test_counts_invalid_and_unknown_values_without_echoing_them(self):
        result = project_site_client_attachment_distribution({
            "eapDistribution": {"totalEapClients": True, "eaps": "private"},
            "switchDistribution": {"totalSwitchClients": 4, "unexpected": "hidden"},
        })
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))
        self.assertNotIn("hidden", repr(result))
        with self.assertRaises(SiteClientAttachmentDistributionError):
            project_site_client_attachment_distribution({str(i): i for i in range(5)})


if __name__ == "__main__":
    unittest.main()
