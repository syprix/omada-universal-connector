#!/usr/bin/env python3
"""Capture selected redacted settings locally and compare two saved snapshots."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.config_snapshots import (  # noqa: E402
    ConfigSnapshotError, compare_snapshots, project_capture,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError  # noqa: E402


_MAX_FILE_BYTES = 262_144


def _duplicate_rejector(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def _read_snapshot(path: str) -> object:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ConfigSnapshotError("snapshot_file_invalid")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = -1
    try:
        fd = os.open(path, flags)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077 or
                info.st_size > _MAX_FILE_BYTES):
            raise ConfigSnapshotError("snapshot_file_invalid")
        content = os.read(fd, _MAX_FILE_BYTES + 1)
        if len(content) > _MAX_FILE_BYTES:
            raise ConfigSnapshotError("snapshot_file_invalid")
        return json.loads(content.decode("utf-8"), object_pairs_hook=_duplicate_rejector,
                          parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
    except ConfigSnapshotError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
        raise ConfigSnapshotError("snapshot_file_invalid") from None
    finally:
        if fd >= 0:
            os.close(fd)


def _write_snapshot(path: str, value: dict[str, object]) -> None:
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
    if len(encoded) > _MAX_FILE_BYTES:
        raise ConfigSnapshotError("snapshot_too_large")
    if not hasattr(os, "O_NOFOLLOW"):
        raise ConfigSnapshotError("snapshot_write_failed")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = -1
    created = False
    try:
        fd = os.open(path, flags, 0o600)
        created = True
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as stream:
            fd = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        if fd >= 0:
            os.close(fd)
        if created:
            try:
                os.unlink(path)
            except OSError:
                pass
        raise ConfigSnapshotError("snapshot_write_failed") from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture", help="save selected current settings")
    capture.add_argument("--site-ref", required=True)
    capture.add_argument("--site-label", required=True,
                         help="local comparison label, lowercase letters/numbers/dash/underscore")
    capture.add_argument("--ap-ref")
    capture.add_argument("--ap-label")
    capture.add_argument("--ssid-ref")
    capture.add_argument("--ssid-label")
    capture.add_argument("--network-ref")
    capture.add_argument("--network-label")
    capture.add_argument("--output", required=True)
    compare = subparsers.add_parser("compare", help="compare two private snapshot files")
    compare.add_argument("before")
    compare.add_argument("after")
    return parser


def run(argv: list[str] | None = None) -> dict[str, object]:
    args = _parser().parse_args(argv)
    if args.command == "compare":
        return compare_snapshots(_read_snapshot(args.before), _read_snapshot(args.after))
    config = OpenApiConfig.from_env()
    client = OmadaOpenApiClient(config)
    result = project_capture(
        site_label=args.site_label, site_ref=args.site_ref, client=client,
        ap_ref=args.ap_ref, ap_label=args.ap_label, ssid_ref=args.ssid_ref,
        ssid_label=args.ssid_label, network_ref=args.network_ref,
        network_label=args.network_label)
    _write_snapshot(args.output, result)
    return {"status": "ok", "resource": "omada_config_snapshot",
            "schema_version": result["schema_version"],
            "section_count": len(result["sections"]), "saved": True,
            "file_permissions": "owner_only"}


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(argv)
    except ConfigSnapshotError as exc:
        print(json.dumps({"status": "error", "error": exc.code}, separators=(",", ":")))
        return 1
    except OpenApiError as exc:
        print(json.dumps({"status": "error", "error": exc.code}, separators=(",", ":")))
        return 1
    except SystemExit as exc:
        return int(exc.code) if type(exc.code) is int else 2
    except Exception:
        print('{"status":"error","error":"snapshot_failed"}')
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
