import unittest

from app.site_lan_multicast_summary import (
    SiteLanMulticastSummaryError, summarize_site_lan_multicasts,
)


def multicast(**overrides):
    row = {
        "id": "private-id", "name": "Private Multicast", "networks": [{
            "networkId": "private-network", "networkName": "Private LAN", "vlan": 120}],
        "protocol": 0, "unknownMulticastRule": 2,
        "unknownMulticastExceptDevice": {"enable": True, "deviceList": [{"mac": "secret"}]},
        "floodKnownEnable": True, "querierEnable": False, "routerPortEnable": True,
        "snoopConfig": {"reportSuppressionEnable": True,
                         "reportSuppressionExceptDevice": {"enable": False, "deviceList": []}},
        "routerPorts": [], "igmpQueriers": [], "mldQueriers": [], "resource": 0,
    }
    row.update(overrides)
    return row


class SiteLanMulticastSummaryTests(unittest.TestCase):
    def test_counts_documented_settings_and_redacts_values(self):
        result = summarize_site_lan_multicasts([multicast(), multicast(protocol=1,
                    unknownMulticastRule=0)], 2, 1, 10)
        self.assertEqual(result["protocol_counts"], {"igmp": 1, "mld": 1, "unknown": 0})
        self.assertEqual(result["unknown_multicast_rule_counts"], {
            "forward": 1, "discard": 0, "router_port_first": 1, "unknown": 0})
        self.assertEqual(result["feature_flag_counts"]["querier"], {
            "enabled": 0, "disabled": 2, "unknown": 0})
        self.assertFalse(result["partial"])
        for secret in ("private-id", "Private Multicast", "private-network", "Private LAN", "secret", "120"):
            self.assertNotIn(secret, str(result))
        self.assertTrue(result["configuration_only_no_multicast_traffic_inferred"])

    def test_unknown_values_missing_fields_and_unknown_properties_mark_partial(self):
        result = summarize_site_lan_multicasts([multicast(protocol=8, unknownMulticastRule=8,
                    additionalSetting=True)], 1, 1, 1)
        self.assertTrue(result["partial"])
        self.assertEqual(result["protocol_counts"]["unknown"], 1)
        self.assertEqual(result["unknown_multicast_rule_counts"]["unknown"], 1)
        self.assertTrue(summarize_site_lan_multicasts([{}], 1, 1, 1)["partial"])

    def test_rejects_invalid_types(self):
        for row in (multicast(protocol=True), multicast(querierEnable=1),
                    multicast(networks="invalid"), multicast(snoopConfig=[])):
            with self.subTest(row=row), self.assertRaises(SiteLanMulticastSummaryError):
                summarize_site_lan_multicasts([row], 1, 1, 1)


if __name__ == "__main__":
    unittest.main()
