from datetime import UTC, datetime, timedelta

from project_pipeline.contracts import ActionIntent, ApprovalState, RiskLevel
from project_pipeline.domain.security import (
    ApprovalDecision,
    ApprovalRecord,
    AuthorityCapability,
    CapabilityGrant,
    DataClassification,
    EgressRequest,
    IdentityKind,
    IdentityState,
    PolicyDisposition,
    SecurityIdentity,
    security_fingerprint,
    security_identifier,
)
from project_pipeline.security.identity import IdentityAuthority
from project_pipeline.security.policy import SecurityPolicyEngine


def ident(name, role):
    return SecurityIdentity(
        identity_id=security_identifier("IDENT", name),
        kind=IdentityKind.HUMAN,
        display_name=name,
        principal=f"human:{name}",
        project_ids=("P",),
        environment_scopes=("prod",),
        role_ids=(security_identifier("ROLE", role),),
    )


def test_default_worker_can_read_but_not_deploy():
    a = IdentityAuthority(identities=(ident("w", "worker"),))
    i = ident("w", "worker")
    assert a.authorize(
        i.identity_id,
        AuthorityCapability.READ,
        project_id="P",
        target="repo:x",
        environment="prod",
        operation="READ",
        risk="LOW",
    )
    assert not a.authorize(
        i.identity_id,
        AuthorityCapability.DEPLOY,
        project_id="P",
        target="prod",
        environment="prod",
        operation="DEPLOY",
        risk="HIGH",
    )


def test_revoked_identity_denied():
    i = ident("w", "worker").model_copy(update={"state": IdentityState.REVOKED})
    a = IdentityAuthority(identities=(i,))
    assert not a.authorize(
        i.identity_id,
        AuthorityCapability.READ,
        project_id="P",
        target="x",
        environment="prod",
        operation="READ",
    )


def test_temporary_grant_is_scoped_and_expires():
    i = ident("w", "worker")
    a = IdentityAuthority(identities=(i,))
    now = datetime.now(UTC)
    g = CapabilityGrant(
        grant_id=security_identifier("GRANT", "w", "secret"),
        identity_id=i.identity_id,
        capability=AuthorityCapability.ACCESS_SECRET,
        project_id="P",
        target_prefix="repo:secrets",
        environment="prod",
        operation_class="secret.read",
        issued_by="human",
        issued_at_utc=now,
        expires_at_utc=now + timedelta(minutes=1),
    )
    a.add_grant(g)
    assert a.authorize(
        i.identity_id,
        AuthorityCapability.ACCESS_SECRET,
        project_id="P",
        target="repo:secrets/db",
        environment="prod",
        operation="secret.read",
        risk="MEDIUM",
        at=now,
    )
    assert not a.authorize(
        i.identity_id,
        AuthorityCapability.ACCESS_SECRET,
        project_id="P",
        target="repo:other",
        environment="prod",
        operation="secret.read",
        risk="MEDIUM",
        at=now,
    )
    assert not a.authorize(
        i.identity_id,
        AuthorityCapability.ACCESS_SECRET,
        project_id="P",
        target="repo:secrets/db",
        environment="prod",
        operation="secret.read",
        risk="MEDIUM",
        at=now + timedelta(minutes=2),
    )


def test_high_impact_action_requires_independent_approval():
    proposer = ident("op", "operator")
    approver = ident("sec", "security-admin")
    a = IdentityAuthority(identities=(proposer, approver))
    e = SecurityPolicyEngine(a)
    intent = ActionIntent(
        actor_id=proposer.identity_id,
        authority="security",
        target="repo:release",
        operation="spend",
        risk=RiskLevel.HIGH,
        idempotency_key="abcdefgh",
        approval_state=ApprovalState.REQUIRED,
        correlation_id="corr",
    )
    assert (
        e.evaluate_action(intent, project_id="P", environment="prod").disposition
        is PolicyDisposition.REQUIRE_APPROVAL
    )


def test_approved_high_impact_action_allowed():
    proposer = ident("op", "operator")
    approver = ident("sec", "security-admin")
    a = IdentityAuthority(identities=(proposer, approver))
    e = SecurityPolicyEngine(a)
    intent = ActionIntent(
        actor_id=proposer.identity_id,
        authority="security",
        target="repo:release",
        operation="spend",
        risk=RiskLevel.HIGH,
        idempotency_key="abcdefgh",
        approval_state=ApprovalState.APPROVED,
        correlation_id="corr",
    )
    ap = ApprovalRecord(
        approval_id=security_identifier("APPROVAL", "spend"),
        action_id=intent.action_id,
        proposer_identity_id=proposer.identity_id,
        approver_identity_id=approver.identity_id,
        capability=AuthorityCapability.SPEND,
        decision=ApprovalDecision.APPROVED,
        reason="approved independently",
        correlation_id="corr",
    )
    assert (
        e.evaluate_action(intent, project_id="P", environment="prod", approval=ap).disposition
        is PolicyDisposition.ALLOW
    )


def test_egress_secret_is_denied_and_untrusted_instruction_constrained():
    e = SecurityPolicyEngine(
        IdentityAuthority(),
        external_provider_allowlist=("p",),
        external_destination_allowlist=("https://x",),
    )
    secret = EgressRequest(
        request_id=security_identifier("EGRESS", "s"),
        actor_identity_id="a",
        project_id="P",
        destination="https://x",
        provider_id="p",
        classification=DataClassification.SECRET,
        content_fingerprint=security_fingerprint("x"),
        contains_secret=True,
    )
    assert e.evaluate_egress(secret).disposition is PolicyDisposition.DENY
    data = secret.model_copy(
        update={
            "request_id": security_identifier("EGRESS", "u"),
            "classification": DataClassification.INTERNAL,
            "contains_secret": False,
            "contains_untrusted_instructions": True,
        }
    )
    assert e.evaluate_egress(data).disposition is PolicyDisposition.CONSTRAIN


def test_instruction_origin_cannot_self_promote_authority():
    assert (
        SecurityPolicyEngine.instruction_authoritative(
            origin="browser", signed_or_trusted=False, requested_authority_change=True
        )[0]
        is False
    )
    assert (
        SecurityPolicyEngine.instruction_authoritative(
            origin="trusted_policy", signed_or_trusted=True, requested_authority_change=True
        )[0]
        is False
    )
