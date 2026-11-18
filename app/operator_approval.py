"""Pure, plan-bound HMAC operator approvals for the connector.

This module can verify that a token was made with a separate 32-byte key and
binds it to one operation, plan ID, caller-supplied plan digest, opaque operator
ID and expiry. It cannot establish who controls the key or prove a human's
identity. The caller must independently authenticate the operator, compute the
plan digest from the exact displayed plan, and consume the existing plan once
before any write; an HMAC token by itself is replayable until it expires.
"""
from __future__ import annotations

import errno
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import time
from typing import Any


class OperatorApprovalError(ValueError):
    """Stable error code; never includes key material or file paths."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


KEY_BYTES = 32
MAX_APPROVAL_TTL_SECONDS = 300
APPROVAL_VERSION = 1
_DOMAIN = b"omada-universal-connector/operator-approval/v1\n"
_OPERATIONS = frozenset({"radio", "dns-cache", "ssid", "gateway-ipv6", "poe",
                         "switch-port-status", "band-steering", "rrm-mode", "site-led", "ap-afc",
                         "site-lldp", "ap-channel-limit", "ap-ofdma", "ap-qos", "switch-port-name",
                         "site-dpi", "gateway-voip", "gateway-tag-qos",
                         "switch-cable-test", "switch-cable-test-cancel",
                         "controller-radius-proxy"})
_PLAN_ID = re.compile(r"[0-9a-f]{48}\Z")
_PLAN_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_OPERATOR_ID = re.compile(r"op_[0-9a-f]{24}\Z")
_SIGNATURE = re.compile(r"[0-9a-f]{64}\Z")
_NONCE = re.compile(r"[0-9a-f]{32}\Z")
_TOKEN_FIELDS = frozenset({"version", "operation", "plan_id", "plan_digest",
                            "operator_id", "expires_at", "nonce", "signature"})


def _key(value: object) -> bytes:
    if not isinstance(value, bytes) or len(value) != KEY_BYTES:
        raise OperatorApprovalError("operator_key_invalid")
    return value


def _validate_context(operation: object, plan_id: object, plan_digest: object) -> None:
    if not isinstance(operation, str) or operation not in _OPERATIONS:
        raise OperatorApprovalError("operator_approval_operation_invalid")
    if not isinstance(plan_id, str) or not _PLAN_ID.fullmatch(plan_id):
        raise OperatorApprovalError("operator_approval_plan_invalid")
    if not isinstance(plan_digest, str) or not _PLAN_DIGEST.fullmatch(plan_digest):
        raise OperatorApprovalError("operator_approval_digest_invalid")


def _validate_operator_id(operator_id: object) -> None:
    if not isinstance(operator_id, str) or not _OPERATOR_ID.fullmatch(operator_id):
        raise OperatorApprovalError("operator_approval_operator_invalid")


def _now_seconds(now: object | None) -> int:
    if now is None:
        return int(time.time())
    if type(now) is not int or now < 0:
        raise OperatorApprovalError("operator_approval_time_invalid")
    return now


def _validate_expiry(expires_at: object, now: int) -> int:
    if type(expires_at) is not int or expires_at < 0:
        raise OperatorApprovalError("operator_approval_expiry_invalid")
    if expires_at <= now:
        raise OperatorApprovalError("operator_approval_expired")
    if expires_at - now > MAX_APPROVAL_TTL_SECONDS:
        raise OperatorApprovalError("operator_approval_expiry_too_far")
    return expires_at


def _message(operation: str, plan_id: str, plan_digest: str,
             operator_id: str, expires_at: int, nonce: str) -> bytes:
    # All fields are restricted to ASCII grammars and joined with fixed newlines.
    return (_DOMAIN + f"{operation}\n{plan_id}\n{plan_digest}\n{operator_id}\n{expires_at}\n{nonce}".encode("ascii"))


def _object_pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for name, value in pairs:
        if name in obj:
            raise OperatorApprovalError("operator_approval_invalid")
        obj[name] = value
    return obj


def _reject_constant(_value: str) -> None:
    raise OperatorApprovalError("operator_approval_invalid")


def parse_approval(encoded: str | bytes) -> dict[str, object]:
    """Parse JSON approval data while rejecting duplicate keys and constants."""
    try:
        if isinstance(encoded, bytes):
            encoded = encoded.decode("utf-8")
        if not isinstance(encoded, str) or len(encoded.encode("utf-8")) > 4096:
            raise OperatorApprovalError("operator_approval_invalid")
        value = json.loads(encoded, object_pairs_hook=_object_pairs_no_duplicates,
                           parse_constant=_reject_constant)
    except OperatorApprovalError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError):
        raise OperatorApprovalError("operator_approval_invalid") from None
    if not isinstance(value, dict):
        raise OperatorApprovalError("operator_approval_invalid")
    return value


def sign_approval(key: bytes, *, operation: str, plan_id: str,
                  plan_digest: str, operator_id: str, expires_at: int,
                  now: int | None = None) -> dict[str, object]:
    """Create a signature token bound to one displayed plan and short expiry.

    The caller computes ``plan_digest`` over the exact plan representation it
    showed to the operator. This function does not infer or validate that digest.
    """
    key = _key(key)
    _validate_context(operation, plan_id, plan_digest)
    _validate_operator_id(operator_id)
    current = _now_seconds(now)
    expiry = _validate_expiry(expires_at, current)
    nonce = secrets.token_hex(16)
    signature = hmac.new(key, _message(operation, plan_id, plan_digest,
                                       operator_id, expiry, nonce), hashlib.sha256).hexdigest()
    return {"version": APPROVAL_VERSION, "operation": operation,
            "plan_id": plan_id, "plan_digest": plan_digest,
            "operator_id": operator_id, "expires_at": expiry, "nonce": nonce,
            "signature": signature}


def verify_approval(key: bytes, approval: dict[str, object] | str | bytes, *,
                    operation: str, plan_id: str, plan_digest: str,
                    now: int | None = None) -> str:
    """Verify a token against the exact expected operation, plan and digest.

    Returns the bound operator ID; that opaque ID is not proof of a person's
    identity. Verification is pure and does not consume the underlying plan.
    """
    key = _key(key)
    _validate_context(operation, plan_id, plan_digest)
    token = parse_approval(approval) if isinstance(approval, (str, bytes)) else approval
    if not isinstance(token, dict) or set(token) != _TOKEN_FIELDS:
        raise OperatorApprovalError("operator_approval_invalid")
    if type(token.get("version")) is not int or token["version"] != APPROVAL_VERSION:
        raise OperatorApprovalError("operator_approval_invalid")
    token_operation = token.get("operation")
    token_plan_id = token.get("plan_id")
    token_digest = token.get("plan_digest")
    operator_id = token.get("operator_id")
    nonce = token.get("nonce")
    _validate_context(token_operation, token_plan_id, token_digest)
    _validate_operator_id(operator_id)
    if not isinstance(nonce, str) or not _NONCE.fullmatch(nonce):
        raise OperatorApprovalError("operator_approval_invalid")
    if (token_operation != operation or token_plan_id != plan_id or
            token_digest != plan_digest):
        raise OperatorApprovalError("operator_approval_mismatch")
    current = _now_seconds(now)
    expiry = _validate_expiry(token.get("expires_at"), current)
    signature = token.get("signature")
    if not isinstance(signature, str) or not _SIGNATURE.fullmatch(signature):
        raise OperatorApprovalError("operator_approval_invalid")
    expected = hmac.new(key, _message(operation, plan_id, plan_digest,
                                      operator_id, expiry, nonce), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise OperatorApprovalError("operator_approval_invalid")
    return operator_id


def load_operator_key(path: str) -> bytes:
    """Read an existing 32-byte key from an owner-only regular file.

    The path and any underlying OS details are deliberately excluded from
    errors. No key is created, decoded, returned elsewhere or logged.
    """
    if not isinstance(path, str) or not path.startswith("/"):
        raise OperatorApprovalError("operator_key_unavailable")
    parts = path.split("/")
    if len(parts) < 3 or any(part in {"", ".", ".."} for part in parts[1:]):
        raise OperatorApprovalError("operator_key_unavailable")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise OperatorApprovalError("operator_key_unavailable")
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    dir_fd = -1
    file_fd = -1
    try:
        dir_fd = os.open("/", dir_flags)
        for component in parts[1:-1]:
            next_fd = os.open(component, dir_flags, dir_fd=dir_fd)
            os.close(dir_fd)
            dir_fd = next_fd
        file_fd = os.open(parts[-1], file_flags, dir_fd=dir_fd)
        info = os.fstat(file_fd)
        mode = stat.S_IMODE(info.st_mode)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or mode not in (0o400, 0o600)
                or info.st_size != KEY_BYTES):
            raise OperatorApprovalError("operator_key_invalid")
        raw = bytearray()
        while len(raw) <= KEY_BYTES:
            part = os.read(file_fd, KEY_BYTES + 1 - len(raw))
            if not part:
                break
            raw.extend(part)
        if len(raw) != KEY_BYTES:
            raise OperatorApprovalError("operator_key_invalid")
        return bytes(raw)
    except OperatorApprovalError:
        raise
    except OSError as exc:
        code = "operator_key_invalid" if exc.errno in {errno.ELOOP, errno.EISDIR} else "operator_key_unavailable"
        raise OperatorApprovalError(code) from None
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        if dir_fd >= 0:
            os.close(dir_fd)
