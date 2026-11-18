import unittest

from app.ssid_network_diagnose import SsidNetworkDiagnoseError, run_site


class SsidNetworkDiagnoseTests(unittest.TestCase):
    site_ref = "a" * 24
    ssid_refs = [f"{value:024x}" for value in range(1, 5)]
    network_refs = [f"{value:024x}" for value in range(10, 12)]

    def inventories(self, ssid_refs=None, network_refs=None):
        ssid_refs = self.ssid_refs if ssid_refs is None else ssid_refs
        network_refs = self.network_refs if network_refs is None else network_refs
        return {
            "/v1/sites": {"status": "ok", "resource": "sites", "count": 1,
                           "items": [{"site_ref": self.site_ref, "site_name": "private-site"}]},
            f"/v1/sites/{self.site_ref}/ssids": {
                "status": "ok", "resource": "ssids", "count": len(ssid_refs),
                "items": [{"ssid_ref": ref, "ssid_name": "private-wlan"} for ref in ssid_refs]},
            f"/v1/sites/{self.site_ref}/networks": {
                "status": "ok", "resource": "networks", "count": len(network_refs),
                "items": [{"network_ref": ref, "name": "private-lan"} for ref in network_refs]},
        }

    def test_reconciles_refs_to_coarse_counts_without_exposing_identity(self):
        replies = self.inventories()
        details = (
            {"status": "ok", "resource": "ssid_configuration", "site_ref": self.site_ref,
             "data": {"ssid_ref": self.ssid_refs[0], "network_binding_ref": self.network_refs[0]}},
            {"status": "ok", "resource": "ssid_configuration", "site_ref": self.site_ref,
             "data": {"ssid_ref": self.ssid_refs[1]}},
            {"status": "ok", "resource": "ssid_configuration", "site_ref": self.site_ref,
             "data": {"ssid_ref": self.ssid_refs[2], "network_binding_ref": "f" * 24}},
        )
        for ref, result in zip(self.ssid_refs, (*details, {"status": "error"})):
            replies[f"/v1/sites/{self.site_ref}/ssids/{ref}"] = result
        seen = []

        def request(path):
            seen.append(path)
            return replies[path]

        result = run_site(self.site_ref, request)
        self.assertEqual(result["matched_count"], 1)
        self.assertEqual(result["unbound_count"], 1)
        self.assertEqual(result["stale_binding_count"], 1)
        self.assertEqual(result["unreadable_count"], 1)
        self.assertTrue(result["partial"])
        self.assertEqual(len(seen), 12)
        rendered = str(result)
        for private_value in (*self.ssid_refs, *self.network_refs, "private-site", "private-wlan", "private-lan"):
            self.assertNotIn(private_value, rendered)

    def test_bounds_detail_requests_and_marks_omitted_ssids_partial(self):
        refs = [f"{value:024x}" for value in range(100)]
        replies = self.inventories(ssid_refs=refs)
        for ref in refs[:64]:
            replies[f"/v1/sites/{self.site_ref}/ssids/{ref}"] = {
                "status": "ok", "resource": "ssid_configuration", "site_ref": self.site_ref,
                "data": {"ssid_ref": ref}}
        detail_calls = []

        def request(path):
            if "/ssids/" in path:
                detail_calls.append(path)
            return replies[path]

        result = run_site(self.site_ref, request)
        self.assertEqual(result["inspected_count"], 64)
        self.assertEqual(result["omitted_count"], 36)
        self.assertEqual(len(detail_calls), 64)
        self.assertTrue(result["partial"])

    def test_rejects_wrong_site_and_duplicate_inventory_refs(self):
        replies = self.inventories()
        replies["/v1/sites"] = {"status": "ok", "resource": "sites", "count": 0, "items": []}
        with self.assertRaisesRegex(SsidNetworkDiagnoseError, "site_ref_unknown"):
            run_site(self.site_ref, lambda path: replies[path])

        replies = self.inventories(ssid_refs=[self.ssid_refs[0], self.ssid_refs[0]])
        with self.assertRaisesRegex(SsidNetworkDiagnoseError, "ssids_inventory_invalid"):
            run_site(self.site_ref, lambda path: replies[path])

    def test_invalid_detail_reference_is_counted_without_stopping_other_reads(self):
        replies = self.inventories(ssid_refs=self.ssid_refs[:2])
        replies[f"/v1/sites/{self.site_ref}/ssids/{self.ssid_refs[0]}"] = {
            "status": "ok", "resource": "ssid_configuration", "site_ref": self.site_ref,
            "data": {"ssid_ref": self.ssid_refs[0], "network_binding_ref": "not-a-ref"}}
        replies[f"/v1/sites/{self.site_ref}/ssids/{self.ssid_refs[1]}"] = {
            "status": "ok", "resource": "ssid_configuration", "site_ref": self.site_ref,
            "data": {"ssid_ref": self.ssid_refs[1], "network_binding_ref": self.network_refs[1]}}
        result = run_site(self.site_ref, lambda path: replies[path])
        self.assertEqual(result["unreadable_count"], 1)
        self.assertEqual(result["matched_count"], 1)
        self.assertTrue(result["partial"])

    def test_adds_bounded_vlan_dhcp_dns_and_gateway_evidence(self):
        replies = self.inventories(ssid_refs=self.ssid_refs[:1], network_refs=self.network_refs[:1])
        network_ref, ssid_ref = self.network_refs[0], self.ssid_refs[0]
        root = f"/v1/sites/{self.site_ref}"
        replies[f"{root}/ssids/{ssid_ref}"] = {
            "status": "ok", "resource": "ssid_configuration", "site_ref": self.site_ref,
            "data": {"ssid_ref": ssid_ref, "network_binding_ref": network_ref}}
        replies[root + "/devices"] = {
            "status": "ok", "resource": "devices", "site_ref": self.site_ref,
            "count": 1, "items": [{"device_ref": "e" * 24, "device_type": "gateway"}]}
        replies[root + "/dns/cache"] = {
            "status": "ok", "resource": "dns_cache_settings", "data": {"enabled": True}}
        replies[root + "/dns/proxy"] = {
            "status": "ok", "resource": "dns_proxy_settings",
            "data": {"enabled": True, "mode": "doh", "resolver": "private.example"}}
        replies[f"{root}/lan-networks/{network_ref}/summary"] = {
            "status": "ok", "resource": "site_lan_network_detail_summary",
            "site_ref": self.site_ref, "network_ref": network_ref,
            "data": {"purpose_label": "vlan", "vlan": 20}}
        replies[f"{root}/networks/{network_ref}/dhcp-server/info"] = {
            "status": "ok", "resource": "network_dhcp_server_info",
            "site_ref": self.site_ref, "network_ref": network_ref,
            "data": {"range_count": 2}, "partial": False}
        gateway_ref = "e" * 24
        replies[f"{root}/gateways/{gateway_ref}/internet-info"] = {
            "status": "ok", "resource": "gateway_internet_info",
            "site_ref": self.site_ref, "device_ref": gateway_ref, "data": {}}

        result = run_site(self.site_ref, lambda path: replies[path])
        checks = result["network_checks"]
        self.assertEqual(checks["checked_network_count"], 1)
        self.assertEqual(checks["vlan_observed_network_count"], 1)
        self.assertEqual(checks["distinct_vlan_count"], 1)
        self.assertEqual(checks["dhcp_pool_range_count"], 2)
        self.assertEqual(checks["dns"]["status"], "partial")
        self.assertEqual(checks["dns"]["cache_status"], "partial")
        self.assertEqual(checks["dns"]["proxy_status"], "partial")
        self.assertEqual(checks["dns"]["network_specific_mapping"], "unknown")
        self.assertEqual(checks["gateway_inventory_count"], 1)
        self.assertEqual(checks["gateway_internet_info_checked_count"], 1)
        self.assertEqual(checks["gateway_network_attachment"], "unknown")
        for private_value in (self.site_ref, network_ref, gateway_ref, "private.example"):
            self.assertNotIn(private_value, str(result))

    def test_failed_and_unclassified_sources_remain_unknown(self):
        replies = self.inventories(ssid_refs=self.ssid_refs[:1], network_refs=self.network_refs[:1])
        root = f"/v1/sites/{self.site_ref}"
        ssid_ref, network_ref = self.ssid_refs[0], self.network_refs[0]
        replies[f"{root}/ssids/{ssid_ref}"] = {
            "status": "ok", "resource": "ssid_configuration", "site_ref": self.site_ref,
            "data": {"ssid_ref": ssid_ref, "network_binding_ref": network_ref}}
        replies[root + "/devices"] = {
            "status": "ok", "resource": "devices", "site_ref": self.site_ref,
            "count": 1, "items": [{"device_ref": "e" * 24, "device_type": "other"}]}
        replies[f"{root}/lan-networks/{network_ref}/summary"] = {
            "status": "ok", "resource": "site_lan_network_detail_summary",
            "site_ref": self.site_ref, "network_ref": network_ref, "data": {}}
        replies[f"{root}/networks/{network_ref}/dhcp-server/info"] = {
            "status": "error", "error": "permission_denied"}
        result = run_site(self.site_ref, lambda path: replies[path])
        checks = result["network_checks"]
        self.assertEqual(checks["vlan_unknown_network_count"], 1)
        self.assertEqual(checks["dhcp_unknown_network_count"], 1)
        self.assertEqual(checks["gateway_inventory_classification"], "partial")
        self.assertIsNone(checks["gateway_inventory_count"])
        self.assertTrue(result["partial"])

    def test_limits_network_details_and_gateway_checks(self):
        refs = [f"{value:024x}" for value in range(100, 133)]
        replies = self.inventories(ssid_refs=refs, network_refs=refs)
        root = f"/v1/sites/{self.site_ref}"
        for ref in refs:
            replies[f"{root}/ssids/{ref}"] = {
                "status": "ok", "resource": "ssid_configuration", "site_ref": self.site_ref,
                "data": {"ssid_ref": ref, "network_binding_ref": ref}}
            replies[f"{root}/lan-networks/{ref}/summary"] = {
                "status": "ok", "resource": "site_lan_network_detail_summary",
                "site_ref": self.site_ref, "network_ref": ref,
                "data": {"purpose_label": "vlan", "vlan": 20}}
            replies[f"{root}/networks/{ref}/dhcp-server/info"] = {
                "status": "ok", "resource": "network_dhcp_server_info",
                "site_ref": self.site_ref, "network_ref": ref,
                "data": {"range_count": 1}, "partial": False}
        gateway_refs = [f"{value:024x}" for value in range(200, 205)]
        replies[root + "/devices"] = {
            "status": "ok", "resource": "devices", "site_ref": self.site_ref,
            "count": len(gateway_refs),
            "items": [{"device_ref": ref, "device_type": "gateway"}
                      for ref in gateway_refs]}
        replies[root + "/dns/cache"] = {
            "status": "ok", "resource": "dns_cache_settings", "data": {"enabled": True}}
        replies[root + "/dns/proxy"] = {
            "status": "ok", "resource": "dns_proxy_settings", "data": {"enabled": True}}
        for ref in gateway_refs[:4]:
            replies[f"{root}/gateways/{ref}/internet-info"] = {
                "status": "ok", "resource": "gateway_internet_info",
                "site_ref": self.site_ref, "device_ref": ref, "data": {}}
        seen = []
        result = run_site(self.site_ref, lambda path: seen.append(path) or replies[path])
        checks = result["network_checks"]
        self.assertEqual(checks["checked_network_count"], 32)
        self.assertEqual(checks["omitted_network_count"], 1)
        self.assertEqual(checks["gateway_internet_info_checked_count"], 4)
        self.assertEqual(checks["gateway_internet_info_omitted_count"], 1)
        self.assertEqual(sum("/lan-networks/" in path for path in seen), 32)
        self.assertEqual(sum("/dhcp-server/info" in path for path in seen), 32)
        self.assertEqual(sum("/internet-info" in path for path in seen), 4)
        self.assertTrue(result["partial"])

    def test_rejects_invalid_site_ref_and_non_callable_requester(self):
        with self.assertRaisesRegex(SsidNetworkDiagnoseError, "site_ref_invalid"):
            run_site("../invalid", lambda path: None)
        with self.assertRaisesRegex(SsidNetworkDiagnoseError, "connector_unavailable"):
            run_site(self.site_ref, None)


if __name__ == "__main__":
    unittest.main()
