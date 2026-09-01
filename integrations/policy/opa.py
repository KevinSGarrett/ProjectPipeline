"""ProjectPipeline-owned OPA/Conftest policy conformance surface.

OPA and Conftest are optional conformance backends. Canonical allow/deny
authority remains ``SecurityPolicyEngine`` / ``PolicyPort`` semantics owned by
ProjectPipeline. Upstream Rego never becomes governing policy authority.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_pipeline.ports import ActionContext, PolicyDecision
from project_pipeline.upstream_integrations.security import ConftestAdapter, OpaAdapter

POLICY_VERSION = "PP-OPA-CONFORMANCE-1.0.0"
DEFAULT_QUERY = "data.project_pipeline.security"


@dataclass(frozen=True, slots=True)
class ConformanceObservation:
    backend: str
    available: bool
    disposition: str
    reasons: tuple[str, ...]
    evidence_sources: tuple[str, ...]
    raw: Mapping[str, Any]


def _decision(
    *,
    allowed: bool,
    decision_id: str,
    reasons: tuple[str, ...],
    required_approvals: tuple[str, ...] = (),
) -> PolicyDecision:
    return PolicyDecision(
        allowed=allowed,
        decision_id=decision_id,
        policy_version=POLICY_VERSION,
        reasons=reasons,
        required_approvals=required_approvals,
    )


def _confined_policy_dir(root: Path, policy_dir: Path | None) -> Path:
    root = root.resolve()
    candidate = (root / (policy_dir or Path("policies/security"))).resolve()
    if root not in candidate.parents and candidate != root:
        # allow policy dir equal to root/policies/security only when under root
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("policy directory escapes repository root") from exc
    if not candidate.is_dir():
        raise FileNotFoundError(f"policy directory missing: {candidate}")
    return candidate


class OpaConformancePolicyPort:
    """PolicyPort adapter that records OPA conformance; never overrides deny authority."""

    def __init__(
        self,
        *,
        repository_root: Path,
        policy_dir: Path | None = None,
        opa: OpaAdapter | None = None,
        conftest: ConftestAdapter | None = None,
        require_backend: bool = False,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.policy_dir = _confined_policy_dir(self.repository_root, policy_dir)
        self.opa = opa or OpaAdapter()
        self.conftest = conftest or ConftestAdapter()
        self.require_backend = require_backend
        self.last_observation: ConformanceObservation | None = None

    def evaluate(
        self, action: str, resource: Mapping[str, Any], context: ActionContext
    ) -> PolicyDecision:
        authorized = bool(resource.get("authorized", False))
        high_impact = bool(resource.get("high_impact", False))
        independent_approval = bool(resource.get("independent_approval", False))
        input_document = {
            "action": action,
            "authorized": authorized,
            "high_impact": high_impact,
            "independent_approval": independent_approval,
            "actor_id": context.actor_id,
            "correlation_id": context.correlation_id,
            "resource": dict(resource),
        }

        # Canonical ProjectPipeline decision first.
        if not authorized:
            decision = _decision(
                allowed=False,
                decision_id=f"POL-OPA-{context.idempotency_key}-DENY",
                reasons=("identity is not authorized for requested capability and scope",),
            )
        elif high_impact and not independent_approval:
            decision = _decision(
                allowed=False,
                decision_id=f"POL-OPA-{context.idempotency_key}-REQUIRE_APPROVAL",
                reasons=("high-impact action lacks independent approval",),
                required_approvals=("independent_approval",),
            )
        else:
            decision = _decision(
                allowed=True,
                decision_id=f"POL-OPA-{context.idempotency_key}-ALLOW",
                reasons=("canonical ProjectPipeline policy allows the action",),
            )

        observation = self._observe_opa(input_document)
        self.last_observation = observation
        if observation.available and observation.disposition == "DENY" and decision.allowed:
            # Conformance backend may only constrain further, never invent allow.
            return _decision(
                allowed=False,
                decision_id=f"POL-OPA-{context.idempotency_key}-CONFORM-DENY",
                reasons=decision.reasons + observation.reasons,
            )
        if self.require_backend and not observation.available:
            return _decision(
                allowed=False,
                decision_id=f"POL-OPA-{context.idempotency_key}-BACKEND-MISSING",
                reasons=("OPA backend required but unavailable",),
            )
        return decision

    def plan_conftest(self, target: Path) -> object:
        return self.conftest.plan_test(
            self.repository_root,
            target=target,
            policy_dir=self.policy_dir.relative_to(self.repository_root),
        )

    def _observe_opa(self, input_document: Mapping[str, Any]) -> ConformanceObservation:
        if not self.opa.available():
            return ConformanceObservation(
                backend="opa",
                available=False,
                disposition="UNAVAILABLE",
                reasons=("opa executable unavailable; canonical policy remains authoritative",),
                evidence_sources=(),
                raw={},
            )
        plan = self.opa.plan_eval(
            self.repository_root,
            policy_dir=self.policy_dir.relative_to(self.repository_root),
            query=DEFAULT_QUERY,
            input_document=input_document,
        )
        # Dry-plan only by default: executing OPA requires an installed binary and
        # is optional. Tests inject a fake adapter when execution must be proven.
        execute = getattr(self.opa, "execute", None)
        if execute is None or not getattr(self.opa, "_execute_enabled", False):
            return ConformanceObservation(
                backend="opa",
                available=True,
                disposition="PLANNED",
                reasons=("opa eval planned; canonical policy remains authoritative",),
                evidence_sources=tuple(plan.evidence_sources),
                raw={"argv": list(plan.argv), "cwd": plan.cwd},
            )
        outcome = execute(plan)
        raw: Mapping[str, Any]
        try:
            raw = json.loads(outcome.stdout or "{}")
        except json.JSONDecodeError:
            raw = {"stdout": outcome.stdout}
        deny_reasons = tuple(
            str(item)
            for item in (raw.get("deny") or raw.get("result") or [])
            if isinstance(item, (str, int, float))
        )
        allowed = bool(raw.get("allow", False)) if "allow" in raw else outcome.returncode == 0
        disposition = "ALLOW" if allowed and not deny_reasons else "DENY"
        return ConformanceObservation(
            backend="opa",
            available=True,
            disposition=disposition,
            reasons=deny_reasons
            or (
                ("opa conformance allow",)
                if disposition == "ALLOW"
                else ("opa conformance deny",)
            ),
            evidence_sources=tuple(plan.evidence_sources),
            raw=raw,
        )


def build_default_policy_port(repository_root: Path) -> OpaConformancePolicyPort:
    return OpaConformancePolicyPort(repository_root=repository_root)
