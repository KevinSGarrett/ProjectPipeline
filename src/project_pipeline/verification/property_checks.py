from __future__ import annotations

import random
from pathlib import Path

from project_pipeline.assurance import evaluate_completion_gate
from project_pipeline.domain.assurance import CompletionGateFacts, GateState, assurance_fingerprint
from project_pipeline.domain.scheduler import AccessMode, ResourceClaim, ResourceType
from project_pipeline.domain.verification import PropertyProbeResult, verification_identifier
from project_pipeline.scheduler import claims_conflict


def _gate_property(seed: int, cases: int) -> PropertyProbeResult:
    rng = random.Random(seed)
    failures: list[str] = []
    for index in range(cases):
        values = [bool(rng.getrandbits(1)) for _ in range(16)]
        gaps = 0 if bool(rng.getrandbits(1)) else rng.randint(1, 5)
        payload: dict[str, object] = {
            "source_requirements_dispositioned": values[0],
            "accepted_requirements_complete_or_external": values[1],
            "implementation_traceability_complete": values[2],
            "critical_paths_tested": values[3],
            "golden_journeys_pass": values[4],
            "autonomous_runtime_qualified": values[5],
            "security_gates_satisfied": values[6],
            "resilience_verified": values[7],
            "deployment_reproducible": values[8],
            "rollback_verified": values[9],
            "engineer_operable_from_docs": values[10],
            "ai_continuable_from_repo_and_jira": values[11],
            "unresolved_items_truthful": values[12],
            "command_center_truthful": values[13],
            "jira_truthful": values[14],
            "unattended_operating_loop_qualified": values[15],
            "unexplained_gap_count": gaps,
        }
        facts = CompletionGateFacts(
            project_id="PROJECT-PIPELINE",
            source_requirements_dispositioned=values[0],
            accepted_requirements_complete_or_external=values[1],
            implementation_traceability_complete=values[2],
            critical_paths_tested=values[3],
            golden_journeys_pass=values[4],
            autonomous_runtime_qualified=values[5],
            security_gates_satisfied=values[6],
            resilience_verified=values[7],
            deployment_reproducible=values[8],
            rollback_verified=values[9],
            engineer_operable_from_docs=values[10],
            ai_continuable_from_repo_and_jira=values[11],
            unresolved_items_truthful=values[12],
            command_center_truthful=values[13],
            jira_truthful=values[14],
            unattended_operating_loop_qualified=values[15],
            unexplained_gap_count=gaps,
            snapshot_fingerprint=assurance_fingerprint((index, payload)),
        )
        decision = evaluate_completion_gate(facts)
        expected = all(values) and gaps == 0
        if decision.final_complete != expected:
            failures.append(
                f"case {index}: expected final={expected}, observed={decision.final_complete}"
            )
        if not expected and decision.state is GateState.COMPLETE:
            failures.append(f"case {index}: incomplete facts produced COMPLETE")
    return PropertyProbeResult(
        property_id=verification_identifier(
            "PROP", "completion-gate-monotonic", str(seed), str(cases)
        ),
        property_name="Completion Gate can be COMPLETE iff every required fact is true and gap count is zero",
        case_count=cases,
        seed=seed,
        failure_count=len(failures),
        passed=not failures,
        failure_examples=tuple(failures[:10]),
    )


def _claim_symmetry_property(seed: int, cases: int) -> PropertyProbeResult:
    rng = random.Random(seed + 1)
    failures: list[str] = []
    kinds = list(ResourceType)
    modes = list(AccessMode)
    for index in range(cases):
        kind = rng.choice(kinds)
        identity = f"resource-{rng.randint(1, 7)}"
        left = ResourceClaim(
            resource_type=kind, resource_key=identity, access_mode=rng.choice(modes)
        )
        right = ResourceClaim(
            resource_type=kind, resource_key=identity, access_mode=rng.choice(modes)
        )
        lr = claims_conflict(left, right)
        rl = claims_conflict(right, left)
        if lr != rl:
            failures.append(f"case {index}: conflict relation is not symmetric")
    return PropertyProbeResult(
        property_id=verification_identifier(
            "PROP", "scheduler-conflict-symmetry", str(seed), str(cases)
        ),
        property_name="Scheduler resource conflict relation is symmetric for equivalent resource identities",
        case_count=cases,
        seed=seed + 1,
        failure_count=len(failures),
        passed=not failures,
        failure_examples=tuple(failures[:10]),
    )


def run_properties(root: Path, *, seed: int, cases: int) -> tuple[PropertyProbeResult, ...]:
    del root
    return (_gate_property(seed, cases), _claim_symmetry_property(seed, cases))
