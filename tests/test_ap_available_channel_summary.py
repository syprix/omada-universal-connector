import unittest

from app.ap_available_channel_summary import summarize_ap_available_channels


class ApAvailableChannelSummaryTests(unittest.TestCase):
    def test_losslessly_compacts_documented_channel_fields_by_radio(self):
        result = summarize_ap_available_channels([
            {"radioId": 0, "apChannelDetailList": [
                {"channel": 1, "freq": 2412, "index": 1,
                 "availableChannelWidthList": [20, 40]},
                {"channel": 2, "freq": 2437, "index": 2,
                 "availableChannelWidthList": [20]}]},
            {"radioId": 3, "apChannelDetailList": [
                {"channel": 5, "freq": 5955, "index": 2,
                 "availableChannelWidthList": [80, 160]}]},
        ])
        self.assertEqual(result["data"]["radios"][0]["channels"],
                         [[1, 2412, 1, [20, 40]], [2, 2437, 2, [20]]])
        self.assertEqual(result["data"]["radios"][1]["band"], "6ghz")
        self.assertEqual(result["data"]["radios"][1]["channels"], [[5, 5955, 2, [80, 160]]])
        self.assertFalse(result["partial"])

    def test_unknown_fields_and_incomplete_optional_channel_values_mark_partial(self):
        result = summarize_ap_available_channels([{
            "radioId": 0, "other": 1, "apChannelDetailList": [
                {"channel": 1, "freq": 2412, "index": None,
                 "availableChannelWidthList": [20], "extra": "secret"}] }])
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["unknown_field_count"], 2)
        self.assertEqual(result["data"]["radios"][0]["channels"], [[1, 2412, None, [20]]])
        self.assertNotIn("secret", repr(result))

    def test_invalid_shape_and_undocumented_radio_are_bounded(self):
        with self.assertRaises(ValueError):
            summarize_ap_available_channels({})
        result = summarize_ap_available_channels([{
            "radioId": 9, "apChannelDetailList": []}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["unknown_radio_count"], 1)


if __name__ == "__main__":
    unittest.main()
