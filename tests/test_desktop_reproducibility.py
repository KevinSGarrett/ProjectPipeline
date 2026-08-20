from __future__ import annotations

from pathlib import Path

from project_pipeline.command_center.desktop_reproducibility import (
    compare_normalized_trees,
    load_nondeterminism_schema,
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
