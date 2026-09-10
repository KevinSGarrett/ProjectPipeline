"""Cycle 21 context pack compile, consume, native tests, and negatives."""

from __future__ import annotations

import json
from pathlib import Path

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


def test_compile_and_consume_pack(tmp_path: Path, project_root: Path) -> None:
    compiled = compile_validation_pack(
        root=project_root,
        database=tmp_path / "context.sqlite3",
        task_id="PP-TASK-000521",
        source_sha=SHA,
        source_tree=TREE,
        overlay_sha256="c" * 64,
        selection=(NATIVE_PASS,),
        host_id="COMFY-V4-CPU-01",
        principal=r"comfy-v4-cpu-01\windows 11",
    )
    assert compiled["ok"] is True
    pack_path = tmp_path / "context_pack.json"
    pack_path.write_text(json.dumps(compiled["pack"], sort_keys=True), encoding="utf-8")
    consumed = consume_pack_on_worker(
        {
            "pack_path": str(pack_path),
            "pack_sha256": compiled["pack"]["content_sha256"],
            "source_sha": SHA,
            "source_tree": TREE,
            "host_id": "COMFY-V4-CPU-01",
            "principal": r"comfy-v4-cpu-01\windows 11",
            "job_id": "PP-TASK-000521",
        }
    )
    assert consumed["ok"] is True
    assert consumed["worker_id"]
    assert consumed["pack_id"] == compiled["pack_id"]


def test_tampered_and_wrong_project_packs_fail(tmp_path: Path, project_root: Path) -> None:
    compiled = compile_validation_pack(
        root=project_root,
        database=tmp_path / "context.sqlite3",
        task_id="PP-TASK-000521",
        source_sha=SHA,
        source_tree=TREE,
        overlay_sha256="c" * 64,
        selection=(NATIVE_PASS,),
        host_id="COMFY-V4-CPU-01",
        principal=r"comfy-v4-cpu-01\windows 11",
    )
    pack = dict(compiled["pack"])
    pack["items"] = []
    pack_path = tmp_path / "context_pack.json"
    pack_path.write_text(json.dumps(pack, sort_keys=True), encoding="utf-8")
    tampered = consume_pack_on_worker(
        {
            "pack_path": str(pack_path),
            "pack_sha256": compiled["pack"]["content_sha256"],
            "source_sha": SHA,
            "source_tree": TREE,
            "host_id": "COMFY-V4-CPU-01",
            "principal": r"comfy-v4-cpu-01\windows 11",
        }
    )
    assert tampered["ok"] is False
    missing = consume_pack_on_worker({"pack_path": str(tmp_path / "absent.json")})
    assert missing["ok"] is False
    assert missing["reason"] == "pack_missing"


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
