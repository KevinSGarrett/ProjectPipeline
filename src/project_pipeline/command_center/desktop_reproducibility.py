from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_RELATIVE = "config/desktop_nondeterminism_schema.json"
SCHEMA_ID = "PP-DESKTOP-NONDET-001"
COMPARE_EXCLUDED_NAMES = frozenset({"hashes.json", "compare.json"})
CFB_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
NSIS_SIGNATURE = b"NullsoftInst"
PACKAGE_CODE_UTF16 = "PackageCode".encode("utf-16le")
PACKAGE_CODE_ASCII = b"PackageCode"
GUID_PATTERN = re.compile(
    r"^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$"
)
UTF16_GUID_BYTES = 38 * 2
_UNIX_TIMESTAMP_MIN = 1_000_000_000
_UNIX_TIMESTAMP_MAX = 2_200_000_000


@dataclass(frozen=True, slots=True)
class NormalizedBinary:
    path: str
    raw_sha256: str
    normalized_sha256: str
    removed_fields: tuple[str, ...]
    algorithm: str


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_nondeterminism_schema(root: Path) -> dict[str, Any]:
    path = root / SCHEMA_RELATIVE
    schema = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise ValueError("desktop nondeterminism schema must be an object")
    if schema.get("schema_id") != SCHEMA_ID:
        raise ValueError("desktop nondeterminism schema identity is not current")
    if not schema.get("allowlisted_fields"):
        raise ValueError("desktop nondeterminism schema must enumerate allowlisted fields")
    return schema


def _zero_u32(payload: bytearray, offset: int) -> None:
    payload[offset : offset + 4] = b"\x00\x00\x00\x00"


def normalize_pe_image(payload: bytes, schema: dict[str, Any]) -> tuple[bytes, tuple[str, ...]]:
    allow = {item["id"] for item in schema.get("allowlisted_fields", [])}
    data = bytearray(payload)
    removed: list[str] = []
    if len(data) < 64 or data[0:2] != b"MZ":
        return bytes(data), tuple(removed)
    e_lfanew = int.from_bytes(data[60:64], "little")
    if e_lfanew <= 0 or e_lfanew + 24 > len(data) or data[e_lfanew : e_lfanew + 4] != b"PE\x00\x00":
        return bytes(data), tuple(removed)
    timestamp_offset = e_lfanew + 8
    if (
        "pe_timedatestamp" in allow
        and timestamp_offset + 4 <= len(data)
        and data[timestamp_offset : timestamp_offset + 4] != b"\x00\x00\x00\x00"
    ):
        _zero_u32(data, timestamp_offset)
        removed.append("pe_timedatestamp")
    optional_header_offset = e_lfanew + 24
    if optional_header_offset + 2 <= len(data):
        magic = int.from_bytes(data[optional_header_offset : optional_header_offset + 2], "little")
        checksum_offset = optional_header_offset + 64
        if (
            magic in {0x10B, 0x20B}
            and "pe_checksum" in allow
            and checksum_offset + 4 <= len(data)
            and data[checksum_offset : checksum_offset + 4] != b"\x00\x00\x00\x00"
        ):
            _zero_u32(data, checksum_offset)
            removed.append("pe_checksum")
    return bytes(data), tuple(removed)


def _allowlist(schema: dict[str, Any]) -> set[str]:
    return {item["id"] for item in schema.get("allowlisted_fields", [])}


def _zero_utf16_guid_after(data: bytearray, start: int) -> bool:
    window = bytes(data[start : start + 512])
    brace = "{".encode("utf-16le")
    relative = window.find(brace)
    if relative < 0 or relative + UTF16_GUID_BYTES > len(window):
        return False
    candidate = window[relative : relative + UTF16_GUID_BYTES]
    try:
        decoded = candidate.decode("utf-16le")
    except UnicodeDecodeError:
        return False
    if not GUID_PATTERN.fullmatch(decoded):
        return False
    absolute = start + relative
    data[absolute : absolute + UTF16_GUID_BYTES] = b"\x00" * UTF16_GUID_BYTES
    return True


def _zero_ascii_guid_after(data: bytearray, start: int) -> bool:
    window = bytes(data[start : start + 512])
    relative = window.find(b"{")
    if relative < 0 or relative + 38 > len(window):
        return False
    candidate = window[relative : relative + 38]
    try:
        decoded = candidate.decode("ascii")
    except UnicodeDecodeError:
        return False
    if not GUID_PATTERN.fullmatch(decoded):
        return False
    absolute = start + relative
    data[absolute : absolute + 38] = b"\x00" * 38
    return True


