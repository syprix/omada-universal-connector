"""HTTPS-pinned, read-only controller-info client for Phase 2.

The Phase 2 route is empirical controller evidence only. It is not presented
as an official TP-Link OpenAPI route and it performs no authentication or
mutation.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import ssl
from dataclasses import dataclass
from urllib.parse import urlsplit

try:
    from .finite_values import is_finite_number
except ImportError:  # direct execution in the image
    from finite_values import is_finite_number


class OmadaError(RuntimeError):
    """Redacted, stable connector error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _normalize_certificate_pin(value: object) -> str:
    if not isinstance(value, str):
        raise OmadaError("controller_certificate_pin_invalid")
    pin = value.strip()
    if pin and (
        len(pin) != 64
        or any(char not in "0123456789abcdefABCDEF" for char in pin)
    ):
        raise OmadaError("controller_certificate_pin_invalid")
    return pin.lower()


@dataclass(frozen=True)
class OmadaConfig:
    base_url: str
    timeout_seconds: float = 5.0
    cert_sha256: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "cert_sha256", _normalize_certificate_pin(self.cert_sha256))
        if not is_finite_number(self.timeout_seconds) or not 0.1 <= self.timeout_seconds <= 30:
            raise OmadaError("controller_timeout_invalid")
        try:
            parsed = urlsplit(self.base_url)
            port = parsed.port
        except (TypeError, ValueError):
            raise OmadaError("controller_url_rejected") from None
        if parsed.scheme != "https" or not parsed.hostname:
            raise OmadaError("controller_https_required")
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or any(ch.isspace() for ch in parsed.hostname)
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise OmadaError("controller_url_rejected")

    @classmethod
    def from_env(cls) -> "OmadaConfig":
        cert_sha256 = os.getenv("OMADA_CERT_SHA256", "")
        try:
            timeout_seconds = float(os.getenv("OMADA_TIMEOUT_SECONDS", "5"))
        except (TypeError, ValueError):
            raise OmadaError("controller_timeout_invalid") from None
        return cls(
            base_url=os.getenv("OMADA_BASE_URL", "https://192.0.2.1"),
            timeout_seconds=timeout_seconds,
            cert_sha256=cert_sha256,
        )


class OmadaClient:
    """Read exactly one empirical controller-info endpoint over pinned HTTPS."""

    FIXED_PATH = "/api/info"
    MAX_RESPONSE_BYTES = 256_000
    MAX_VERSION_CHARS = 64
    _CONTROLLER_ID = re.compile(r"[A-Za-z0-9-]{8,128}")

    def __init__(self, config: OmadaConfig) -> None:
        self.config = config

    def read_controller_info(self) -> dict[str, object]:
        payload = self._request_json(self.FIXED_PATH)
        result = payload.get("result")
        controller_id = result.get("omadacId") if isinstance(result, dict) else None
        if not isinstance(controller_id, str) or not self._CONTROLLER_ID.fullmatch(controller_id):
            raise OmadaError("controller_info_incomplete")

        data: dict[str, object] = {
            "controller_id_present": True,
            "controller_id_sha256": hashlib.sha256(controller_id.encode("utf-8")).hexdigest(),
        }
        if isinstance(result, dict):
            version = result.get("controllerVer") if "controllerVer" in result else result.get("version")
        else:
            version = None
        if version is not None:
            if (
                not isinstance(version, str)
                or not version
                or len(version) > self.MAX_VERSION_CHARS
                or any(ord(char) < 32 or ord(char) == 127 for char in version)
            ):
                raise OmadaError("controller_response_invalid")
            data["version"] = version
        return {
            "status": "verified",
            "resource": "controller_info",
            "path": self.FIXED_PATH,
            "data": data,
        }

    def _connection(self) -> http.client.HTTPSConnection:
        # OmadaConfig validates scheme, authority, path, and port on creation.
        parsed = urlsplit(self.config.base_url)
        if not self.config.cert_sha256:
            raise OmadaError("controller_certificate_pin_required")
        port = parsed.port or 443
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        connection = http.client.HTTPSConnection(
            parsed.hostname,
            port,
            context=context,
            timeout=self.config.timeout_seconds,
        )
        try:
            connection.connect()
            certificate = connection.sock.getpeercert(binary_form=True) if connection.sock else b""
        except ssl.SSLCertVerificationError as exc:
            connection.close()
            raise OmadaError("controller_certificate_untrusted") from exc
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            connection.close()
            raise OmadaError("controller_unreachable") from exc
        actual = hashlib.sha256(certificate).hexdigest()
        if actual != self.config.cert_sha256:
            connection.close()
            raise OmadaError("controller_certificate_changed")
        return connection

    def _request_json(self, path: str) -> dict[str, object]:
        if path != self.FIXED_PATH:
            raise OmadaError("controller_path_rejected")
        connection = self._connection()
        try:
            connection.request("GET", path, headers={"Accept": "application/json"})
            response = connection.getresponse()
            content_length = response.getheader("Content-Length")
            if content_length is not None:
                try:
                    if int(content_length) < 0 or int(content_length) > self.MAX_RESPONSE_BYTES:
                        raise OmadaError("controller_response_too_large")
                except ValueError:
                    raise OmadaError("controller_response_invalid") from None
            raw = response.read(self.MAX_RESPONSE_BYTES + 1)
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            raise OmadaError("controller_unreachable") from exc
        finally:
            connection.close()
        if response.status != 200:
            raise OmadaError("controller_http_error")
        if len(raw) > self.MAX_RESPONSE_BYTES:
            raise OmadaError("controller_response_too_large")
        content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise OmadaError("controller_response_invalid")
        try:
            payload = json.loads(raw or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
            raise OmadaError("controller_response_invalid") from exc
        if not isinstance(payload, dict):
            raise OmadaError("controller_response_invalid")
        if payload.get("errorCode") not in (None, 0):
            raise OmadaError("controller_api_rejected")
        return payload
