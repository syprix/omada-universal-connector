import unittest

from app.site_network_delivery_summary import (
    SiteNetworkDeliveryError, project_site_network_delivery,
)


class SiteNetworkDeliverySummaryTests(unittest.TestCase):
    def test_counts_delivery_state_arrays_and_redacts_ids(self):
        result = project_site_network_delivery({
            "successDevices": ["private-device"], "successStacks": ["private-stack"],
            "failDevices": [], "failStacks": [],
            "deliveringDevices": ["active-device"], "deliveringStacks": [],
            "doneDevicesNum": 1, "totalDevicesNum": 2, "state": 1,
        })
        self.assertEqual(result["state"], "delivering")
        self.assertEqual(result["device_counts"],
                         {"succeeded": 1, "failed": 0, "delivering": 1})
        self.assertEqual(result["stack_counts"],
                         {"succeeded": 1, "failed": 0, "delivering": 0})
        self.assertNotIn("private-device", str(result))
        self.assertNotIn("active-device", str(result))
        self.assertFalse(result["reachability_inferred"])
        self.assertFalse(result["partial"])

    def test_inconsistent_progress_is_partial_and_missing_fields_are_unknown(self):
        result = project_site_network_delivery({"successDevices": ["d"],
                                                "doneDevicesNum": 0,
                                                "totalDevicesNum": 0, "state": 0})
        self.assertTrue(result["partial"])
        missing = project_site_network_delivery({})
        self.assertEqual(missing["state"], "unknown")
        self.assertTrue(missing["partial"])

    def test_rejects_unknown_states_and_invalid_counts(self):
        for payload in ({"state": 3}, {"state": True}, {"doneDevicesNum": -1},
                        {"successDevices": [1]}):
            with self.subTest(payload=payload), self.assertRaises(SiteNetworkDeliveryError):
                project_site_network_delivery(payload)


if __name__ == "__main__":
    unittest.main()
