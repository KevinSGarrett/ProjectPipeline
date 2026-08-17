from __future__ import annotations

import json
import subprocess
from pathlib import Path

from project_pipeline.validation.pp380_dispositions import (
    EXPECTED_EQUIVALENCE_CLAIMS,
    EXPECTED_EQUIVALENCE_FALSE,
    EXPECTED_EQUIVALENCE_TRUE,
    GENERATOR_VERSION,
    content_addressed_receipt,
    generate_pp380_corrected_dispositions,
    render_pp380_markdown,
    self_consistent_hash,
    validate_pp380_corrected_dispositions,
    write_pp380_outputs,
)

ROOT = Path(__file__).resolve().parents[1]


class _FakeGit:
    def __init__(self, blobs: dict[tuple[str, str], str | None], commits: dict[str, str]) -> None:
        self.blobs = blobs
        self.commits = commits

    def resolve_commit(self, ref: str) -> str:
        if ref not in self.commits:
            raise ValueError(f"git ref is not resolvable: {ref}")
        return self.commits[ref]

    def blob_sha256(self, commit: str, relative_path: str) -> str | None:
        return self.blobs.get((commit, relative_path))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _minimal_sources(tmp_path: Path) -> tuple[Path, Path, _FakeGit]:
    ledger = {
        "summary": {"commits": {"pp380": "pp380sha"}},
        "rows": [
            {
                "row_id": 1,
                "workspace": "main",
                "status_code": " M",
                "path": "keep.txt",
                "original_category": "SUPERSEDED_BY_PR44",
                "owner_task": "PR-44",
                "authority_classification": "AUXILIARY",
            },
            {
                "row_id": 2,
                "workspace": "main",
                "status_code": " M",
                "path": "diverge.txt",
                "original_category": "SUPERSEDED_BY_PR44",
                "owner_task": "PR-44",
                "authority_classification": "AUXILIARY",
            },
        ],
    }
    source_map = {
        "rows": [
            {
                "workspace": "main",
                "status_code": " M",
                "path": "keep.txt",
                "sha256": "a" * 64,
                "current_category": "SUPERSEDED_BY_PR44",
            },
            {
                "workspace": "main",
                "status_code": " M",
                "path": "diverge.txt",
                "sha256": "b" * 64,
                "current_category": "SUPERSEDED_BY_PR44",
            },
        ]
    }
    ledger_path = tmp_path / "ledger.json"
    map_path = tmp_path / "map.json"
    _write_json(ledger_path, ledger)
    _write_json(map_path, source_map)
    git = _FakeGit(
        blobs={
            ("pr44sha", "keep.txt"): "a" * 64,
            ("pr44sha", "diverge.txt"): "c" * 64,
            ("pr46sha", "keep.txt"): None,
            ("pp380sha", "keep.txt"): None,
        },
        commits={"pr44": "pr44sha", "pr46": "pr46sha", "pp380": "pp380sha"},
    )
    return ledger_path, map_path, git


def test_corrected_pp380_dispositions_are_hash_verified_and_complete() -> None:
    report_path = ROOT / "evidence" / "pp380_cycle6_corrected_dispositions.json"
    errors = validate_pp380_corrected_dispositions(ROOT, report_path)
    assert errors == []
    document = json.loads(report_path.read_text(encoding="utf-8"))
    assert document["summary"]["equivalence_claim_rows"] == EXPECTED_EQUIVALENCE_CLAIMS
    assert document["summary"]["equivalence_true"] == EXPECTED_EQUIVALENCE_TRUE
    assert document["summary"]["equivalence_false"] == EXPECTED_EQUIVALENCE_FALSE
    assert not Path(document["summary"]["source_cycle5_disposition"]).is_absolute()
    assert not Path(document["summary"]["source_reconciliation_map"]).is_absolute()


def test_corrected_pp380_dispositions_tampered_receipt_fails(tmp_path: Path) -> None:
    source_path = ROOT / "evidence" / "pp380_cycle6_corrected_dispositions.json"
    document = json.loads(source_path.read_text(encoding="utf-8"))
    document["generation_proof"]["content_addressed_receipt_sha256"] = "0" * 64
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    errors = validate_pp380_corrected_dispositions(ROOT, tampered)
    assert "generation_proof content-addressed receipt is invalid" in errors


def test_corrected_pp380_dispositions_runtime_evidence_regeneration_fails(tmp_path: Path) -> None:
    source_path = ROOT / "evidence" / "pp380_cycle6_corrected_dispositions.json"
    document = json.loads(source_path.read_text(encoding="utf-8"))
    row = next(
        entry
        for entry in document["rows"]
        if entry["original_category"] == "LOCAL_RUNTIME_EVIDENCE"
    )
    row["proposed_final_action"] = "REGENERATE_AFTER_INTEGRATION"
    tampered = tmp_path / "tampered_runtime.json"
    tampered.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    errors = validate_pp380_corrected_dispositions(ROOT, tampered, verify_sources=False)
    assert any("runtime evidence must preserve observed artifact" in error for error in errors)