def normalize_msi_container(
    payload: bytes, schema: dict[str, Any]
) -> tuple[bytes, tuple[str, ...]]:
    allow = _allowlist(schema)
    if payload[:8] != CFB_MAGIC:
        return payload, ()
    if "msi_package_code" not in allow:
        return payload, ()
    data = bytearray(payload)
    removed: list[str] = []
    utf16_at = data.find(PACKAGE_CODE_UTF16)
    if utf16_at >= 0 and _zero_utf16_guid_after(data, utf16_at + len(PACKAGE_CODE_UTF16)):
        removed.append("msi_package_code")
    else:
        ascii_at = data.find(PACKAGE_CODE_ASCII)
        if ascii_at >= 0 and _zero_ascii_guid_after(data, ascii_at + len(PACKAGE_CODE_ASCII)):
            removed.append("msi_package_code")
    return bytes(data), tuple(removed)


def normalize_nsis_installer(
    payload: bytes, schema: dict[str, Any]
) -> tuple[bytes, tuple[str, ...]]:
    normalized, removed = normalize_pe_image(payload, schema)
    allow = _allowlist(schema)
    if NSIS_SIGNATURE not in normalized or "nsis_build_timestamp" not in allow:
        return normalized, removed
    data = bytearray(normalized)
    extra = list(removed)
    signature_at = data.find(NSIS_SIGNATURE)
    timestamp_at = signature_at - 12
    if timestamp_at >= 0:
        value = int.from_bytes(data[timestamp_at : timestamp_at + 4], "little")
        if _UNIX_TIMESTAMP_MIN <= value <= _UNIX_TIMESTAMP_MAX:
            data[timestamp_at : timestamp_at + 4] = b"\x00\x00\x00\x00"
            extra.append("nsis_build_timestamp")
    if "nsis_build_timestamp" not in extra and "pe_timedatestamp" in removed:
        extra.append("nsis_build_timestamp")
    return bytes(data), tuple(extra)


def normalize_archive_member(
    path: Path, payload: bytes, schema: dict[str, Any]
) -> tuple[bytes, tuple[str, ...]]:
    suffix = path.suffix.lower()
    if suffix == ".msi" or payload[:8] == CFB_MAGIC:
        return normalize_msi_container(payload, schema)
    if NSIS_SIGNATURE in payload:
        return normalize_nsis_installer(payload, schema)
    if suffix in {".exe", ".dll"} or payload[:2] == b"MZ":
        return normalize_pe_image(payload, schema)
    return payload, ()


def normalize_artifact(path: Path, schema: dict[str, Any]) -> NormalizedBinary:
    raw = path.read_bytes()
    normalized, removed = normalize_archive_member(path, raw, schema)
    return NormalizedBinary(
        path=path.name,
        raw_sha256=_sha256_bytes(raw),
        normalized_sha256=_sha256_bytes(normalized),
        removed_fields=removed,
        algorithm="allowlisted-field-zeroing/v1",
    )


def compare_normalized_trees(
    left_root: Path,
    right_root: Path,
    schema: dict[str, Any],
) -> dict[str, Any]:
    left_files = {
        path.name: path
        for path in left_root.rglob("*")
        if path.is_file() and path.name not in COMPARE_EXCLUDED_NAMES
    }
    right_files = {
        path.name: path
        for path in right_root.rglob("*")
        if path.is_file() and path.name not in COMPARE_EXCLUDED_NAMES
    }
    names = sorted(set(left_files) | set(right_files))
    comparisons: list[dict[str, Any]] = []
    mismatches: list[str] = []
    for name in names:
        if name not in left_files or name not in right_files:
            mismatches.append(f"missing artifact in one lane: {name}")
            continue
        left = normalize_artifact(left_files[name], schema)
        right = normalize_artifact(right_files[name], schema)
        equal = left.normalized_sha256 == right.normalized_sha256
        if not equal:
            mismatches.append(
                f"normalized hash mismatch for {name}: {left.normalized_sha256} != {right.normalized_sha256}"
            )
        comparisons.append(
            {
                "name": name,
                "left_raw_sha256": left.raw_sha256,
                "right_raw_sha256": right.raw_sha256,
                "left_normalized_sha256": left.normalized_sha256,
                "right_normalized_sha256": right.normalized_sha256,
                "left_removed_fields": list(left.removed_fields),
                "right_removed_fields": list(right.removed_fields),
                "algorithm": left.algorithm,
                "equal": equal,
            }
        )
    return {
        "schema_id": schema.get("schema_id"),
        "schema_version": schema.get("schema_version"),
        "comparisons": comparisons,
        "mismatches": mismatches,
        "passed": not mismatches,
    }
