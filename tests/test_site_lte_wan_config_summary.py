import unittest

from app.site_lte_wan_config_summary import (
    SiteLteWanConfigError, summarize_site_lte_wan_config,
)


class SiteLteWanConfigSummaryTests(unittest.TestCase):
    def test_counts_configuration_and_status_separately_and_redacts_private_values(self):
        row = {
            "portUuId": "private-port-uuid", "portName": "private LTE port",
            "status": 3, "cardStatus": 4, "simCardUsed": 1, "simPriority": 2,
            "mobileData": True, "dataRoaming": False, "networkMode": 4, "bandMode": 1,
            "bands": ["n78"], "bands5g": ["n78"],
            "dialupSetting": {"networkSearch": 1, "isp": "private carrier",
                              "ispNum": 310, "apnMode": 1, "apn": "private.apn"},
            "failoverTimeout": 500, "dataRoaming2": True, "networkMode2": 6,
            "bandMode2": 0, "dialupSetting2": {"networkSearch": 0, "apnMode": 0},
            "failoverTimeout2": 100, "supportNetworkMode": [3, 4, 5],
        }
        result = summarize_site_lte_wan_config({
            "portUuid": "private-parent-uuid", "portName": "private parent",
            "portDesc": "private description", "lteWanPortsConfig": [row],
        })
        self.assertEqual(result["configured_flags"]["mobile_data"],
                         {"enabled": 1, "disabled": 0, "unreported": 0})
        self.assertEqual(result["network_mode_code_counts"]["sim1"]["4"], 1)
        self.assertEqual(result["documented_modem_status_code_counts"]["3"], 1)
        self.assertEqual(result["documented_sim_card_status_code_counts"]["4"], 1)
        self.assertEqual(result["failover_timeout_configured_count"]["sim1"], 1)
        self.assertFalse(result["partial"])
        rendered = repr(result)
        for private in ("private-port-uuid", "private LTE port", "private parent",
                        "private description", "private carrier", "private.apn", "n78"):
            self.assertNotIn(private, rendered)

    def test_missing_unknown_and_truncated_values_remain_visible(self):
        result = summarize_site_lte_wan_config(
            {"portUuid": "private", "portName": "private", "portDesc": "private",
             "lteWanPortsConfig": [{"mobileData": "yes", "status": 9}, {}]}, max_items=1)
        self.assertTrue(result["truncated"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_record_count"], 0)
        self.assertEqual(result["configured_flags"]["mobile_data"]["unreported"], 1)
        self.assertEqual(result["documented_modem_status_code_counts"]["unknown"], 1)

    def test_invalid_list_is_rejected_and_invalid_rows_are_counted(self):
        with self.assertRaises(SiteLteWanConfigError):
            summarize_site_lte_wan_config({"lteWanPortsConfig": "bad"})
        result = summarize_site_lte_wan_config(
            {"lteWanPortsConfig": [{f"field_{n}": True for n in range(65)}]})
        self.assertEqual(result["invalid_record_count"], 1)
        self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