def test_corrected_pp380_dispositions_unknown_owner_regeneration_fails(tmp_path: Path) -> None:
    source_path = ROOT / "evidence" / "pp380_cycle6_corrected_dispositions.json"
    document = json.loads(source_path.read_text(encoding="utf-8"))
    row = next(entry for entry in document["rows"] if entry["original_category"] == "UNKNOWN_OWNER")
    row["proposed_final_action"] = "REGENERATE_AFTER_INTEGRATION"
    tampered = tmp_path / "tampered_owner.json"
    tampered.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    errors = validate_pp380_corrected_dispositions(ROOT, tampered, verify_sources=False)
    assert any(
        "unknown owner row must remain preserved pending attestation" in error for error in errors
    )


def test_source_map_tamper_is_detected(tmp_path: Path) -> None:
    source_path = ROOT / "evidence" / "pp380_cycle6_corrected_dispositions.json"
    document = json.loads(source_path.read_text(encoding="utf-8"))
    document["generation_proof"]["source_map_sha256"] = "1" * 64
    document["generation_proof"]["self_consistent_hash_sha256"] = self_consistent_hash(
        generator_version=document["generation_proof"]["generator_version"],
        source_map_sha256="1" * 64,
        source_ledger_sha256=document["generation_proof"]["source_ledger_sha256"],
        rows_sha256=document["generation_proof"]["rows_sha256"],
    )
    tampered = tmp_path / "map_tamper.json"
    tampered.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    errors = validate_pp380_corrected_dispositions(ROOT, tampered)
    assert any("source_map_sha256 does not match" in error for error in errors)


def test_source_ledger_tamper_is_detected(tmp_path: Path) -> None:
    source_path = ROOT / "evidence" / "pp380_cycle6_corrected_dispositions.json"
    document = json.loads(source_path.read_text(encoding="utf-8"))
    document["generation_proof"]["source_ledger_sha256"] = "2" * 64
    document["generation_proof"]["self_consistent_hash_sha256"] = self_consistent_hash(
        generator_version=document["generation_proof"]["generator_version"],
        source_map_sha256=document["generation_proof"]["source_map_sha256"],
        source_ledger_sha256="2" * 64,
        rows_sha256=document["generation_proof"]["rows_sha256"],
    )
    tampered = tmp_path / "ledger_tamper.json"
    tampered.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    errors = validate_pp380_corrected_dispositions(ROOT, tampered)
    assert any("source_ledger_sha256 does not match" in error for error in errors)


def test_coordinated_document_tamper_cannot_recompute_content_addressed_receipt(
    tmp_path: Path,
) -> None:
    source_path = ROOT / "evidence" / "pp380_cycle6_corrected_dispositions.json"
    document = json.loads(source_path.read_text(encoding="utf-8"))
    document["rows"][0]["semantic_reason"] = "coordinated tamper"
    rows_sha256 = document["generation_proof"]["rows_sha256"]
    document["generation_proof"]["self_consistent_hash_sha256"] = self_consistent_hash(
        generator_version=document["generation_proof"]["generator_version"],
        source_map_sha256=document["generation_proof"]["source_map_sha256"],
        source_ledger_sha256=document["generation_proof"]["source_ledger_sha256"],
        rows_sha256=rows_sha256,
    )
    document["generation_proof"]["content_addressed_receipt_sha256"] = content_addressed_receipt(
        generator_version=GENERATOR_VERSION,
        source_map_bytes=b"not-the-real-source-map",
        source_ledger_bytes=b"not-the-real-source-ledger",
        git_ref_receipts=document["generation_proof"]["git_ref_receipts"],
        rows=document["rows"],
    )
    tampered = tmp_path / "coordinated.json"
    tampered.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    errors = validate_pp380_corrected_dispositions(ROOT, tampered)
    assert any(
        "content-addressed receipt is invalid" in error or "rows_sha256" in error
        for error in errors
    )


def test_wrong_ref_and_missing_optional_object_fail(tmp_path: Path) -> None:
    ledger_path, map_path, git = _minimal_sources(tmp_path)
    document = generate_pp380_corrected_dispositions(
        repo_root=tmp_path,
        source_ledger_path=ledger_path,
        source_map_path=map_path,
        pr44_ref="pr44",
        pr46_ref="pr46",
        pp380_ref="pp380",
        git=git,
    )
    output = tmp_path / "out.json"
    write_pp380_outputs(document, output, tmp_path / "out.md")
    document["generation_proof"]["git_ref_receipts"]["pr44"]["requested_ref"] = "missing-ref"
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    errors = validate_pp380_corrected_dispositions(tmp_path, output, git=git)
    assert any("git ref is not resolvable: missing-ref" in error for error in errors)


