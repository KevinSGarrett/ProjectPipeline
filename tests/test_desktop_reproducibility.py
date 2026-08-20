from __future__ import annotations

from pathlib import Path

from project_pipeline.command_center.desktop_reproducibility import (
    CFB_MAGIC,
    NSIS_SIGNATURE,
    compare_normalized_trees,
    load_nondeterminism_schema,
    normalize_msi_container,
    normalize_nsis_installer,
    normalize_pe_image,
)

ROOT = Path(__file__).resolve().parents[1]


def _minimal_pe(*, timestamp: int, checksum: int = 1) -> bytes:
    payload = bytearray(256)
    payload[0:2] = b"MZ"
    payload[60:64] = (128).to_bytes(4, "little")
    payload[128:132] = b"PE\x00\x00"
    payload[136:140] = timestamp.to_bytes(4, "little")
    payload[152:154] = (0x10B).to_bytes(2, "little")
    payload[216:220] = checksum.to_bytes(4, "little")
    payload[220:] = b"application-payload"
    return bytes(payload)


def test_nondeterminism_schema_is_versioned_and_allowlisted() -> None:
    schema = load_nondeterminism_schema(ROOT)
    assert schema["schema_id"] == "PP-DESKTOP-NONDET-001"
    assert {item["id"] for item in schema["allowlisted_fields"]} >= {
        "pe_timedatestamp",
        "pe_checksum",
        "msi_package_code",
        "nsis_build_timestamp",
    }


def test_normalized_pe_comparison_ignores_only_allowlisted_fields(tmp_path: Path) -> None:
    schema = load_nondeterminism_schema(ROOT)
    left_dir = tmp_path / "A"
    right_dir = tmp_path / "B"
    left_dir.mkdir()
    right_dir.mkdir()
    left = _minimal_pe(timestamp=1, checksum=11)
    right = _minimal_pe(timestamp=99, checksum=22)
    (left_dir / "app.exe").write_bytes(left)
    (right_dir / "app.exe").write_bytes(right)
    normalized_left, removed_left = normalize_pe_image(left, schema)
    normalized_right, removed_right = normalize_pe_image(right, schema)
    assert removed_left == ("pe_timedatestamp", "pe_checksum")
    assert removed_right == ("pe_timedatestamp", "pe_checksum")
    assert normalized_left == normalized_right
    result = compare_normalized_trees(left_dir, right_dir, schema)
    assert result["passed"] is True


def _msi_like(*, package_code: str, payload: bytes) -> bytes:
    guid = f"{{{package_code}}}".encode("utf-16le")
    return CFB_MAGIC + b"\x00" * 24 + "PackageCode".encode("utf-16le") + guid + payload


def _nsis_like(*, timestamp: int, pe_timestamp: int = 1, payload: bytes = b"payload") -> bytes:
    body = bytearray(_minimal_pe(timestamp=pe_timestamp))
    header_timestamp = timestamp.to_bytes(4, "little")
    body.extend(header_timestamp + b"\x00\x00\x00\x00\x00\x00\x00\x00" + NSIS_SIGNATURE + payload)
    return bytes(body)


def test_msi_package_code_is_allowlisted_and_stripped(tmp_path: Path) -> None:
    schema = load_nondeterminism_schema(ROOT)
    left_dir = tmp_path / "A"
    right_dir = tmp_path / "B"
    left_dir.mkdir()
    right_dir.mkdir()
    payload = b"extracted-application-tree"
    left = _msi_like(package_code="AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA", payload=payload)
    right = _msi_like(package_code="BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB", payload=payload)
    (left_dir / "app.msi").write_bytes(left)
    (right_dir / "app.msi").write_bytes(right)
    normalized_left, removed_left = normalize_msi_container(left, schema)
    normalized_right, removed_right = normalize_msi_container(right, schema)
    assert removed_left == ("msi_package_code",)
    assert removed_right == ("msi_package_code",)
    assert normalized_left == normalized_right
    result = compare_normalized_trees(left_dir, right_dir, schema)
    assert result["passed"] is True


def test_msi_unallowlisted_payload_difference_fails(tmp_path: Path) -> None:
    schema = load_nondeterminism_schema(ROOT)
    left_dir = tmp_path / "A"
    right_dir = tmp_path / "B"
    left_dir.mkdir()
    right_dir.mkdir()
    (left_dir / "app.msi").write_bytes(
        _msi_like(package_code="AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA", payload=b"tree-a")
    )
    (right_dir / "app.msi").write_bytes(
        _msi_like(package_code="BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB", payload=b"tree-b")
    )
    result = compare_normalized_trees(left_dir, right_dir, schema)
    assert result["passed"] is False


def test_nsis_header_timestamp_is_allowlisted_and_stripped(tmp_path: Path) -> None:
    schema = load_nondeterminism_schema(ROOT)
    left_dir = tmp_path / "A"
    right_dir = tmp_path / "B"
    left_dir.mkdir()
    right_dir.mkdir()
    left = _nsis_like(timestamp=1_700_000_000, pe_timestamp=11)
    right = _nsis_like(timestamp=1_800_000_000, pe_timestamp=22)
    (left_dir / "installer.exe").write_bytes(left)
    (right_dir / "installer.exe").write_bytes(right)
    _, removed_left = normalize_nsis_installer(left, schema)
    _, removed_right = normalize_nsis_installer(right, schema)
    assert "nsis_build_timestamp" in removed_left
    assert "nsis_build_timestamp" in removed_right
    result = compare_normalized_trees(left_dir, right_dir, schema)
    assert result["passed"] is True


def test_compare_ignores_raw_hash_sidecars(tmp_path: Path) -> None:
    schema = load_nondeterminism_schema(ROOT)
    left_dir = tmp_path / "A"
    right_dir = tmp_path / "B"
    left_dir.mkdir()
    right_dir.mkdir()
    payload = _minimal_pe(timestamp=1)
    (left_dir / "app.exe").write_bytes(payload)
    (right_dir / "app.exe").write_bytes(payload)
    (left_dir / "hashes.json").write_text('{"lane":"A","sha256":"aaa"}\n', encoding="utf-8")
    (right_dir / "hashes.json").write_text('{"lane":"B","sha256":"bbb"}\n', encoding="utf-8")
    result = compare_normalized_trees(left_dir, right_dir, schema)
    assert result["passed"] is True
    assert all(item["name"] != "hashes.json" for item in result["comparisons"])


def test_unallowlisted_payload_difference_fails(tmp_path: Path) -> None:
    schema = load_nondeterminism_schema(ROOT)
    left_dir = tmp_path / "A"
    right_dir = tmp_path / "B"
    left_dir.mkdir()
    right_dir.mkdir()
    left = bytearray(_minimal_pe(timestamp=1))
    right = bytearray(_minimal_pe(timestamp=1))
    right[221] = (right[221] + 1) % 256
    (left_dir / "app.exe").write_bytes(left)
    (right_dir / "app.exe").write_bytes(right)
    result = compare_normalized_trees(left_dir, right_dir, schema)
    assert result["passed"] is False
    assert result["mismatches"]
