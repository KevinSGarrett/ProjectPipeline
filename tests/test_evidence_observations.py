from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from project_pipeline.assurance.observation import (
    evidence_status,
    generate_observation,
    record_observation,
)
from project_pipeline.assurance.observation_store import (
    EvidenceObservationStore,
    ObservationStoreError,
)
from project_pipeline.cli import main
from project_pipeline.domain.evidence_observation import EnvironmentClass, ObservationResult
from project_pipeline.io import sha256_canonical_file

CURRENT_SHA = "c" * 40
CURRENT_TREE = "d" * 40


def _record(store: EvidenceObservationStore, evidence_id: str, digest: str, **updates):
    payload = {
        "evidence_id": evidence_id,
        "test_ids": ["TEST-A"],
        "criterion_ids": ["AC-A"],
        "requirement_ids": ["REQ-GOV-0001"],
        "integrated_sha": CURRENT_SHA,
        "integrated_tree": CURRENT_TREE,
        "acceptance_scope_fingerprint": "a" * 64,
        "path_fingerprints": {"src/module.py": digest},
        "artifact_digest": digest,
        "command_identity": ("pytest", "tests/test_a.py"),
        "environment_class": EnvironmentClass.LOCAL,
        "result": ObservationResult.PASS,
        "independent_verification_receipt": "unit",
    }
    payload.update(updates)
    return record_observation(store, **payload)


def test_windows_paths_and_lf_hashing(tmp_path: Path) -> None:
    artifact = tmp_path / "receipt.txt"
    artifact.write_bytes(b"alpha\r\nbeta\r\n")
    digest = sha256_canonical_file(artifact)
    lf = tmp_path / "receipt_lf.txt"
    lf.write_bytes(b"alpha\nbeta\n")
    assert digest == sha256_canonical_file(lf)
    store = EvidenceObservationStore.open(tmp_path)
    observation = _record(
        store,
        "EVID-000001",
        digest,
        path_fingerprints={"src\\module.py": digest},
    )
    assert observation.path_fingerprints["src\\module.py"] == digest
    assert store.get(observation.observation_id) is not None


def test_idempotent_and_conflicting_replay(tmp_path: Path) -> None:
    store = EvidenceObservationStore.open(tmp_path)
    first = _record(store, "EVID-000001", "b" * 64)
    again = store.put(first)
    assert again.observation_id == first.observation_id
    mutated = first.model_copy(update={"independent_verification_receipt": "other"})
    try:
        store.put(mutated)
        raise AssertionError("conflicting replay must fail closed")
    except ObservationStoreError as exc:
        assert "conflicting replay" in str(exc)


def test_concurrent_writers_are_serialized(tmp_path: Path) -> None:
    store = EvidenceObservationStore.open(tmp_path)
    errors: list[str] = []

    def write(index: int) -> None:
        try:
            _record(
                store,
                f"EVID-{index:06d}",
                "c" * 64,
                test_ids=[f"TEST-{index}"],
            )
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=write, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert store.status()["observations"] == 8


def test_crash_recovery_replays_journal(tmp_path: Path) -> None:
    store = EvidenceObservationStore.open(tmp_path)
    observation = _record(store, "EVID-000009", "d" * 64)
    store._db.execute("DELETE FROM evidence_observations")
    store._db.commit()
    restored = store.replay_journal()
    assert restored == 1
    assert store.get(observation.observation_id) is not None


def test_retention_keeps_current_and_drops_superseded(tmp_path: Path) -> None:
    store = EvidenceObservationStore.open(tmp_path)
    first = _record(store, "EVID-000010", "e" * 64)
    second = _record(store, "EVID-000010", "e" * 64, command_identity=("pytest", "retry"))
    assert second.supersedes == first.observation_id
    removed = store.retain(keep_current=True, max_age_seconds=0)
    assert removed == 1
    assert store.get(second.observation_id) is not None
    assert store.get(first.observation_id) is None


def test_evidence_cli_list_get_status(tmp_path: Path, capsys) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    artifact = evidence_dir / "receipt.txt"
    artifact.write_text("ok\n", encoding="utf-8")
    row = {
        "artifact_path": "evidence/receipt.txt",
        "claim": "cli status",
        "criterion_ids": ["AC-1"],
        "environment": "local_build_environment",
        "evidence_id": "EVID-000001",
        "method": "pytest",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "requirement_ids": ["REQ-GOV-0001"],
        "result": "PASS",
        "schema_version": "1.0.0",
        "sha256": sha256_canonical_file(artifact),
        "supersedes": None,
        "verification_status": "VERIFIED",
    }
    (evidence_dir / "EVIDENCE_LEDGER.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert main(["evidence", "list", "--root", str(tmp_path)]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["count"] == 1
    assert main(["evidence", "get", "--root", str(tmp_path), "--evidence-id", "EVID-000001"]) == 0
    gotten = json.loads(capsys.readouterr().out)
    assert gotten["definition"]["evidence_id"] == "EVID-000001"
    assert main(["evidence", "status", "--root", str(tmp_path)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["definitions"] == 1
    assert status["inline_subject_bindings"] == 0
    assert evidence_status(tmp_path)["definitions"] == 1


def test_generate_observation_uses_injected_runner(tmp_path: Path) -> None:
    (tmp_path / "plans/_traceability").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src").mkdir()
    impl = tmp_path / "src" / "module.py"
    impl.write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_mod.py").write_text(
        "def test_mod():\n    assert 1 == 1\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "TEST_CATALOG.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0.0",
                "test_count": 1,
                "tests": [
                    {"test_id": "TEST-MOD", "path": "tests/test_mod.py", "callable": "test_mod"}
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "plans/_traceability/requirements.jsonl").write_text(
        json.dumps(
            {
                "requirement_id": "REQ-GOV-0001",
                "implementation_paths": ["src/module.py"],
                "test_ids": ["TEST-MOD"],
                "evidence_ids": ["EVID-000001"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    artifact = tmp_path / "evidence" / "receipt.txt"
    artifact.parent.mkdir()
    artifact.write_text("ok\n", encoding="utf-8")
    (tmp_path / "evidence" / "EVIDENCE_LEDGER.jsonl").write_text(
        json.dumps(
            {
                "artifact_path": "evidence/receipt.txt",
                "claim": "mod",
                "criterion_ids": ["AC-1"],
                "environment": "local_build_environment",
                "evidence_id": "EVID-000001",
                "method": "pytest",
                "observed_at_utc": datetime.now(UTC).isoformat(),
                "requirement_ids": ["REQ-GOV-0001"],
                "result": "PASS",
                "schema_version": "1.0.0",
                "sha256": sha256_canonical_file(artifact),
                "test_ids": ["TEST-MOD"],
                "verification_status": "VERIFIED",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def runner(test_ids, paths):
        assert test_ids == ["TEST-MOD"]
        assert paths == ["tests/test_mod.py"]
        return {test_id: "PASS" for test_id in test_ids}

    observation = generate_observation(
        tmp_path,
        "EVID-000001",
        runner=runner,
        current_sha=CURRENT_SHA,
        current_tree=CURRENT_TREE,
    )
    assert observation.result is ObservationResult.PASS
    assert observation.integrated_sha == CURRENT_SHA
