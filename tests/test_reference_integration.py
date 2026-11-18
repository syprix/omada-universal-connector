from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_ID = "site_alpha"
DEVICE_ID = "device_alpha"


def make_config(controller: str, key_file: str | None = None) -> OpenApiConfig:
    return OpenApiConfig(
        "https://controller.example", controller, "client-id", "client-secret",
        cert_sha256="a" * 64, reference_key_file=key_file,
    )


class StableReferenceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.key_a = os.path.join(self.tempdir.name, "key-a")
        self.key_b = os.path.join(self.tempdir.name, "key-b")
        for path, byte in ((self.key_a, b"A"), (self.key_b, b"B")):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(byte * 32)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def inventory_client(self, controller: str, key_file: str | None,
                         site_id: str = SITE_ID):
        client = OmadaOpenApiClient(make_config(controller, key_file))

        def pages(path: str, _token: str):
            if path.endswith("/sites"):
                return [{"siteId": site_id}]
            if path.endswith("/devices"):
                return [{"deviceId": DEVICE_ID, "mac": "AA:BB:CC:DD:EE:01",
                         "deviceType": "switch", "name": "private label"}]
            raise AssertionError("unexpected fixture path")

        with patch.object(client, "_access_token", return_value="fixture-token"), \
                patch.object(client, "_read_pages", side_effect=pages):
            site_ref = client.list_sites()["items"][0]["site_ref"]
            device_ref = client.list_devices(site_ref)["items"][0]["device_ref"]
        return client, site_ref, device_ref

    def test_site_and_device_refs_survive_client_restart_and_inventory_refresh(self) -> None:
        first = self.inventory_client("controller_a", self.key_a)
        restarted = self.inventory_client("controller_a", self.key_a)
        refreshed = self.inventory_client("controller_a", self.key_a)
        self.assertEqual(first[1:], restarted[1:])
        self.assertEqual(first[1:], refreshed[1:])

    def test_controller_site_and_key_are_bound_into_refs(self) -> None:
        baseline = self.inventory_client("controller_a", self.key_a)
        other_controller = self.inventory_client("controller_b", self.key_a)
        other_key = self.inventory_client("controller_a", self.key_b)
        other_site = self.inventory_client("controller_a", self.key_a, "site_beta")
        self.assertNotEqual(baseline[1], other_controller[1])
        self.assertNotEqual(baseline[2], other_controller[2])
        self.assertNotEqual(baseline[1], other_key[1])
        self.assertNotEqual(baseline[2], other_key[2])
        self.assertNotEqual(baseline[1], other_site[1])
        self.assertNotEqual(baseline[2], other_site[2])

        client = OmadaOpenApiClient(make_config("controller_a", self.key_a))
        site_a = client._opaque_ref("site", "site_alpha")
        site_b = client._opaque_ref("site", "site_beta")
        device_a = client._opaque_ref("device", "site_alpha:device_alpha")
        device_b = client._opaque_ref("device", "site_beta:device_alpha")
        self.assertNotEqual(site_a, site_b)
        self.assertNotEqual(device_a, device_b)

    def test_invalid_key_files_fail_closed_without_ephemeral_fallback(self) -> None:
        short = os.path.join(self.tempdir.name, "short")
        with open(short, "wb") as handle:
            handle.write(b"short")
        os.chmod(short, 0o600)
        public = os.path.join(self.tempdir.name, "public")
        with open(public, "wb") as handle:
            handle.write(b"C" * 32)
        os.chmod(public, 0o644)
        for path, expected in ((short, "reference_key_file_invalid"),
                               (public, "reference_key_permissions_invalid"),
                               (os.path.join(self.tempdir.name, "missing"),
                                "reference_key_file_unavailable")):
            with self.subTest(path=os.path.basename(path)), \
                    self.assertRaises(OpenApiError) as raised:
                OmadaOpenApiClient(make_config("controller_a", path))
            self.assertEqual(raised.exception.code, expected)

    def test_legacy_unconfigured_mode_remains_ephemeral(self) -> None:
        first = self.inventory_client("controller_a", None)
        second = self.inventory_client("controller_a", None)
        self.assertNotEqual(first[1], second[1])
        self.assertNotEqual(first[2], second[2])

    def test_client_snapshot_refs_remain_short_lived(self) -> None:
        client = OmadaOpenApiClient(make_config("controller_a", self.key_a))
        with patch.object(client, "_access_token", return_value="fixture-token"), \
                patch.object(client, "_read_pages", side_effect=[
                    [{"siteId": SITE_ID}],
                    [{"mac": "AA:BB:CC:DD:EE:02", "wireless": True}],
                    [{"mac": "AA:BB:CC:DD:EE:02", "wireless": True}],
                ]):
            site_ref = client.list_sites()["items"][0]["site_ref"]
            first = client.list_clients(site_ref)["items"][0]["client_ref"]
            second = client.list_clients(site_ref)["items"][0]["client_ref"]
        self.assertNotEqual(first, second)

    def test_environment_blank_is_legacy_and_configured_path_is_preserved(self) -> None:
        base = {
            "OMADA_BASE_URL": "https://controller.example",
            "OMADA_CONTROLLER_ID": "controller_a",
            "OMADA_CLIENT_ID_FILE": "client-id",
            "OMADA_CLIENT_SECRET_FILE": "client-secret",
            "OMADA_CERT_SHA256": "a" * 64,
        }
        with patch.dict(os.environ, {**base, "OMADA_REFERENCE_KEY_FILE": ""}, clear=True):
            self.assertIsNone(OpenApiConfig.from_env().reference_key_file)
        with patch.dict(os.environ, {**base, "OMADA_REFERENCE_KEY_FILE": self.key_a}, clear=True):
            self.assertEqual(OpenApiConfig.from_env().reference_key_file, self.key_a)


if __name__ == "__main__":
    unittest.main()
