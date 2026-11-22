import unittest
from app.site_bridge_device_summary import (
    SiteBridgeDeviceSummaryError, summarize_site_bridge_devices,
)


class SiteBridgeDeviceSummaryTests(unittest.TestCase):
    def test_counts_adopted_pending_status_and_stack_coverage(self):
        result = summarize_site_bridge_devices(
            {"totalRows": 1, "data": [{"mac": "00:11:22:33:44:55", "name": "Private bridge",
                                        "type": "bridge", "status": 3, "detailStatus": 2}],
             "stackData": [{"stackId": "secret", "stackName": "Private group",
                            "stackStatus": 4}]},
            {"totalRows": 1, "data": [{"mac": "00:11:22:33:44:66", "sn": "secret-sn",
                                        "type": "bridge", "status": 0, "detailStatus": 1}]},
        )
        self.assertEqual(result["adopted"]["by_source_status_code"], {"3": 1})
        self.assertEqual(result["pending"]["by_source_status_code"], {"0": 1})
        self.assertEqual(result["adopted"]["stack_groups"]["by_status_code"], {"4": 1})
        self.assertTrue(result["adopted"]["coverage_complete"])
        for secret in ("00:11:22:33:44:55", "Private bridge", "secret", "secret-sn"):
            self.assertNotIn(secret, str(result))

    def test_missing_group_coverage_or_invalid_rows_are_partial(self):
        result = summarize_site_bridge_devices(
            {"totalRows": 2, "data": [{"type": "bridge", "status": 0}],
             "stackData": []},
            {"totalRows": 1, "data": [None]},
        )
        self.assertTrue(result["partial"])
        self.assertFalse(result["adopted"]["coverage_complete"])
        self.assertEqual(result["pending"]["invalid_row_count"], 1)

    def test_invalid_grid_rejected(self):
        with self.assertRaises(SiteBridgeDeviceSummaryError):
            summarize_site_bridge_devices({}, {"data": [], "totalRows": 0})


if __name__ == "__main__":
    unittest.main()
