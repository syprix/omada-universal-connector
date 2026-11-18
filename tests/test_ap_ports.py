import unittest

from app.ap_ports import ApPortsError, summarize_ap_ports


class ApPortsTests(unittest.TestCase):
    def test_counts_link_and_capability_codes_without_port_identity(self) -> None:
        result = summarize_ap_ports([
            {"id": "secret-id", "name": "private label", "port": 1, "lanPort": "LAN1",
             "linkStatus": 1, "linkSpeed": 3, "duplex": 2, "portType": 4,
             "supportPoe": True, "poeOutEnable": True, "poeState": 0,
             "poeInputMode": 2, "uplinkPort": True, "logicUplinkPort": True,
             "supportVlan": True, "localVlanEnable": False, "localVlanId": 22,
             "localVlanNetworkId": "secret-network"},
            {"port": 2, "linkStatus": 0, "linkSpeed": 2, "duplex": 1,
             "supportPoe": False, "poeOutEnable": False, "uplinkPort": False,
             "supportVlan": False, "localVlanEnable": False},
        ])
        self.assertEqual(result["summary"]["by_link_status_code"], {0: 1, 1: 1})
        self.assertEqual(result["summary"]["by_link_speed_code"], {2: 1, 3: 1})
        self.assertEqual(result["summary"]["uplink_ports"], 1)
        self.assertEqual(result["summary"]["poe_supported_ports"], 1)
        self.assertEqual(result["summary"]["poe_state_code_counts"], {0: 1})
        for private in ("secret-id", "private label", "LAN1", "secret-network", "localVlanId"):
            self.assertNotIn(private, repr(result))
        self.assertFalse(result["partial"])

    def test_marks_malformed_or_unknown_values_partial(self) -> None:
        result = summarize_ap_ports([{"linkStatus": 8, "supportPoe": "true", "vendorField": 1}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["summary"]["invalid_field_count"], 2)
        self.assertEqual(result["summary"]["unknown_field_count"], 1)

    def test_bounds_rows(self) -> None:
        with self.assertRaises(ApPortsError):
            summarize_ap_ports([{}] * 129)


if __name__ == "__main__":
    unittest.main()
