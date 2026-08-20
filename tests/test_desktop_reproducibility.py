from __future__ import annotations

from pathlib import Path

from project_pipeline.command_center.desktop_reproducibility import (
    NSIS_SIGNATURE,
    DesktopReproducibilityError,
    compare_desktop_artifact_sets,
    compare_extracted_payload_trees,
    compare_normalized_trees,
    extract_msi_administrative_image,
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


def _nsis_pe(*, pe_timestamp: int) -> bytes:
    return _minimal_pe(timestamp=pe_timestamp) + b"\xef\xbe\xad\xde" + NSIS_SIGNATURE + b"body"


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


def test_identity_msi_containers_are_not_compared_as_raw_bytes(tmp_path: Path) -> None:
    schema = load_nondeterminism_schema(ROOT)
    left_dir = tmp_path / "A"
    right_dir = tmp_path / "B"
    for root in (left_dir, right_dir):
        (root / "compare").mkdir(parents=True)
        (root / "identity").mkdir(parents=True)
        (root / "compare" / "app.exe").write_bytes(_minimal_pe(timestamp=3))
    (left_dir / "identity" / "app.msi").write_bytes(b"D0CF-left-package-code")
    (right_dir / "identity" / "app.msi").write_bytes(b"D0CF-right-package-code")
    result = compare_normalized_trees(left_dir, right_dir, schema)
    assert result["passed"] is True
    assert all(not item["name"].endswith(".msi") for item in result["comparisons"])


def test_extracted_msi_payload_trees_ignore_package_identity(tmp_path: Path) -> None:
    schema = load_nondeterminism_schema(ROOT)
    left = tmp_path / "extract-A"
    right = tmp_path / "extract-B"
    for root, stamp, residual in ((left, 4, b"residual-A"), (right, 8, b"residual-B")):
        (root / "ProgramFiles").mkdir(parents=True)
        (root / "ProgramFiles" / "app.exe").write_bytes(_minimal_pe(timestamp=stamp))
        (root / "app.msi").write_bytes(residual)
    result = compare_extracted_payload_trees(
        left, right, schema, name="app.msi", removed_field="msi_package_code"
    )
    assert result["equal"] is True
    assert "msi_package_code" in result["left_removed_fields"]
    assert "msi_package_code" in result["right_removed_fields"]


def test_extracted_msi_payload_difference_fails(tmp_path: Path) -> None:
    schema = load_nondeterminism_schema(ROOT)
    left = tmp_path / "extract-A"
    right = tmp_path / "extract-B"
    left.mkdir()
    right.mkdir()
    (left / "app.exe").write_bytes(_minimal_pe(timestamp=1))
    changed = bytearray(_minimal_pe(timestamp=1))
    changed[221] = (changed[221] + 1) % 256
    (right / "app.exe").write_bytes(changed)
    result = compare_extracted_payload_trees(
        left, right, schema, name="app.msi", removed_field="msi_package_code"
    )
    assert result["equal"] is False


def test_missing_msiexec_is_fail_closed(tmp_path: Path, monkeypatch) -> None:
    def _raise(*_args, **_kwargs):
        raise FileNotFoundError("msiexec")

    monkeypatch.setattr(
        "project_pipeline.command_center.desktop_reproducibility.subprocess.run",
        _raise,
    )
    msi = tmp_path / "app.msi"
    msi.write_bytes(b"not-a-real-msi")
    try:
        extract_msi_administrative_image(msi, tmp_path / "out")
    except DesktopReproducibilityError as exc:
        assert "unavailable" in str(exc)
    else:
        raise AssertionError("missing msiexec must fail closed")


def test_unextractable_identity_msi_fails_closed(tmp_path: Path) -> None:
    schema = load_nondeterminism_schema(ROOT)
    left_dir = tmp_path / "A"
    right_dir = tmp_path / "B"
    for root in (left_dir, right_dir):
        (root / "compare").mkdir(parents=True)
        (root / "identity").mkdir(parents=True)
        (root / "compare" / "app.exe").write_bytes(_minimal_pe(timestamp=1))
        (root / "identity" / "app.msi").write_bytes(b"not-a-real-msi")
    result = compare_desktop_artifact_sets(left_dir, right_dir, schema)
    assert result["passed"] is False
    assert any("msiexec" in item or "extract" in item.lower() for item in result["mismatches"])


def test_nsis_identity_uses_pe_container_timestamp(tmp_path: Path) -> None:
    schema = load_nondeterminism_schema(ROOT)
    left_dir = tmp_path / "A"
    right_dir = tmp_path / "B"
    for root, stamp in ((left_dir, 11), (right_dir, 22)):
        (root / "compare").mkdir(parents=True)
        (root / "identity").mkdir(parents=True)
        (root / "compare" / "app.exe").write_bytes(_minimal_pe(timestamp=stamp))
        (root / "identity" / "setup.exe").write_bytes(_nsis_pe(pe_timestamp=stamp))
    result = compare_desktop_artifact_sets(left_dir, right_dir, schema)
    assert result["passed"] is True
    nsis = next(item for item in result["comparisons"] if item["name"] == "setup.exe")
    assert "nsis_build_timestamp" in nsis["left_removed_fields"]


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
