from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from project_pipeline.domain.security import (
    AuthorityCapability,
    CapabilityGrant,
    SecretCapabilityReference,
    SecretLease,
    security_identifier,
)


class SecretBackendPort(Protocol):
    backend_name: str

    def resolve(self, reference: SecretCapabilityReference) -> str: ...


@dataclass(slots=True)
class EphemeralSecret:
    """Runtime-only secret material. Its repr and structured metadata never expose plaintext."""

    value: str = field(repr=False)
    lease: SecretLease

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.value.encode("utf-8")).hexdigest()

    def metadata(self) -> dict[str, object]:
        return {
            "lease_id": self.lease.lease_id,
            "secret_ref_id": self.lease.secret_ref_id,
            "fingerprint": self.fingerprint,
            "plaintext_persisted": False,
        }


class SecretsBroker:
    """Issues scoped secret leases and materializes plaintext only on explicit runtime demand."""

    def __init__(
        self, *, backends: dict[str, SecretBackendPort], max_lease_seconds: int = 900
    ) -> None:
        self.backends = dict(backends)
        self.max_lease_seconds = max_lease_seconds
        self.references: dict[str, SecretCapabilityReference] = {}
        self.leases: dict[str, SecretLease] = {}

    def register_reference(self, reference: SecretCapabilityReference) -> None:
        existing = self.references.get(reference.secret_ref_id)
        if existing is not None and existing != reference:
            raise ValueError("secret reference id collision")
        self.references[reference.secret_ref_id] = reference

    @staticmethod
    def _target_allowed(reference: SecretCapabilityReference, target: str) -> bool:
        return any(
            target == prefix or target.startswith(prefix.rstrip("/") + "/")
            for prefix in reference.allowed_target_prefixes
        )

    def issue_lease(
        self,
        *,
        secret_ref_id: str,
        identity_id: str,
        project_id: str,
        target: str,
        operation: str,
        issued_by: str,
        grant: CapabilityGrant,
        ttl_seconds: int = 300,
        now: datetime | None = None,
    ) -> SecretLease:
        when = now or datetime.now(UTC)
        if (
            grant.identity_id != identity_id
            or grant.capability is not AuthorityCapability.ACCESS_SECRET
        ):
            raise PermissionError(
                "secret lease requires an ACCESS_SECRET grant for the requesting identity"
            )
        if not grant.active_at(when):
            raise PermissionError("secret capability grant is expired or revoked")
        if grant.project_id != project_id or grant.environment == "":
            raise PermissionError("secret capability grant project/environment scope is invalid")
        if grant.operation_class != operation:
            raise PermissionError("secret capability grant does not allow requested operation")
        if not (
            target == grant.target_prefix
            or target.startswith(grant.target_prefix.rstrip("/") + "/")
        ):
            raise PermissionError("secret capability grant does not allow requested target")
        reference = self.references.get(secret_ref_id)
        if reference is None:
            raise KeyError("unknown secret capability reference")
        if operation not in reference.allowed_operations or not self._target_allowed(
            reference, target
        ):
            raise PermissionError("secret reference does not allow requested operation/target")
        if ttl_seconds <= 0 or ttl_seconds > self.max_lease_seconds:
            raise ValueError("secret lease TTL exceeds configured maximum")
        lease = SecretLease(
            lease_id=security_identifier(
                "SLEASE",
                secret_ref_id,
                identity_id,
                project_id,
                target,
                operation,
                when.isoformat(),
            ),
            secret_ref_id=secret_ref_id,
            identity_id=identity_id,
            project_id=project_id,
            target=target,
            operation=operation,
            issued_by=issued_by,
            issued_at_utc=when,
            expires_at_utc=when + timedelta(seconds=ttl_seconds),
        )
        self.leases[lease.lease_id] = lease
        return lease

    def revoke(self, lease_id: str, *, now: datetime | None = None) -> SecretLease:
        lease = self.leases[lease_id]
        when = now or datetime.now(UTC)
        updated = lease.model_copy(update={"revoked_at_utc": when})
        self.leases[lease_id] = updated
        return updated

    def materialize(
        self,
        lease_id: str,
        *,
        identity_id: str,
        target: str,
        operation: str,
        now: datetime | None = None,
    ) -> EphemeralSecret:
        when = now or datetime.now(UTC)
        lease = self.leases[lease_id]
        if not lease.active_at(when):
            raise PermissionError("secret lease is expired or revoked")
        if (lease.identity_id, lease.target, lease.operation) != (identity_id, target, operation):
            raise PermissionError("secret lease scope mismatch")
        reference = self.references[lease.secret_ref_id]
        backend = self.backends.get(reference.backend.value)
        if backend is None:
            raise RuntimeError(f"secret backend is unavailable: {reference.backend.value}")
        value = backend.resolve(reference)
        if not value:
            raise RuntimeError("secret backend returned empty material")
        updated = lease.model_copy(
            update={"materialization_count": lease.materialization_count + 1}
        )
        self.leases[lease_id] = updated
        return EphemeralSecret(value=value, lease=updated)
