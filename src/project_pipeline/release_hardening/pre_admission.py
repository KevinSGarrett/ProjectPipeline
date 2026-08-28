"""Phase-aware release gates.

`build_hardening_report` stays a local, pre-release snapshot that can never
declare itself production ready. Campaign admission needs a different question
answered: are the prerequisites that *can* be satisfied before the timed
campaign satisfied? Publication needs a third, strictly fail-closed question
that still defers to the deterministic Completion Gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from project_pipeline.security.supply_chain import evaluate_supply_chain

REQUIRED_DURATION_STAGES = (
    "UNATTENDED_4_HOUR",
    "UNATTENDED_24_HOUR",
    "UNATTENDED_72_HOUR",
)

# Emitted by the local hardening snapshot to preserve the self-certification
# boundary. It is definitionally unsatisfiable before publication, so it must
# not be treated as a pre-admission prerequisite.
SELF_CERTIFICATION_BOUNDARY_BLOCKER = (
    "independent Completion Gate has not declared the project complete"
)


class PreAdmissionState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


@dataclass(frozen=True)
class PreAdmissionVerdict:
    """Whether the candidate may enter the timed duration campaign."""

    state: PreAdmissionState
    blockers: tuple[str, ...] = ()
    supply_chain_state: str = "UNKNOWN"
    resolver_lock_state: str = "UNKNOWN"


@dataclass(frozen=True)
class PublicationVerdict:
    """Whether the qualified draft may be published."""

    eligible: bool
    blockers: tuple[str, ...] = field(default=())


def _resolver_lock_state(root: Path) -> tuple[str, bool]:
    import json

    policy = json.loads((root / "config/dependency_policy.json").read_text(encoding="utf-8"))
    resolver = policy.get("resolver_lock", {})
    state = str(resolver.get("state", "UNKNOWN"))
    verification = resolver.get("verification") or {}
    verified = bool(
        state == "READY"
        and verification.get("lock_sha256")
        and verification.get("uv_version")
        and verification.get("verification_command")
    )
    return state, verified


def evaluate_pre_admission_release_gate(root: Path) -> PreAdmissionVerdict:
    """Evaluate only the prerequisites satisfiable before the duration ladder."""

    blockers: list[str] = []
    try:
        gate, _ = evaluate_supply_chain(root, release_mode=True)
        supply_chain_state = gate.state.value
    except Exception as error:
        return PreAdmissionVerdict(
            state=PreAdmissionState.ERROR,
            blockers=(f"supply-chain evaluation failed: {error}",),
        )
    if supply_chain_state != "PASS":
        blockers.append("release supply-chain evidence is incomplete")

    resolver_state, resolver_verified = _resolver_lock_state(root)
    if not resolver_verified:
        blockers.append(f"resolver lock is not verified READY (state={resolver_state})")

    return PreAdmissionVerdict(
        state=PreAdmissionState.PASS if not blockers else PreAdmissionState.FAIL,
        blockers=tuple(blockers),
        supply_chain_state=supply_chain_state,
        resolver_lock_state=resolver_state,
    )


def evaluate_final_publication_gate(
    root: Path,
    *,
    duration_evidence: dict[str, bool],
    completion_gate_complete: bool,
    published_bytes_verified: bool,
) -> PublicationVerdict:
    """Fail-closed publication gate; never satisfied by pre-admission alone."""

    blockers: list[str] = []
    for stage in REQUIRED_DURATION_STAGES:
        if not duration_evidence.get(stage, False):
            blockers.append(f"{stage} duration evidence is missing or invalid")

    pre_admission = evaluate_pre_admission_release_gate(root)
    if pre_admission.state is not PreAdmissionState.PASS:
        blockers.extend(pre_admission.blockers)

    if not completion_gate_complete:
        blockers.append(SELF_CERTIFICATION_BOUNDARY_BLOCKER)
    if not published_bytes_verified:
        blockers.append("published-byte verification has not been performed")

    return PublicationVerdict(eligible=not blockers, blockers=tuple(blockers))
