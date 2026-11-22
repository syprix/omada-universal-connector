import unittest

from app.site_remote_logging_summary import (
    SiteRemoteLoggingSummaryError, summarize_site_remote_logging,
)


class SiteRemoteLoggingSummaryTests(unittest.TestCase):
    def test_returns_activation_categories_and_target_presence_only(self):
        result = summarize_site_remote_logging({
            "enable": True, "host": "logs.example.invalid", "port": 6514,
            "moreClientLog": False, "resource": 1,
        })
        self.assertTrue(result["enabled"])
        self.assertFalse(result["client_logs_enabled"])
        self.assertEqual(result["resource_source"], "template")
        self.assertTrue(result["destination_host_configured"])
        self.assertTrue(result["destination_port_configured"])
        self.assertNotIn("logs.example.invalid", str(result))
        self.assertNotIn("6514", str(result))
        self.assertEqual(result["delivery_success"], "not assessed")

    def test_unknown_categories_and_fields_are_marked_partial(self):
        result = summarize_site_remote_logging({
            "enable": False, "resource": 9, "futureField": "private",
        })
        self.assertIsNone(result["resource_source"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private", str(result))

    def test_enable_is_required_and_boolean(self):
        for value in (None, {"enable": 1}, []):
            with self.assertRaises(SiteRemoteLoggingSummaryError):
                summarize_site_remote_logging(value)


if __name__ == "__main__":
    unittest.main()
