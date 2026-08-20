from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_RELATIVE = "config/desktop_nondeterminism_schema.json"
SCHEMA_ID = "PP-DESKTOP-NONDET-001"
COMPARE_EXCLUDED_NAMES = frozenset({"hashes.json", "compare.json"})
COMPARE_DIR_NAME = "compare"
IDENTITY_DIR_NAMES = frozenset({"identity", "installers"})
INSTALLER_CONTAINER_SUFFIXES = frozenset({".msi", ".msix"})
NSIS_SIGNATURE = b"NullsoftInst"
EXTRACTED_TREE_ALGORITHM = "compare_extracted_payload_tree/v1"


@dataclass(frozen=True, slots=True)
class NormalizedBinary:
    path: str
    raw_sha256: str
    normalized_sha256: str
    removed_fields: tuple[str, ...]
    algorithm: str


class DesktopReproducibilityError(RuntimeError):
    """Raised when an installer payload cannot be extracted for comparison."""


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


def _allowlist(schema: dict[str, Any]) -> set[str]:
    return {item["id"] for item in schema.get("allowlisted_fields", [])}


def _zero_u32(payload: bytearray, offset: int) -> None:
    payload[offset : offset + 4] = b"\x00\x00\x00\x00"


def normalize_pe_image(payload: bytes, schema: dict[str, Any]) -> tuple[bytes, tuple[str, ...]]:
    allow = _allowlist(schema)
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


def normalize_archive_member(
    path: Path, payload: bytes, schema: dict[str, Any]
) -> tuple[bytes, tuple[str, ...]]:
    suffix = path.suffix.lower()
    if suffix in INSTALLER_CONTAINER_SUFFIXES:
        return payload, ()
    normalized, removed = normalize_pe_image(payload, schema)
    extra = list(removed)
    if (
        NSIS_SIGNATURE in payload
        and "nsis_build_timestamp" in _allowlist(schema)
        and "pe_timedatestamp" in removed
    ):
        extra.append("nsis_build_timestamp")
    if suffix in {".exe", ".dll"} or payload[:2] == b"MZ":
        return normalized, tuple(extra)
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


def _is_identity_path(path: Path, root: Path) -> bool:
    try:
        parts = set(path.relative_to(root).parts)
    except ValueError:
        parts = set(path.parts)
    return bool(parts & IDENTITY_DIR_NAMES)


def _compare_root(root: Path) -> Path:
    nested = root / COMPARE_DIR_NAME
    return nested if nested.is_dir() else root


def _iter_compare_files(root: Path) -> dict[str, Path]:
    base = _compare_root(root)
    files: dict[str, Path] = {}
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if path.name in COMPARE_EXCLUDED_NAMES:
            continue
        if _is_identity_path(path, root) or _is_identity_path(path, base):
            continue
        if path.suffix.lower() in INSTALLER_CONTAINER_SUFFIXES:
            continue
        files[path.relative_to(base).as_posix()] = path
    return files


def _identity_root(root: Path) -> Path | None:
    for name in ("identity", "installers"):
        candidate = root / name
        if candidate.is_dir():
            return candidate
    return None


