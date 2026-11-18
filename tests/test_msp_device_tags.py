import unittest

from app.msp_device_tags import MspDeviceTagsError, project_msp_device_tags


class MspDeviceTagsTests(unittest.TestCase):
    def test_returns_counts_without_tag_names_or_ids(self):
        result = project_msp_device_tags([
            {"name": "private-team", "tagId": "sensitive-id"},
            {"name": "another-private-name", "tagId": "id-2"},
        ])
        self.assertEqual(result["data"], {
            "tag_count": 2, "tag_id_present_count": 2,
            "invalid_count": 0, "unknown_field_count": 0,
        })
        self.assertNotIn("private-team", str(result))
        self.assertNotIn("sensitive-id", str(result))
        self.assertFalse(result["partial"])

    def test_bad_rows_are_counted_and_oversized_shapes_rejected(self):
        result = project_msp_device_tags([{"name": "", "extra": "secret"}])
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        with self.assertRaises(MspDeviceTagsError):
            project_msp_device_tags([{} for _ in range(1_001)])
