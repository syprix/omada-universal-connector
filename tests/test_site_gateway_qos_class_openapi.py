import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class GatewayQosClassOpenApiTests(unittest.TestCase):
    def make_client(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        site_ref = "6" * 24
        client._site_ids_by_ref[site_ref] = "site-internal"
        return client, site_ref

    def test_client_binds_site_and_reads_fixed_class_grid(self):
        client, site_ref = self.make_client()
        payload = {"errorCode": 0, "result": {
            "totalRows": 1, "currentPage": 1, "currentSize": 1,
            "data": [{"enable": True, "ipVersion": 0, "classType": 2,
                      "localIp": "private-local", "remoteIp": "private-remote",
                      "serviceType": "private-service", "dscp": "46",
                      "id": "private-rule"}],
        }}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=payload) as request:
            result = client.read_site_gateway_qos_class_summary(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-internal/qos/gateway/class-rules?page=1&pageSize=100",
            token="token")
        self.assertEqual(result["enabled_state_counts"]["enabled"], 1)
        self.assertEqual(result["documented_class_counts"]["2"], 1)
        for value in ("private-local", "private-remote", "private-service", "private-rule"):
            self.assertNotIn(value, repr(result))

    def test_request_guard_binds_controller_page_and_fixed_page_size(self):
        client, _ = self.make_client()
        self.assertTrue(client._site_gateway_qos_class_request_valid(
            "/openapi/v1/ctrl/sites/site-internal/qos/gateway/class-rules?page=1&pageSize=100"))
        self.assertFalse(client._site_gateway_qos_class_request_valid(
            "/openapi/v1/other/sites/site-internal/qos/gateway/class-rules?page=1&pageSize=100"))
        self.assertFalse(client._site_gateway_qos_class_request_valid(
            "/openapi/v1/ctrl/sites/site-internal/qos/gateway/class-rules?page=11&pageSize=100"))
        self.assertFalse(client._site_gateway_qos_class_request_valid(
            "/openapi/v1/ctrl/sites/site-internal/qos/gateway/class-rules?page=1&pageSize=1000"))


if __name__ == "__main__":
    unittest.main()
