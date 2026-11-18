import unittest

from app.site_template_summary import SiteTemplateSummaryError, summarize_site_template


class SiteTemplateSummaryTests(unittest.TestCase):
    def test_projects_opaque_ref_and_bounded_metadata(self):
        result = summarize_site_template({
            "id": "private-template-id", "omadacId": "controller",
            "name": "Private name", "type": 1, "bindSiteNum": 3,
            "settings": ["LAN", "IPTV"], "category": "legacy",
        }, template_ref="a" * 24)
        self.assertEqual(result["data"], {"site_template_ref": "a" * 24,
                         "template_type": "pro", "bound_site_count": 3, "settings_count": 2})
        self.assertFalse(result["partial"])
        for value in ("private-template-id", "controller", "Private name", "IPTV", "legacy"):
            self.assertNotIn(value, repr(result))

    def test_name_is_only_exposed_when_configured(self):
        result = summarize_site_template({"id": "x", "name": "Room", "type": 0},
                                         template_ref="b" * 24, expose_name=True)
        self.assertEqual(result["data"]["template_name"], "Room")

    def test_bad_metadata_marks_partial(self):
        result = summarize_site_template({"id": "x", "type": 9, "settings": "bad"},
                                         template_ref="c" * 24)
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 2)

    def test_non_object_rejected(self):
        with self.assertRaises(SiteTemplateSummaryError):
            summarize_site_template([], template_ref="d" * 24)


if __name__ == "__main__":
    unittest.main()