def canonical_extracted_tree(root: Path, schema: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    members: list[tuple[str, str]] = []
    removed: list[str] = []
    residual_installer = False
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in COMPARE_EXCLUDED_NAMES:
            continue
        if path.suffix.lower() in INSTALLER_CONTAINER_SUFFIXES:
            residual_installer = True
            continue
        relative = path.relative_to(root).as_posix()
        normalized, fields = normalize_archive_member(path, path.read_bytes(), schema)
        members.append((relative, _sha256_bytes(normalized)))
        removed.extend(fields)
    if residual_installer and "msi_package_code" in _allowlist(schema):
        removed.append("msi_package_code")
    digest = _sha256_bytes(
        json.dumps(members, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    return digest, tuple(dict.fromkeys(removed))


def extract_msi_administrative_image(msi_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            [
                "msiexec",
                "/a",
                str(msi_path.resolve()),
                f"TARGETDIR={destination.resolve()}",
                "/qn",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (FileNotFoundError, OSError) as exc:
        raise DesktopReproducibilityError(
            f"msiexec administrative extract unavailable for {msi_path.name}"
        ) from exc
    if completed.returncode != 0 or not any(destination.rglob("*")):
        raise DesktopReproducibilityError(
            f"msiexec administrative extract failed for {msi_path.name}"
        )


def compare_extracted_payload_trees(
    left_root: Path,
    right_root: Path,
    schema: dict[str, Any],
    *,
    name: str,
    removed_field: str,
) -> dict[str, Any]:
    left_digest, left_removed = canonical_extracted_tree(left_root, schema)
    right_digest, right_removed = canonical_extracted_tree(right_root, schema)
    equal = left_digest == right_digest
    return {
        "name": name,
        "left_raw_sha256": None,
        "right_raw_sha256": None,
        "left_normalized_sha256": left_digest,
        "right_normalized_sha256": right_digest,
        "left_removed_fields": list(left_removed),
        "right_removed_fields": list(right_removed),
        "algorithm": f"{EXTRACTED_TREE_ALGORITHM}:{removed_field}",
        "equal": equal,
    }


def _compare_named_files(
    left_files: dict[str, Path],
    right_files: dict[str, Path],
    schema: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
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
    return comparisons, mismatches


def compare_normalized_trees(
    left_root: Path,
    right_root: Path,
    schema: dict[str, Any],
) -> dict[str, Any]:
    comparisons, mismatches = _compare_named_files(
        _iter_compare_files(left_root),
        _iter_compare_files(right_root),
        schema,
    )
    return {
        "schema_id": schema.get("schema_id"),
        "schema_version": schema.get("schema_version"),
        "comparisons": comparisons,
        "mismatches": mismatches,
        "passed": not mismatches,
    }


def compare_desktop_artifact_sets(
    left_root: Path,
    right_root: Path,
    schema: dict[str, Any],
) -> dict[str, Any]:
    result = compare_normalized_trees(left_root, right_root, schema)
    comparisons = list(result["comparisons"])
    mismatches = list(result["mismatches"])
    left_identity = _identity_root(left_root)
    right_identity = _identity_root(right_root)
    if left_identity is None and right_identity is None:
        return result
    if left_identity is None or right_identity is None:
        mismatches.append("installer identity directory missing in one lane")
        result["comparisons"] = comparisons
        result["mismatches"] = mismatches
        result["passed"] = False
        return result
    left_msis = {path.name: path for path in left_identity.glob("*.msi")}
    right_msis = {path.name: path for path in right_identity.glob("*.msi")}
    for name in sorted(set(left_msis) | set(right_msis)):
        if name not in left_msis or name not in right_msis:
            mismatches.append(f"missing MSI identity artifact in one lane: {name}")
            continue
        try:
            with (
                tempfile.TemporaryDirectory(prefix="pp-msi-left-") as left_tmp,
                tempfile.TemporaryDirectory(prefix="pp-msi-right-") as right_tmp,
            ):
                extract_msi_administrative_image(left_msis[name], Path(left_tmp))
                extract_msi_administrative_image(right_msis[name], Path(right_tmp))
                extracted = compare_extracted_payload_trees(
                    Path(left_tmp),
                    Path(right_tmp),
                    schema,
                    name=name,
                    removed_field="msi_package_code",
                )
        except DesktopReproducibilityError as exc:
            mismatches.append(str(exc))
            continue
        comparisons.append(extracted)
        if not extracted["equal"]:
            mismatches.append(
                f"extracted MSI payload tree mismatch for {name}: "
                f"{extracted['left_normalized_sha256']} != {extracted['right_normalized_sha256']}"
            )
    left_nsis = {
        path.name: path
        for path in left_identity.glob("*.exe")
        if NSIS_SIGNATURE in path.read_bytes()
    }
    right_nsis = {
        path.name: path
        for path in right_identity.glob("*.exe")
        if NSIS_SIGNATURE in path.read_bytes()
    }
    nsis_comparisons, nsis_mismatches = _compare_named_files(left_nsis, right_nsis, schema)
    comparisons.extend(nsis_comparisons)
    mismatches.extend(nsis_mismatches)
    result["comparisons"] = comparisons
    result["mismatches"] = mismatches
    result["passed"] = not mismatches
    return result
