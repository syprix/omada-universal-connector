import unittest

from app.site_lan_network_interface_summary import (
    SiteLanNetworkInterfaceSummaryError, summarize_site_lan_network_interfaces,
)


def network(**overrides):
    row = {
        "id": "private-id", "name": "Office VLAN", "purpose": 1,
        "interfaceIds": ["router-port-private"], "vlanType": 0, "vlan": 120,
        "application": 0, "gatewaySubnet": "192.0.2.1/24", "igmpSnoopEnable": True,
    }
    row.update(overrides)
    return row


class SiteLanNetworkInterfaceSummaryTests(unittest.TestCase):
    def test_counts_network_and_interface_categories_without_values(self):
        result = summarize_site_lan_network_interfaces(
            [network(), network(vlanType=1, purpose=1), network(purpose=0)], None)
        self.assertEqual(result["purpose_counts"], {"vlan": 1, "interface": 2, "unknown": 0})
        self.assertEqual(result["interface_vlan_type_counts"], {
            "single": 1, "multiple": 1, "unknown": 0})
        self.assertEqual(result["application_scope_counts"]["gateway_and_switch"], 3)
        self.assertEqual(result["interface_association_counts"]["identifier_count"], 3)
        self.assertEqual(result["gateway_subnet_presence"]["present"], 3)
        self.assertFalse(result["partial"])
        for secret in ("private-id", "Office VLAN", "router-port-private", "192.0.2.1", "120"):
            self.assertNotIn(secret, str(result))
        self.assertFalse(result["router_or_vlan_mapping_inferred_from_interface_ids"])

    def test_type_filter_only_accepts_documented_zero_and_checks_response(self):
        result = summarize_site_lan_network_interfaces([network()], 0)
        self.assertEqual(result["interface_type_filter"], "single_only")
        inconsistent = summarize_site_lan_network_interfaces([network(vlanType=1)], 0)
        self.assertTrue(inconsistent["partial"])
        with self.assertRaises(SiteLanNetworkInterfaceSummaryError):
            summarize_site_lan_network_interfaces([network()], 1)

    def test_missing_fields_and_unrecognized_values_mark_partial(self):
        result = summarize_site_lan_network_interfaces(
            [network(purpose=4, vlanType=8, application=7, extra="unknown")], None)
        self.assertTrue(result["partial"])
        self.assertEqual(result["purpose_counts"]["unknown"], 1)
        self.assertEqual(summarize_site_lan_network_interfaces([{}], None)["partial"], True)

    def test_rejects_wrong_documented_types(self):
        for row in (network(purpose=True), network(interfaceIds="private"),
                    network(igmpSnoopEnable=1), network(gatewaySubnet=3)):
            with self.subTest(row=row), self.assertRaises(SiteLanNetworkInterfaceSummaryError):
                summarize_site_lan_network_interfaces([row], None)


if __name__ == "__main__":
    unittest.main()
