import unittest

from app.site_ssid_topology_device_summary import project_site_ssid_topology_devices


class SiteSsidTopologyDeviceSummaryTests(unittest.TestCase):
    def test_counts_only_matched_inventory_classes(self):
        result = project_site_ssid_topology_devices(
            ["AA:BB:CC:DD:EE:01", "aa-bb-cc-dd-ee-02", "aa:bb:cc:dd:ee:03"],
            {"ap": "aa:bb:cc:dd:ee:01", "sw": "aa:bb:cc:dd:ee:02"},
            {"ap": "Access Point", "sw": "Switch"})
        self.assertEqual(result["device_class_counts"],
                         {"ap": 1, "gateway": 0, "switch": 1, "olt": 0})
        self.assertEqual(result["unmatched_topology_device_count"], 1)
        self.assertNotIn("aa:bb:cc:dd:ee:01", str(result))
        self.assertTrue(result["partial"])

    def test_ambiguous_inventory_is_not_double_counted(self):
        result = project_site_ssid_topology_devices(
            ["aa:bb:cc:dd:ee:01"],
            {"a": "aa:bb:cc:dd:ee:01", "b": "aa-bb-cc-dd-ee-01"},
            {"a": "ap", "b": "ap"})
        self.assertEqual(result["ambiguous_inventory_count"], 1)
        self.assertEqual(result["matched_device_count"], 0)


if __name__ == "__main__":
    unittest.main()
