from __future__ import annotations

import tempfile
from pathlib import Path

from pydantic import ValidationError

from project_pipeline.assurance import evaluate_completion_gate
from project_pipeline.domain.assurance import CompletionGateFacts, assurance_fingerprint
from project_pipeline.domain.verification import (
    VerificationCategory,
    VerificationCheckResult,
    VerificationResultState,
)
from project_pipeline.verification.external_tools import AxeCoreProfile, SchemathesisAdapter


def run_adversarial_checks(root: Path) -> tuple[str, ...]:
    observations: list[str] = []

    try:
        VerificationCheckResult(
            check_id="VCHK-" + "A" * 20,
            state=VerificationResultState.SKIPPED,
            required=True,
            category=VerificationCategory.CONTRACT,
            duration_ms=0,
            reason="attempted silent skip",
        )
    except ValidationError:
        observations.append("required-check-silent-skip rejected")
    else:
        raise AssertionError("required verification check accepted SKIPPED")

    values = {
        "source_requirements_dispositioned": True,
        "accepted_requirements_complete_or_external": True,
        "implementation_traceability_complete": True,
        "critical_paths_tested": True,
        "golden_journeys_pass": True,
        "autonomous_runtime_qualified": True,
        "security_gates_satisfied": True,
        "resilience_verified": True,
        "deployment_reproducible": True,
        "rollback_verified": True,
        "engineer_operable_from_docs": True,
        "ai_continuable_from_repo_and_jira": True,
        "unresolved_items_truthful": True,
        "command_center_truthful": False,
        "jira_truthful": True,
        "unattended_operating_loop_qualified": True,
        "unexplained_gap_count": 0,
    }
    decision = evaluate_completion_gate(
        CompletionGateFacts(
            project_id="PROJECT-PIPELINE",
            **values,
            snapshot_fingerprint=assurance_fingerprint(values),
        )
    )
    if decision.final_complete:
        raise AssertionError("Completion Gate accepted a false required fact")
    observations.append("single-false-completion-fact prevents completion")

    with tempfile.TemporaryDirectory() as temp:
        outside = Path(temp) / "schema.json"
        outside.write_text("{}", encoding="utf-8")
        try:
            SchemathesisAdapter().build(root, schema=outside, base_url="http://127.0.0.1:9999")
        except ValueError:
            observations.append("api-schema-path-traversal rejected")
        else:
            raise AssertionError("Schemathesis adapter accepted out-of-root schema")

        try:
            AxeCoreProfile().validate_bundle(root, outside)
        except ValueError:
            observations.append("external-axe-bundle rejected")
        else:
            raise AssertionError("axe-core profile accepted out-of-root bundle")

    return tuple(observations)
