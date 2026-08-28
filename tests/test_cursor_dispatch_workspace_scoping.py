"""Regression tests for provider-workspace scoping during Cursor qualification.

After dispatch the provider workspace is audited: any file in it other than the
requested artifact counts as an out-of-scope provider mutation. The qualification
harness previously materialized its own bootstrap evidence inside that same
workspace, so harness-written files were attributed to the provider and a
healthy dispatch was reported as FAILED with reason "out-of-scope mutation".

The bootstrap branch only runs when durable evidence is missing, so the verdict
depended on leftover state from earlier probe executions: the first observation
on a fresh machine failed and later observations passed. Because the campaign
runs this probe on a four-hour cadence, that produced the alternating pass/fail
behaviour that disqualified Cycle 16-B campaigns at stage transitions.
"""

from __future__ import annotations

import json
from pathlib import Path

from project_pipeline.autonomy_runtime.cursor_cli_qualification import (
    ARTIFACT_NAME,
    _artifact_payload,
    _readback_artifact,
    qualify_cursor_cli_provider,
)
from project_pipeline.lifecycle.attestation_recovery import (
    PUBLIC_ATTESTATION_REF,
    PUBLIC_QUALIFICATION_REF,
)

IDEMPOTENCY_KEY = "scoping-regression"


def _phase(report: dict, name: str) -> dict:
    for entry in report.get("phases", []):
        if entry.get("phase") == name:
            return entry.get("observations", {})
    raise AssertionError(f"phase {name} was not recorded")


def test_bootstrap_evidence_is_written_beside_the_workspace_not_inside_it(
    tmp_path: Path,
) -> None:
    """The defect itself: harness evidence must not land in the audited workspace."""

    candidate = tmp_path / "candidate"
    candidate.mkdir()
    disposable = tmp_path / "disposable"

    qualify_cursor_cli_provider(
        repository_root=candidate,
        disposable_root=disposable,
    )

    evidence_root = disposable / "public-evidence"
    assert (evidence_root / PUBLIC_ATTESTATION_REF).is_file()
    assert (evidence_root / PUBLIC_QUALIFICATION_REF).is_file()
    assert not (disposable / "cursor-cli-qualification" / "public-evidence").exists()


def test_relocated_bootstrap_evidence_still_validates(tmp_path: Path) -> None:
    """Moving the evidence root must not weaken evidence validation."""

    candidate = tmp_path / "candidate"
    candidate.mkdir()
    disposable = tmp_path / "disposable"

    report = qualify_cursor_cli_provider(
        repository_root=candidate,
        disposable_root=disposable,
    )

    validation = _phase(report, "EVIDENCE_VALIDATION")
    assert validation["accepted"] is True
    assert [item["disposition"] for item in validation["artifacts"]] == [
        "RECOVERED_VALID",
        "RECOVERED_VALID",
    ]
    assert (disposable / "cursor-cli-durable" / "privacy_attestation.json").is_file()
    assert (disposable / "cursor-cli-durable" / "provider_qualification.json").is_file()


def test_harness_files_in_the_workspace_are_audited_as_provider_mutations(
    tmp_path: Path,
) -> None:
    """Why placement matters: the audit cannot tell who wrote a workspace file.

    This pins the auditing semantics that made the misplaced evidence fatal.
    """

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ARTIFACT_NAME).write_text(
        json.dumps(_artifact_payload(IDEMPOTENCY_KEY), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    clean = _readback_artifact(workspace, IDEMPOTENCY_KEY)
    assert clean["ok"] is True
    assert clean["extras"] == []

    stray = workspace / "public-evidence" / "evidence" / "anything.json"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text("{}", encoding="utf-8")

    polluted = _readback_artifact(workspace, IDEMPOTENCY_KEY)
    assert polluted["ok"] is False
    assert polluted["extras"] == ["public-evidence/evidence/anything.json"]
    assert polluted["payload_matches"] is True


def test_verdict_is_identical_across_consecutive_observations(tmp_path: Path) -> None:
    """Consecutive observations must agree.

    The first run bootstraps durable evidence and the second finds it already
    present. These two runs take different internal branches, and before the fix
    they could disagree, which is what made a long campaign a coin flip.
    """

    candidate = tmp_path / "candidate"
    candidate.mkdir()
    disposable = tmp_path / "disposable"

    first = qualify_cursor_cli_provider(
        repository_root=candidate,
        disposable_root=disposable,
    )
    second = qualify_cursor_cli_provider(
        repository_root=candidate,
        disposable_root=disposable,
    )

    assert first["outcome"] == second["outcome"]
    assert tuple(first.get("reasons") or ()) == tuple(second.get("reasons") or ())
    assert "out-of-scope mutation" not in tuple(first.get("reasons") or ())
    assert "out-of-scope mutation" not in tuple(second.get("reasons") or ())
