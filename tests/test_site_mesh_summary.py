import unittest

from app.site_mesh_summary import SiteMeshSummaryError, project_site_mesh_summary


class SiteMeshSummaryTests(unittest.TestCase):
    def test_projects_mesh_flags_and_redacts_gateway_address(self):
        result = project_site_mesh_summary({"mesh": {
            "meshEnable": True, "autoFailoverEnable": True,
            "defGatewayEnable": False, "gateway": "192.0.2.1", "fullSector": False,
        }})
        self.assertEqual(result["data"], {
            "mesh_enabled": True, "auto_failover_enabled": True,
            "automatic_gateway_detection": False,
            "custom_gateway_configured": True, "full_sector_dfs_enabled": False,
        })
        self.assertNotIn("192.0.2.1", repr(result))
        self.assertFalse(result["partial"])

    def test_unknown_and_invalid_fields_are_counted(self):
        result = project_site_mesh_summary({"mesh": {
            "meshEnable": "yes", "gateway": "999.1.1.1", "secret": "private",
        }})
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("private", repr(result))
        oversized = project_site_mesh_summary({"mesh": {str(i): i for i in range(17)}})
        self.assertEqual(oversized["invalid_field_count"], 1)
        with self.assertRaises(SiteMeshSummaryError):
            project_site_mesh_summary({str(i): i for i in range(5)})

    def test_missing_mesh_is_reported_as_partial(self):
        result = project_site_mesh_summary({})
        self.assertEqual(result["missing_field_count"], 1)
        self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
