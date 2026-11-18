from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class InputHardeningTests(unittest.TestCase):
    def test_fifo_secret_paths_open_nonblocking_and_never_read_fifo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token_fifo = os.path.join(directory, "token-fifo")
            credential_fifo = os.path.join(directory, "credential-fifo")
            os.mkfifo(token_fifo)
            os.mkfifo(credential_fifo)
            token_fd = os.open(token_fifo, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
            with patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": token_fifo}), \
                    patch("app.main.os.open", return_value=token_fd) as token_open, \
                    patch("app.main.os.read", side_effect=AssertionError("FIFO must not be read")) as token_read:
                self.assertIsNone(main._caller_token())
            self.assertTrue(token_open.call_args.args[1] & getattr(os, "O_NONBLOCK", 0))
            token_read.assert_not_called()

            credential_fd = os.open(credential_fifo, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
            os.close(credential_fd)
            client = OmadaOpenApiClient(OpenApiConfig(
                "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
            original_open = os.open
            with patch("app.openapi.os.open", wraps=original_open) as credential_open, \
                    patch("app.openapi.os.read", side_effect=AssertionError("FIFO must not be read")) as credential_read, \
                    self.assertRaisesRegex(OpenApiError, "credential_file_invalid"):
                client._read_secret(credential_fifo)
            self.assertTrue(credential_open.call_args_list[-1].args[1] & getattr(os, "O_NONBLOCK", 0))
            credential_read.assert_not_called()

    def test_regular_token_and_credential_fixtures_are_still_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token_path = os.path.join(directory, "token")
            credential_path = os.path.join(directory, "credential")
            with open(token_path, "w", encoding="utf-8") as stream:
                stream.write("caller-token-0123456789abcdef0123456789\n")
            with open(credential_path, "w", encoding="utf-8") as stream:
                stream.write("client-secret-value\n")
            os.chmod(credential_path, 0o600)
            with patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": token_path}):
                self.assertEqual(main._caller_token(), b"caller-token-0123456789abcdef0123456789")
            self.assertEqual(OmadaOpenApiClient._read_secret(credential_path), "client-secret-value")

    def test_controller_credentials_reject_open_modes_links_symlinks_and_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "credential")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("client-secret-value")
            client = OmadaOpenApiClient(OpenApiConfig(
                "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))

            os.chmod(path, 0o644)
            with self.assertRaisesRegex(OpenApiError, "credential_file_invalid"):
                client._read_secret(path)

            os.chmod(path, 0o600)
            hardlink = os.path.join(directory, "credential-hardlink")
            os.link(path, hardlink)
            with self.assertRaisesRegex(OpenApiError, "credential_file_invalid"):
                client._read_secret(path)
            os.unlink(hardlink)

            symlink = os.path.join(directory, "credential-symlink")
            os.symlink(path, symlink)
            with self.assertRaisesRegex(OpenApiError, "credential_file_unavailable"):
                client._read_secret(symlink)

            real_directory = os.path.join(directory, "real-directory")
            os.mkdir(real_directory)
            nested = os.path.join(real_directory, "credential")
            with open(nested, "w", encoding="utf-8") as stream:
                stream.write("client-secret-value")
            os.chmod(nested, 0o600)
            directory_alias = os.path.join(directory, "directory-alias")
            os.symlink(real_directory, directory_alias)
            with self.assertRaisesRegex(OpenApiError, "credential_file_unavailable"):
                client._read_secret(os.path.join(directory_alias, "credential"))

            with self.assertRaisesRegex(OpenApiError, "credential_file_invalid"):
                client._read_secret("relative/credential")

    def test_container_image_copies_the_complete_application_module_directory(self) -> None:
        dockerfile = os.path.join(os.path.dirname(__file__), "..", "Dockerfile")
        with open(dockerfile, encoding="utf-8") as stream:
            lines = stream.read().splitlines()
        self.assertIn("COPY app/ /app/app/", lines)

    def test_controller_json_rejects_top_level_and_nested_duplicate_keys(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))

        class Response:
            status = 200
            def __init__(self, raw: bytes):
                self.raw = raw
            def read(self, _size: int) -> bytes:
                return self.raw
            def getheader(self, key: str, default: str | None = None) -> str | None:
                return "application/json" if key.lower() == "content-type" else default

        class Connection:
            def __init__(self, raw: bytes):
                self.response = Response(raw)
                self.closed = False
            def request(self, *_args, **_kwargs) -> None:
                return None
            def getresponse(self) -> Response:
                return self.response
            def close(self) -> None:
                self.closed = True

        path = "/openapi/v1/ctrl/dashboard/overview-without-client"
        for raw in (b'{"result":{"enable":true,"enable":false}}',
                    b'{"result":{"nested":{"value":1,"value":2}}}'):
            with self.subTest(raw=raw), patch.object(client, "_connection", return_value=Connection(raw)), \
                    self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                client._request_json("GET", path)

        with patch.object(client, "_connection", return_value=Connection(
                b'{"errorCode":0,"result":{"enable":true,"nested":{"value":2}}}')):
            self.assertEqual(client._request_json("GET", path),
                             {"errorCode": 0, "result": {"enable": True, "nested": {"value": 2}}})

    def test_nonstandard_and_nonfinite_controller_numbers_still_fail(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))

        class Response:
            status = 200
            def __init__(self, raw: bytes): self.raw = raw
            def read(self, _size: int) -> bytes: return self.raw
            def getheader(self, key: str, default: str | None = None) -> str | None:
                return "application/json" if key.lower() == "content-type" else default

        class Connection:
            def __init__(self, raw: bytes): self.response = Response(raw)
            def request(self, *_args, **_kwargs): pass
            def getresponse(self): return self.response
            def close(self): pass

        path = "/openapi/v1/ctrl/dashboard/overview-without-client"
        for raw in (b'{"value":NaN}', b'{"value":Infinity}', b'{"value":1e999}',
                    b'{"value":' + b"9" * 5000 + b'}'):
            with self.subTest(raw_length=len(raw)), patch.object(client, "_connection", return_value=Connection(raw)), \
                    self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                client._request_json("GET", path)


if __name__ == "__main__":
    unittest.main()
