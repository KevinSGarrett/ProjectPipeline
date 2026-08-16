from __future__ import annotations

from collections.abc import Iterable

from project_pipeline.domain.resilience import (
    FailoverDecision,
    FailureDomain,
    MachineHealth,
    MachineRole,
    OperatingMode,
    OperatingModeDecision,
    resilience_identifier,
)

_CRITICAL_STOP = {FailureDomain.DATABASE}
_DEGRADED = {
    FailureDomain.PROVIDER,
    FailureDomain.API,
    FailureDomain.EXTERNAL_SYSTEM,
    FailureDomain.QUOTA,
    FailureDomain.BUDGET,
    FailureDomain.GPU,
    FailureDomain.CLOUD,
}


def decide_operating_mode(
    failures: Iterable[FailureDomain],
    *,
    canonical_state_available: bool = True,
    emergency_stop: bool = False,
) -> OperatingModeDecision:
    domains = tuple(sorted(set(failures), key=lambda value: value.value))
    if emergency_stop:
        mode = OperatingMode.EMERGENCY_STOP
        allowed = ("read_state", "export_evidence", "notify")
        blocked = ("mutate", "execute", "deploy", "spend")
        reasons = ("emergency stop was explicitly requested",)
    elif not canonical_state_available or any(item in _CRITICAL_STOP for item in domains):
        mode = OperatingMode.RECOVERY
        allowed = ("read_state", "restore", "reconcile", "notify")
        blocked = ("commit_authority", "external_mutation", "deploy")
        reasons = (
            "canonical state is unavailable or unsafe; recovery and reconciliation are required",
        )
    elif not domains:
        mode = OperatingMode.FULL
        allowed = ("all_qualified_capabilities",)
        blocked = ()
        reasons = ("no active failure domains",)
    elif FailureDomain.NETWORK in domains or FailureDomain.CLOUD in domains:
        mode = OperatingMode.LOCAL_FIRST
        allowed = (
            "deterministic_control",
            "local_workers",
            "local_models",
            "local_repository",
            "local_evidence",
        )
        blocked = ("unavailable_remote_capabilities",)
        reasons = (
            "remote connectivity or cloud dependency is unavailable; preserve local deterministic work",
        )
    else:
        mode = OperatingMode.DEGRADED
        allowed = ("deterministic_control", "unaffected_capabilities", "local_work")
        blocked = tuple(f"failed:{item.value.lower()}" for item in domains)
        reasons = (
            "one or more non-canonical dependencies are unavailable; continue unaffected work",
        )
    return OperatingModeDecision(
        decision_id=resilience_identifier(
            "MODE", mode.value, *[item.value for item in domains] or ["NONE"]
        ),
        mode=mode,
        failure_domains=domains,
        allowed_capabilities=allowed,
        blocked_capabilities=blocked,
        reasons=reasons,
    )


class RecoveryDirector:
    """Deterministic recovery authority. Advisory/model runtimes never issue fencing tokens."""

    def decide_failover(
        self,
        active: MachineHealth,
        candidate: MachineHealth,
        *,
        witness_confirmed: bool,
        active_lease_expired: bool,
    ) -> FailoverDecision:
        reasons: list[str] = []
        eligible = True
        if active.healthy:
            eligible = False
            reasons.append("active control machine is still healthy")
        if (
            MachineRole.STANDBY_CONTROL not in candidate.roles
            and MachineRole.RECOVERY not in candidate.roles
        ):
            eligible = False
            reasons.append("candidate lacks standby or recovery control role")
        if not candidate.healthy:
            eligible = False
            reasons.append("candidate is unhealthy")
        if not active_lease_expired:
            eligible = False
            reasons.append("active authority lease is not expired or fenced")
        if not witness_confirmed:
            eligible = False
            reasons.append("external or independent witness has not confirmed takeover")
        if eligible:
            reasons.append(
                "active authority is fenced and candidate is eligible for reconciled takeover"
            )
        token = max(active.fencing_token, candidate.fencing_token) + 1
        return FailoverDecision(
            decision_id=resilience_identifier(
                "FAILOVER",
                active.machine_id,
                candidate.machine_id,
                str(token),
                str(witness_confirmed),
                str(active_lease_expired),
            ),
            active_machine_id=active.machine_id,
            candidate_machine_id=candidate.machine_id,
            eligible=eligible,
            reasons=tuple(reasons),
            required_fencing_token=token,
            witness_required=True,
            witness_confirmed=witness_confirmed,
            reconcile_before_commit=True,
        )

    @staticmethod
    def provider_substitution(
        required_capabilities: Iterable[str], providers: Iterable[dict[str, object]]
    ) -> dict[str, object]:
        required = set(required_capabilities)
        candidates = []
        for provider in providers:
            caps = set(str(x) for x in provider.get("capabilities", ()))
            if provider.get("available") and required.issubset(caps):
                candidates.append(provider)
        candidates.sort(
            key=lambda item: (float(item.get("cost_score", 1.0)), str(item.get("provider_id", "")))
        )
        return {
            "required_capabilities": sorted(required),
            "selected_provider_id": candidates[0].get("provider_id") if candidates else None,
            "candidate_count": len(candidates),
            "task_semantics_preserved": True,
            "blocked": not candidates,
        }


def verify_human_repair(
    *,
    verification_results: dict[str, bool],
    stale_assumptions_invalidated: bool,
    reconciliation_complete: bool,
) -> dict[str, object]:
    failed = sorted(name for name, ok in verification_results.items() if not ok)
    verified = (
        bool(verification_results)
        and not failed
        and stale_assumptions_invalidated
        and reconciliation_complete
    )
    return {
        "verified": verified,
        "failed_checks": failed,
        "stale_assumptions_invalidated": stale_assumptions_invalidated,
        "reconciliation_complete": reconciliation_complete,
        "resume_eligible_work": verified,
    }
