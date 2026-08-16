from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from project_pipeline.domain.security import (
    ApprovalDecision,
    ApprovalRecord,
    AuthorityCapability,
    CapabilityGrant,
    IdentityState,
    RoleDefinition,
    SecurityIdentity,
    security_identifier,
)

_RISK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def default_roles() -> tuple[RoleDefinition, ...]:
    return (
        RoleDefinition(
            role_id=security_identifier("ROLE", "observer"),
            name="observer",
            capabilities=(AuthorityCapability.READ,),
            max_risk="CRITICAL",
        ),
        RoleDefinition(
            role_id=security_identifier("ROLE", "worker"),
            name="worker",
            capabilities=(AuthorityCapability.READ, AuthorityCapability.PROPOSE),
            max_risk="HIGH",
        ),
        RoleDefinition(
            role_id=security_identifier("ROLE", "operator"),
            name="operator",
            capabilities=(
                AuthorityCapability.READ,
                AuthorityCapability.PROPOSE,
                AuthorityCapability.APPROVE,
                AuthorityCapability.MUTATE,
                AuthorityCapability.MERGE,
                AuthorityCapability.SPEND,
                AuthorityCapability.EXTERNAL_MODEL,
                AuthorityCapability.ACCESS_SECRET,
            ),
            max_risk="HIGH",
        ),
        RoleDefinition(
            role_id=security_identifier("ROLE", "security-admin"),
            name="security-admin",
            capabilities=(
                AuthorityCapability.READ,
                AuthorityCapability.APPROVE,
                AuthorityCapability.MUTATE,
                AuthorityCapability.ACCESS_SECRET,
                AuthorityCapability.MODIFY_POLICY,
                AuthorityCapability.MODIFY_INSTRUCTIONS,
                AuthorityCapability.DEPLOY,
            ),
            max_risk="CRITICAL",
        ),
        RoleDefinition(
            role_id=security_identifier("ROLE", "completion-authority"),
            name="completion-authority",
            capabilities=(
                AuthorityCapability.READ,
                AuthorityCapability.APPROVE,
                AuthorityCapability.COMPLETE_PROJECT,
            ),
            max_risk="CRITICAL",
        ),
        RoleDefinition(
            role_id=security_identifier("ROLE", "emergency-operator"),
            name="emergency-operator",
            capabilities=(
                AuthorityCapability.READ,
                AuthorityCapability.APPROVE,
                AuthorityCapability.EMERGENCY,
            ),
            max_risk="CRITICAL",
            emergency=True,
        ),
    )


class IdentityAuthority:
    """In-process deterministic identity and least-privilege authority evaluator."""

    def __init__(
        self,
        *,
        identities: Iterable[SecurityIdentity] = (),
        roles: Iterable[RoleDefinition] | None = None,
        grants: Iterable[CapabilityGrant] = (),
    ) -> None:
        role_values = tuple(default_roles() if roles is None else roles)
        self.identities = {item.identity_id: item for item in identities}
        self.roles = {item.role_id: item for item in role_values}
        self.grants = {item.grant_id: item for item in grants}

    def register_identity(self, identity: SecurityIdentity) -> None:
        existing = self.identities.get(identity.identity_id)
        if existing is not None and existing != identity:
            raise ValueError("security identity id collision")
        self.identities[identity.identity_id] = identity

    def register_role(self, role: RoleDefinition) -> None:
        existing = self.roles.get(role.role_id)
        if existing is not None and existing != role:
            raise ValueError("role id collision")
        self.roles[role.role_id] = role

    def add_grant(self, grant: CapabilityGrant) -> None:
        existing = self.grants.get(grant.grant_id)
        if existing is not None and existing != grant:
            raise ValueError("capability grant id collision")
        if grant.identity_id not in self.identities:
            raise ValueError("capability grant identity is unknown")
        self.grants[grant.grant_id] = grant

    @staticmethod
    def _target_allowed(prefixes: tuple[str, ...], target: str) -> bool:
        return not prefixes or any(
            target == prefix or target.startswith(prefix.rstrip("/") + "/") for prefix in prefixes
        )

    def authorize(
        self,
        identity_id: str,
        capability: AuthorityCapability,
        *,
        project_id: str,
        target: str,
        environment: str,
        operation: str,
        risk: str = "MEDIUM",
        at: datetime | None = None,
    ) -> bool:
        identity = self.identities.get(identity_id)
        if identity is None or identity.state is not IdentityState.ACTIVE:
            return False
        if identity.project_ids and project_id not in identity.project_ids:
            return False
        if identity.environment_scopes and environment not in identity.environment_scopes:
            return False
        for role_id in identity.role_ids:
            role = self.roles.get(role_id)
            if role is None or capability not in role.capabilities:
                continue
            if _RISK[risk] > _RISK[role.max_risk]:
                continue
            if role.allowed_environments and environment not in role.allowed_environments:
                continue
            if self._target_allowed(role.allowed_target_prefixes, target):
                return True
        when = at or datetime.now(UTC)
        for grant in self.grants.values():
            if (
                grant.identity_id == identity_id
                and grant.capability is capability
                and grant.project_id == project_id
                and grant.environment == environment
                and grant.operation_class == operation
                and grant.active_at(when)
                and self._target_allowed((grant.target_prefix,), target)
            ):
                return True
        return False

    def validate_approval(
        self,
        approval: ApprovalRecord,
        *,
        project_id: str,
        target: str,
        environment: str,
        risk: str,
    ) -> bool:
        if approval.decision is not ApprovalDecision.APPROVED:
            return False
        return self.authorize(
            approval.approver_identity_id,
            AuthorityCapability.APPROVE,
            project_id=project_id,
            target=target,
            environment=environment,
            operation=approval.capability.value,
            risk=risk,
            at=approval.decided_at_utc,
        )
