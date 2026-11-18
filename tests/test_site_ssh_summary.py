import unittest

from app.site_ssh_summary import SiteSshSummaryError, summarize_site_ssh


class SiteSshSummaryTests(unittest.TestCase):
    def test_projects_documented_settings(self):
        result = summarize_site_ssh({"sshEnable": True, "sshServerPort": 2222,
                                     "layer3Access": False})
        self.assertEqual(result["data"], {"enabled": True,
                         "layer3_access_enabled": False, "server_port": 2222})
        self.assertFalse(result["partial"])

    def test_validates_documented_port_and_partial_data(self):
        self.assertFalse(summarize_site_ssh({"sshEnable": False, "sshServerPort": 22,
                                             "layer3Access": True})["partial"])
        result = summarize_site_ssh({"sshEnable": True, "sshServerPort": 23, "extra": "discard"})
        self.assertTrue(result["partial"])
        self.assertIsNone(result["data"]["server_port"])
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("discard", repr(result))

    def test_non_object_response_rejected(self):
        with self.assertRaises(SiteSshSummaryError):
            summarize_site_ssh([])


if __name__ == "__main__":
    unittest.main()
