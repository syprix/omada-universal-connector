import unittest
from app.site_ssid_topology_reference_count import (
    SsidTopologyReferenceError, count_ssid_topology_references,
)

class SsidTopologyReferenceCountTests(unittest.TestCase):
    def test_counts_strings_as_opaque_references(self):
        result = count_ssid_topology_references({"errorCode": 0, "msg": "", "result": ["x", "not-a-mac", "x"]})
        self.assertEqual(result["reference_count"], 3)
        self.assertEqual(result["reference_semantics"], "opaque_string")
        self.assertNotIn("not-a-mac", str(result))

    def test_rejects_missing_or_invalid_operation_response_envelope(self):
        for payload in ({"result": []}, {"errorCode": 0, "result": [1]},
                        {"errorCode": 1, "msg": "bad", "result": []}):
            with self.subTest(payload=payload), self.assertRaises(SsidTopologyReferenceError):
                count_ssid_topology_references(payload)

if __name__ == "__main__": unittest.main()
