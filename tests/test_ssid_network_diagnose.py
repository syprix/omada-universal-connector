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
        self.assertEqual(len(seen), 7)
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

    def test_rejects_invalid_site_ref_and_non_callable_requester(self):
        with self.assertRaisesRegex(SsidNetworkDiagnoseError, "site_ref_invalid"):
            run_site("../invalid", lambda path: None)
        with self.assertRaisesRegex(SsidNetworkDiagnoseError, "connector_unavailable"):
            run_site(self.site_ref, None)


if __name__ == "__main__":
    unittest.main()
