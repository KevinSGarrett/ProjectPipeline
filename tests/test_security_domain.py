from datetime import UTC, datetime

import pytest

from project_pipeline.domain.security import (
    ApprovalDecision,
    ApprovalRecord,
    AuthorityCapability,
    CapabilityGrant,
    IdentityKind,
    RoleDefinition,
    RootOfTrust,
    SecretBackendKind,
    SecretCapabilityReference,
    security_identifier,
)


def test_security_identifier_stable_and_strict():
    assert security_identifier("IDENT", "a") == security_identifier("IDENT", "a")
    with pytest.raises(ValueError):
        security_identifier("IDENT", "")


def test_identity_kinds_are_distinct():
    assert {x.value for x in IdentityKind} == {"HUMAN", "AGENT", "SERVICE", "ADAPTER"}


def test_role_requires_capability():
    with pytest.raises(ValueError):
        RoleDefinition(role_id=security_identifier("ROLE", "empty"), name="empty", capabilities=())


def test_emergency_role_requires_emergency_capability():
    with pytest.raises(ValueError):
        RoleDefinition(
            role_id=security_identifier("ROLE", "bad"),
            name="bad",
            capabilities=(AuthorityCapability.READ,),
            emergency=True,
        )


def test_grant_requires_future_expiry():
    now = datetime.now(UTC)
    with pytest.raises(ValueError):
        CapabilityGrant(
            grant_id=security_identifier("GRANT", "bad"),
            identity_id="x",
            capability=AuthorityCapability.READ,
            project_id="p",
            target_prefix="x",
            environment="e",
            operation_class="READ",
            issued_by="x",
            issued_at_utc=now,
            expires_at_utc=now,
        )


def test_approval_cannot_self_approve():
    with pytest.raises(ValueError):
        ApprovalRecord(
            approval_id=security_identifier("APPROVAL", "x"),
            action_id="a",
            proposer_identity_id="same",
            approver_identity_id="same",
            capability=AuthorityCapability.DEPLOY,
            decision=ApprovalDecision.APPROVED,
            reason="not independent",
            correlation_id="c",
        )


def test_root_of_trust_requires_references():
    with pytest.raises(ValueError):
        RootOfTrust(
            root_id=security_identifier("ROOTTRUST", "x"),
            bootstrap_identity_id="i",
            trusted_policy_paths=(),
            trusted_key_references=(),
            recovery_procedure="r",
            rotation_procedure="r",
            revocation_procedure="r",
        )


def test_secret_reference_accepts_age_backend():
    value = SecretCapabilityReference(
        secret_ref_id=security_identifier("SREF", "age"),
        logical_name="age",
        backend=SecretBackendKind.AGE,
        reference="age-file://secret.age",
        allowed_operations=("read",),
        allowed_target_prefixes=("repo:",),
    )
    assert value.backend is SecretBackendKind.AGE
