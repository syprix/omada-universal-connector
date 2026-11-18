from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class SwitchPortNameOpenApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=2, max_pages=4))
        self.site_ref, self.switch_ref = "a" * 24, "b" * 24
        self.switch_mac = "00:11:22:33:44:55"
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._switch_macs_by_site_ref[self.site_ref] = {
            self.switch_ref: self.switch_mac}

    def test_capability_evidence_is_bound_to_site_and_switch(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=[{
                    "switchMac": self.switch_mac, "port": 7, "portName": "Old label"}]) as read:
            result = self.client.read_switch_port_name(self.site_ref, self.switch_ref, 7)
        read.assert_called_once_with(
            "/openapi/v1/ctrl/sites/site_1/switches/ports/overview", "token")
        self.assertEqual(result["data"], {"name": "Old label"})
        self.assertIn(("switch_port_name", self.site_ref + ":" + self.switch_ref),
                      self.client._capability_evidence)
        self.assertNotIn(("switch_port_name", self.site_ref),
                         self.client._capability_evidence)

    def test_target_validator_and_put_body_reject_all_edge_whitespace(self) -> None:
        for name in ("\u00a0name", "name\u00a0", "\u2003name", "name\u2003"):
            with self.subTest(name=repr(name)):
                self.assertFalse(self.client._valid_switch_port_name(name))
                self.assertFalse(self.client._valid_switch_port_name_body(
                    ('{"name":' + json.dumps(name) + "}").encode("ascii")))

        self.assertTrue(self.client._valid_switch_port_name("inside\u00a0space"))

    def test_invalid_edge_whitespace_is_rejected_before_any_transport(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json") as request:
            for name in ("\u00a0name", "name\u2003"):
                with self.subTest(name=repr(name)), self.assertRaisesRegex(
                        OpenApiError, "switch_port_name_invalid"):
                    self.client.put_switch_port_name(
                        self.site_ref, self.switch_ref, 7, {"name": name})
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
