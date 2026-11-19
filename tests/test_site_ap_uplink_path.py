from __future__ import annotations

import unittest

from app.site_ap_uplink_path import (
    SiteApUplinkPathError,
    summarize_site_ap_uplink_paths,
)


SITE = "a" * 24
AP_A = "b" * 24
AP_B = "c" * 24
SWITCH = "d" * 24


class SiteApUplinkPathTests(unittest.TestCase):
    def test_joins_wired_and_mesh_hops_to_current_inventory_references(self):
        inventory = [
            {"device_ref": AP_A, "device_type": "AP", "state": 1,
             "model": "EAP-X", "firmware": "1.2.3"},
            {"device_ref": AP_B, "device_type": "AP", "state": 1},
            {"device_ref": SWITCH, "device_type": "Switch", "state": 1},
        ]
        wired = {
            AP_A: {"status": "ok", "data": {"wiredUplink": {
                "rate_mbps": 1000, "uplink_device_ref_status": "mapped",
                "uplink_device_ref": SWITCH, "upErrorsPackets": 2,
                "upDropPackets": 1}}},
            AP_B: {"status": "ok", "data": {"wiredUplink": {
                "rate_mbps": 0, "uplink_device_ref_status": "not_in_inventory"}}},
        }
        mesh = {
            AP_A: {"status": "ok", "data": {"wireless_linked": False}},
            AP_B: {"status": "ok", "data": {
                "wireless_linked": True,
                "wireless_uplink": {"uplink_ap_ref_status": "mapped",
                                    "uplink_ap_ref": AP_A, "rssi": -60, "snr": 30,
                                    "tx_rate_mbps": 600, "rx_rate_mbps": 500},
            }},
        }
        result = summarize_site_ap_uplink_paths(
            SITE, [AP_A, AP_B], inventory, wired, mesh)
        self.assertEqual(result["aps"][0]["path"]["link_kind"], "wired")
        self.assertEqual(result["aps"][0]["path"]["next_hop_ref"], SWITCH)
        self.assertIn("reported_uplink_errors_nonzero",
                      result["aps"][0]["review_signals"])
        self.assertIn("reported_uplink_drops_nonzero",
                      result["aps"][0]["review_signals"])
        self.assertEqual(result["aps"][1]["path"]["link_kind"], "mesh")
        self.assertEqual(result["aps"][1]["path"]["next_hop_ref"], AP_A)
        self.assertEqual(result["aps"][1]["path"]["continuation"],
                         "selected_device_included")
        self.assertEqual(result["aps"][1]["mesh_link"]["rssi"], -60)
        self.assertFalse(result["partial"])
        self.assertNotIn("mac", repr(result).lower())

    def test_unmapped_hop_and_unavailable_source_remain_unknown_and_partial(self):
        result = summarize_site_ap_uplink_paths(SITE, [AP_A], [
            {"device_ref": AP_A, "device_type": "AP", "state": 3}
        ], {AP_A: {"status": "error"}}, {AP_A: {"status": "ok", "data": {
            "wireless_linked": True,
            "wireless_uplink": {"uplink_ap_ref_status": "not_in_ap_inventory",
                                  "rssi": -70},
        }}})
        self.assertEqual(result["aps"][0]["path"]["link_kind"], "mesh")
        self.assertIsNone(result["aps"][0]["path"]["next_hop_ref"])
        self.assertEqual(result["source_coverage"]["unavailable_wired_uplink_count"], 1)
        self.assertEqual(result["source_coverage"]["unmapped_next_hop_count"], 1)
        self.assertIn("mesh_parent_not_mapped", result["aps"][0]["review_signals"])
        self.assertIn("device_inventory_reports_heartbeat_missed",
                      result["aps"][0]["review_signals"])
        self.assertTrue(result["partial"])

    def test_partial_sources_are_not_misreported_as_unavailable(self):
        result = summarize_site_ap_uplink_paths(SITE, [AP_A], [
            {"device_ref": AP_A, "device_type": "AP", "state": 1}
        ], {AP_A: {"status": "ok", "data": {"wiredUplink": {"rate_mbps": 1000}},
                   "partial": True}}, {AP_A: {"status": "ok", "data": {
            "wireless_linked": False}, "partial": True}})
        self.assertEqual(result["source_coverage"]["unavailable_wired_uplink_count"], 0)
        self.assertEqual(result["source_coverage"]["unavailable_mesh_statistics_count"], 0)
        self.assertEqual(result["source_coverage"]["partial_ap_count"], 1)
        self.assertIn("wired_uplink_partial", result["aps"][0]["review_signals"])
        self.assertIn("mesh_statistics_partial", result["aps"][0]["review_signals"])
        self.assertTrue(result["partial"])

    def test_positive_wired_rate_evidences_one_hop_when_mesh_read_fails(self):
        result = summarize_site_ap_uplink_paths(SITE, [AP_A], [
            {"device_ref": AP_A, "device_type": "AP", "state": 1},
            {"device_ref": SWITCH, "device_type": "Switch", "state": 1},
        ], {AP_A: {"status": "ok", "data": {"wiredUplink": {
            "rate_mbps": 1000, "uplink_device_ref": SWITCH}}}},
             {AP_A: {"status": "error"}})
        self.assertEqual(result["aps"][0]["path"]["link_kind"], "wired")
        self.assertEqual(result["aps"][0]["path"]["next_hop_ref"], SWITCH)
        self.assertEqual(result["source_coverage"]["unavailable_mesh_statistics_count"], 1)
        self.assertEqual(result["source_coverage"]["unknown_path_count"], 0)
        self.assertTrue(result["partial"])

    def test_rejects_duplicate_unbounded_and_noninventory_ap_refs(self):
        inventory = [{"device_ref": AP_A, "device_type": "AP"}]
        with self.assertRaises(SiteApUplinkPathError):
            summarize_site_ap_uplink_paths(SITE, [AP_A, AP_A], inventory, {}, {})
        with self.assertRaises(SiteApUplinkPathError):
            summarize_site_ap_uplink_paths(SITE, [], inventory, {}, {})
        with self.assertRaises(SiteApUplinkPathError):
            summarize_site_ap_uplink_paths(SITE, [AP_B], inventory, {}, {})


if __name__ == "__main__":
    unittest.main()
