import unittest

from app.site_gateway_qos_class_summary import summarize_gateway_qos_class_rows


class GatewayQosClassSummaryTests(unittest.TestCase):
    def test_counts_documented_enable_ip_version_and_class_fields(self):
        rows = [
            {"enable": True, "ipVersion": 0, "classType": 1,
             "localIp": "private-local-group", "remoteIp": "private-remote-group",
             "serviceType": "private-service", "dscp": "46", "id": "private-id"},
            {"enable": False, "ipVersion": 1, "classType": 3},
        ]
        result = summarize_gateway_qos_class_rows(rows, source_total=2)
        self.assertEqual(result["enabled_state_counts"]["enabled"], 1)
        self.assertEqual(result["enabled_state_counts"]["disabled"], 1)
        self.assertEqual(result["documented_ip_version_counts"]["0"], 1)
        self.assertEqual(result["documented_ip_version_counts"]["1"], 1)
        self.assertEqual(result["documented_class_counts"]["1"], 1)
        self.assertEqual(result["documented_class_counts"]["3"], 1)
        self.assertEqual(result["traffic_state"], "configuration only")
        for value in ("private-local-group", "private-remote-group",
                      "private-service", "private-id"):
            self.assertNotIn(value, repr(result))

    def test_unknown_missing_and_omitted_rows_are_partial(self):
        result = summarize_gateway_qos_class_rows(
            [{"enable": "yes", "ipVersion": 7, "classType": None}, {}],
            source_total=5, omitted_rows=3)
        self.assertEqual(result["enabled_state_counts"]["unknown"], 1)
        self.assertEqual(result["enabled_state_counts"]["missing"], 1)
        self.assertEqual(result["documented_ip_version_counts"]["unknown"], 1)
        self.assertEqual(result["documented_class_counts"]["unknown"], 1)
        self.assertEqual(result["omitted_rule_count"], 3)
        self.assertTrue(result["partial"])

    def test_rejects_inconsistent_source_totals(self):
        with self.assertRaises(ValueError):
            summarize_gateway_qos_class_rows([], source_total=-1)


if __name__ == "__main__":
    unittest.main()