def test_duplicate_and_missing_rows_fail(tmp_path: Path) -> None:
    ledger_path, map_path, git = _minimal_sources(tmp_path)
    document = generate_pp380_corrected_dispositions(
        repo_root=tmp_path,
        source_ledger_path=ledger_path,
        source_map_path=map_path,
        pr44_ref="pr44",
        pr46_ref="pr46",
        pp380_ref="pp380",
        git=git,
    )
    document["rows"].append(document["rows"][0])
    output = tmp_path / "dup.json"
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    errors = validate_pp380_corrected_dispositions(tmp_path, output, verify_sources=False, git=git)
    assert any("duplicate row_id" in error for error in errors)

    document["rows"] = [document["rows"][1]]
    document["summary"]["row_count"] = 1
    missing = tmp_path / "missing.json"
    missing.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    errors = validate_pp380_corrected_dispositions(tmp_path, missing, verify_sources=False, git=git)
    assert any("contiguous 1..N" in error for error in errors)


def test_wrong_action_and_category_fail(tmp_path: Path) -> None:
    ledger_path, map_path, git = _minimal_sources(tmp_path)
    document = generate_pp380_corrected_dispositions(
        repo_root=tmp_path,
        source_ledger_path=ledger_path,
        source_map_path=map_path,
        pr44_ref="pr44",
        pr46_ref="pr46",
        pp380_ref="pp380",
        git=git,
    )
    document["rows"][0]["proposed_final_action"] = "COMMIT_UNIQUE_PP380_DELTA"
    document["rows"][0]["original_category"] = "UNIQUE_ACCEPTANCE_WORK"
    output = tmp_path / "wrong_action.json"
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    errors = validate_pp380_corrected_dispositions(tmp_path, output, git=git)
    assert any(
        "do not match canonical regeneration" in error
        or "action_counts mismatch" in error
        or "equivalence_claim_rows" in error
        for error in errors
    )


def test_byte_identical_regeneration_and_portable_paths(tmp_path: Path) -> None:
    ledger_path, map_path, git = _minimal_sources(tmp_path)
    first = generate_pp380_corrected_dispositions(
        repo_root=tmp_path,
        source_ledger_path=ledger_path,
        source_map_path=map_path,
        pr44_ref="pr44",
        pr46_ref="pr46",
        pp380_ref="pp380",
        git=git,
    )
    second = generate_pp380_corrected_dispositions(
        repo_root=tmp_path,
        source_ledger_path=ledger_path,
        source_map_path=map_path,
        pr44_ref="pr44",
        pr46_ref="pr46",
        pp380_ref="pp380",
        git=git,
    )
    assert json.dumps(first, indent=2) == json.dumps(second, indent=2)
    assert render_pp380_markdown(first) == render_pp380_markdown(second)
    assert first["summary"]["source_cycle5_disposition"] == "ledger.json"
    assert first["summary"]["equivalence_claim_rows"] == 2
    assert first["summary"]["equivalence_true"] == 1
    assert (
        first["rows"][0]["proposed_final_action"] == "SUPERSEDED_BY_EXACT_PR_HEAD_AND_EQUIVALENCE"
    )
    assert first["rows"][1]["proposed_final_action"] == "THREE_WAY_RECONCILE_AFTER_PR44"


def test_clean_clone_generator_invocation(tmp_path: Path) -> None:
    repo = tmp_path / "clone"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "pp380@example.local"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "PP380"], cwd=repo, check=True)
    (repo / "keep.txt").write_text("keep\n", encoding="utf-8")
    (repo / "diverge.txt").write_text("left\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "pr44"], cwd=repo, check=True, capture_output=True)
    pr44 = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    (repo / "diverge.txt").write_text("right\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "unique"], cwd=repo, check=True, capture_output=True)
    unique = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    ledger = {
        "summary": {"commits": {"pp380": unique}},
        "rows": [
            {
                "row_id": 1,
                "workspace": "main",
                "status_code": " M",
                "path": "keep.txt",
                "original_category": "SUPERSEDED_BY_PR44",
                "owner_task": "PR-44",
                "authority_classification": "AUXILIARY",
            }
        ],
    }
    keep_hash = __import__("hashlib").sha256(b"keep\n").hexdigest()
    source_map = {
        "rows": [
            {
                "workspace": "main",
                "status_code": " M",
                "path": "keep.txt",
                "sha256": keep_hash,
                "current_category": "SUPERSEDED_BY_PR44",
            }
        ]
    }
    (repo / "evidence").mkdir()
    _write_json(repo / "evidence" / "ledger.json", ledger)
    _write_json(repo / "evidence" / "map.json", source_map)
    document = generate_pp380_corrected_dispositions(
        repo_root=repo,
        source_ledger_path=repo / "evidence" / "ledger.json",
        source_map_path=repo / "evidence" / "map.json",
        pr44_ref=pr44,
        pr46_ref=pr44,
        pp380_ref=unique,
    )
    output = repo / "evidence" / "out.json"
    write_pp380_outputs(document, output, repo / "evidence" / "out.md")
    assert document["rows"][0]["content_equal"] is True
    assert validate_pp380_corrected_dispositions(repo, output) == []
