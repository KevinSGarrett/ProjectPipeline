from __future__ import annotations

from datetime import UTC, datetime, timedelta

from project_pipeline.domain.security import (
    AuthorityCapability,
    CapabilityGrant,
    DataClassification,
    EgressRequest,
    IdentityKind,
    SecurityIdentity,
    security_fingerprint,
    security_identifier,
)
from project_pipeline.security.identity import IdentityAuthority, default_roles
from project_pipeline.security.policy import SecurityPolicyEngine


def supported_security_scenarios() -> tuple[str, ...]:
    return ("least-privilege", "egress-secret-block", "independent-approval")


def simulate_security(scenario: str) -> dict[str, object]:
    if scenario not in supported_security_scenarios():
        raise ValueError(f"unsupported security scenario: {scenario}")
    authority = IdentityAuthority()
    [authority.register_role(r) for r in default_roles()]
    identity = SecurityIdentity(
        identity_id=security_identifier("IDENT", "sim-agent"),
        kind=IdentityKind.AGENT,
        display_name="Simulation agent",
        principal="sim://agent",
        project_ids=("PROJECT-PIPELINE",),
        environment_scopes=("local",),
        role_ids=(security_identifier("ROLE", "worker"),),
    )
    authority.register_identity(identity)
    if scenario == "least-privilege":
        return {
            "scenario": scenario,
            "read": authority.authorize(
                identity.identity_id,
                AuthorityCapability.READ,
                project_id="PROJECT-PIPELINE",
                target="repo:x",
                environment="local",
                operation="READ",
                risk="LOW",
            ),
            "deploy": authority.authorize(
                identity.identity_id,
                AuthorityCapability.DEPLOY,
                project_id="PROJECT-PIPELINE",
                target="prod",
                environment="local",
                operation="DEPLOY",
                risk="HIGH",
            ),
        }
    if scenario == "egress-secret-block":
        engine = SecurityPolicyEngine(
            authority,
            external_provider_allowlist=("provider:test",),
            external_destination_allowlist=("https://example.invalid",),
        )
        request = EgressRequest(
            request_id=security_identifier("EGRESS", "sim"),
            actor_identity_id=identity.identity_id,
            project_id="PROJECT-PIPELINE",
            destination="https://example.invalid",
            provider_id="provider:test",
            classification=DataClassification.SECRET,
            content_fingerprint=security_fingerprint("secret"),
            contains_secret=True,
        )
        decision = engine.evaluate_egress(request)
        return {
            "scenario": scenario,
            "disposition": decision.disposition.value,
            "reasons": decision.reasons,
        }
    now = datetime.now(UTC)
    grant = CapabilityGrant(
        grant_id=security_identifier("GRANT", "sim", "approve"),
        identity_id=identity.identity_id,
        capability=AuthorityCapability.APPROVE,
        project_id="PROJECT-PIPELINE",
        target_prefix="repo:",
        environment="local",
        operation_class="DEPLOY",
        issued_by="bootstrap",
        issued_at_utc=now,
        expires_at_utc=now + timedelta(minutes=5),
    )
    authority.add_grant(grant)
    return {
        "scenario": scenario,
        "self_approval_allowed": False,
        "grant_active": grant.active_at(now),
    }
