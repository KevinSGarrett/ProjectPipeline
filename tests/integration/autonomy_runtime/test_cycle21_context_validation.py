"""Cycle 21 context pack compile, consume, native tests, and negatives."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime.context_validation import (
    NATIVE_FAIL,
    NATIVE_PASS,
    compile_validation_pack,
    consume_pack_on_worker,
    execute_native_tests,
    verify_output_contract,
)

SHA = "f41c64d5b533ed4a329e0e431ee073dd791ee050"
TREE = "66778a1fdc0a7a8d8cf3b07f25367ed896ffca2b"
OVERLAY = "c" * 64
HOST = "COMFY-V4-CPU-01"
PRINCIPAL = r"comfy-v4-cpu-01\windows 11"


def _compile(tmp_path: Path, project_root: Path) -> dict[str, object]:
    return compile_validation_pack(
        root=project_root,
        database=tmp_path / "context.sqlite3",
        task_id="PP-TASK-000521",
        source_sha=SHA,
        source_tree=TREE,
        overlay_sha256=OVERLAY,
        selection=(NATIVE_PASS,),
        host_id=HOST,
        principal=PRINCIPAL,
    )


def _consume_payload(
    tmp_path: Path, compiled: dict[str, object], **changes: object
) -> dict[str, object]:
    payload: dict[str, object] = {
        "pack_path": str(tmp_path / "context_pack.json"),
        "workspace": str(tmp_path),
        "pack_sha256": compiled["pack"]["content_sha256"],  # type: ignore[index]
        "source_sha": SHA,
        "source_tree": TREE,
        "overlay_sha256": OVERLAY,
        "host_id": HOST,
        "principal": PRINCIPAL,
        "job_id": "PP-TASK-000521",
        "project_id": "PROJECT-PIPELINE",
    }
    payload.update(changes)
    return payload


def test_compile_and_consume_pack(tmp_path: Path, project_root: Path) -> None:
    compiled = _compile(tmp_path, project_root)
    assert compiled["ok"] is True
    pack_path = tmp_path / "context_pack.json"
    pack_path.write_text(json.dumps(compiled["pack"], sort_keys=True), encoding="utf-8")
    consumed = consume_pack_on_worker(_consume_payload(tmp_path, compiled))
    assert consumed["ok"] is True
    assert consumed["worker_id"]
    assert consumed["pack_id"] == compiled["pack_id"]


def test_tampered_and_wrong_project_packs_fail(tmp_path: Path, project_root: Path) -> None:
    compiled = _compile(tmp_path, project_root)
    pack = dict(compiled["pack"])  # type: ignore[arg-type]
    original_digest = str(pack["content_sha256"])
    pack["items"] = []
    pack_path = tmp_path / "context_pack.json"
    pack_path.write_text(json.dumps(pack, sort_keys=True), encoding="utf-8")
    tampered = consume_pack_on_worker(
        _consume_payload(tmp_path, compiled, pack_sha256=original_digest)
    )
    assert tampered["ok"] is False
    assert tampered["reason"] == "pack_tampered"
    pack_path.unlink()
    missing = consume_pack_on_worker(
        _consume_payload(tmp_path, compiled, pack_sha256=original_digest)
    )
    assert missing["ok"] is False
    assert missing["reason"] == "pack_missing"
    pack_path.write_text(json.dumps(compiled["pack"], sort_keys=True), encoding="utf-8")
    wrong_project = consume_pack_on_worker(
        _consume_payload(tmp_path, compiled, project_id="OTHER-PROJECT")
    )
    assert wrong_project["ok"] is False
    assert wrong_project["reason"] == "wrong_project"
    wrong_overlay = consume_pack_on_worker(
        _consume_payload(tmp_path, compiled, overlay_sha256="d" * 64)
    )
    assert wrong_overlay["ok"] is False
    assert wrong_overlay["reason"] == "wrong_overlay"


def test_native_pass_and_known_fail_fixture(tmp_path: Path, project_root: Path) -> None:
    passed = execute_native_tests(
        root=project_root, selection=(NATIVE_PASS,), output_dir=tmp_path / "pass"
    )
    assert passed["ok"] is True
    assert int(passed["collected"]) >= 1
    assert passed["junit_sha256"]
    failed = execute_native_tests(
        root=project_root, selection=(NATIVE_FAIL,), output_dir=tmp_path / "fail"
    )
    assert failed["ok"] is False
    assert failed["status"] == "FAIL"
    contract = verify_output_contract(failed, artifact_bytes=None)
    assert contract["ok"] is False


def test_relative_output_dir_writes_junit_even_when_pytest_cwd_differs(
    tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    monkeypatch.chdir(jobs)
    passed = execute_native_tests(root=project_root, selection=(NATIVE_PASS,), output_dir=Path())
    assert passed["ok"] is True
    assert int(passed["collected"]) >= 1
    junit = jobs / "junit.xml"
    assert junit.is_file()
    assert Path(str(passed["junit_path"])).resolve() == junit.resolve()
    junit_arg = next(item for item in passed["command"] if str(item).startswith("--junitxml="))
    assert Path(str(junit_arg).split("=", 1)[1]).is_absolute()
