from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class SwitchPortTagsIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller_1", "client-id", "client-secret",
            tls_trust="system_ca",
        ))
        self.client._site_ids_by_ref["a" * 24] = "site_1"

    def test_reads_site_route_and_drops_tag_content(self) -> None:
        with patch.object(self.client, "_access_token", return_value="fixture-token"), \
                patch.object(self.client, "_request_json", return_value={"result": [
                    {"tagId": "private-tag", "name": "private-label", "resource": 1},
                ]}) as request:
            result = self.client.list_switch_port_tags("a" * 24)
        request.assert_called_once_with(
            "GET", "/openapi/v1/controller_1/sites/site_1/switches/port-tag",
            token="fixture-token")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["summary"]["by_resource_code"], {1: 1})
        self.assertNotIn("private-tag", repr(result))
        self.assertNotIn("private-label", repr(result))

    def test_rejects_unknown_site_before_upstream_request(self) -> None:
        with self.assertRaises(OpenApiError) as error:
            self.client.list_switch_port_tags("b" * 24)
        self.assertEqual(error.exception.code, "site_ref_unknown")


if __name__ == "__main__":
    unittest.main()
