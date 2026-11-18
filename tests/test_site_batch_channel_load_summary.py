import unittest

from app.site_batch_channel_load_summary import (
    SiteBatchChannelLoadSummaryError,
    summarize_site_batch_channel_loads,
)


class SiteBatchChannelLoadSummaryTests(unittest.TestCase):
    def test_aggregates_only_loads_and_suppresses_channel_values(self):
        result = summarize_site_batch_channel_loads([{
            "channelLoads2g": [{"channel": 1, "load": 10}, {"channel": 6, "load": 30}],
            "channelLoads5g": [{"channel": 36, "load": 50}],
            "channelLoads6g": [],
            "mac": "00:11:22:33:44:55",
        }])
        self.assertEqual(result["data"]["bands"]["2g"], {
            "returned_channel_count": 2, "minimum_load": 10,
            "maximum_load": 30, "average_load": 20.0})
        self.assertEqual(result["data"]["bands"]["5g"]["average_load"], 50.0)
        self.assertNotIn("channelLoads", repr(result))
        self.assertNotIn("'channel':", repr(result))
        self.assertNotIn("00:11:22:33:44:55", repr(result))

    def test_marks_missing_optional_fields_and_invalid_rows_partial(self):
        result = summarize_site_batch_channel_loads([{"channelLoads2g": [None]}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["omitted_value_count"], 1)

    def test_unknown_fields_are_counted_and_mark_partial(self):
        result = summarize_site_batch_channel_loads([{
            "channelLoads2g": [{"channel": 1, "load": 8, "deviceMac": "private"}],
            "channelLoads5g": [], "channelLoads6g": [], "extra": True}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["unknown_field_count"], 2)
        self.assertNotIn("private", repr(result))

    def test_rejects_unbounded_shapes_and_malformed_lists(self):
        with self.assertRaises(SiteBatchChannelLoadSummaryError):
            summarize_site_batch_channel_loads({})
        with self.assertRaises(SiteBatchChannelLoadSummaryError):
            summarize_site_batch_channel_loads([{"channelLoads2g": "invalid"}])
        with self.assertRaises(SiteBatchChannelLoadSummaryError):
            summarize_site_batch_channel_loads([{"channelLoads2g": [{"channel": 1, "load": 1}] * 257}])


if __name__ == "__main__":
    unittest.main()
