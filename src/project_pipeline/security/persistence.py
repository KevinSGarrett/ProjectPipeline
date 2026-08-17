from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import TypeVar

from project_pipeline.domain.security import (
    ApprovalRecord,
    CapabilityGrant,
    EgressDecision,
    PolicyDecision,
    RootOfTrust,
    SecretCapabilityReference,
    SecretLease,
    SecurityAuditEvent,
    SecurityIdentity,
    SoftwareBillOfMaterials,
    SupplyChainGateResult,
)
from project_pipeline.persistence.migrations import SQLiteMigrationRunner

T = TypeVar("T")


class SecurityStore:
    """Persistent metadata for identity, policy, secret leases, and supply-chain evidence.

    Plaintext secret material is deliberately not accepted by this store.
    """

    def __init__(self, database: Path | str, root: Path) -> None:
        self.database = database
        self.root = root.resolve()
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> SecurityStore:
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    @property
    def db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("security store is not open")
        return self.connection

    def initialize(self) -> None:
        SQLiteMigrationRunner(self.db, self.root).apply_all()

    def _save(
        self,
        table: str,
        key_col: str,
        key: str,
        payload: str,
        *,
        extras: tuple[tuple[str, object], ...] = (),
    ) -> None:
        cols = [key_col, *[name for name, _ in extras], "payload_json"]
        values = [key, *[value for _, value in extras], payload]
        marks = ",".join("?" for _ in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols[1:])
        with self.db:
            self.db.execute(
                f"INSERT INTO {table} ({','.join(cols)}) VALUES ({marks}) ON CONFLICT({key_col}) DO UPDATE SET {updates}",
                values,
            )

    def _bounded_limit(self, limit: int, *, maximum: int = 500) -> int:
        return max(1, min(int(limit), maximum))

    def _bounded_offset(self, offset: int) -> int:
        return max(0, int(offset))

    def _get_model(
        self, table: str, key_col: str, key: str, decoder: Callable[[str], T]
    ) -> T | None:
        row = self.db.execute(
            f"SELECT payload_json FROM {table} WHERE {key_col} = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return decoder(str(row["payload_json"]))

    def _list_models(
        self,
        table: str,
        decoder: Callable[[str], T],
        *,
        order_col: str,
        limit: int,
        offset: int = 0,
    ) -> tuple[T, ...]:
        bounded = self._bounded_limit(limit)
        bounded_offset = self._bounded_offset(offset)
        rows = self.db.execute(
            f"SELECT payload_json FROM {table} ORDER BY {order_col} LIMIT ? OFFSET ?",
            (bounded, bounded_offset),
        ).fetchall()
        return tuple(decoder(str(row["payload_json"])) for row in rows)

    def save_identity(self, value: SecurityIdentity) -> None:
        self._save(
            "security_identities",
            "identity_id",
            value.identity_id,
            value.model_dump_json(),
            extras=(("kind", value.kind.value), ("state", value.state.value)),
        )

    def get_identity(self, identity_id: str) -> SecurityIdentity | None:
        return self._get_model(
            "security_identities",
            "identity_id",
            identity_id,
            SecurityIdentity.model_validate_json,
        )

    def list_identities(self, *, limit: int = 50, offset: int = 0) -> tuple[SecurityIdentity, ...]:
        return self._list_models(
            "security_identities",
            SecurityIdentity.model_validate_json,
            order_col="identity_id",
            limit=limit,
            offset=offset,
        )

    def save_grant(self, value: CapabilityGrant) -> None:
        self._save(
            "security_capability_grants",
            "grant_id",
            value.grant_id,
            value.model_dump_json(),
            extras=(
                ("identity_id", value.identity_id),
                ("capability", value.capability.value),
                ("expires_at_utc", value.expires_at_utc.isoformat()),
            ),
        )

    def get_grant(self, grant_id: str) -> CapabilityGrant | None:
        return self._get_model(
            "security_capability_grants",
            "grant_id",
            grant_id,
            CapabilityGrant.model_validate_json,
        )

    def list_grants(self, *, limit: int = 50, offset: int = 0) -> tuple[CapabilityGrant, ...]:
        return self._list_models(
            "security_capability_grants",
            CapabilityGrant.model_validate_json,
            order_col="grant_id",
            limit=limit,
            offset=offset,
        )

    def save_approval(self, value: ApprovalRecord) -> None:
        self._save(
            "security_approvals",
            "approval_id",
            value.approval_id,
            value.model_dump_json(),
            extras=(("action_id", value.action_id), ("decision", value.decision.value)),
        )

    def list_approvals(self, *, limit: int = 50, offset: int = 0) -> tuple[ApprovalRecord, ...]:
        return self._list_models(
            "security_approvals",
            ApprovalRecord.model_validate_json,
            order_col="approval_id",
            limit=limit,
            offset=offset,
        )

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        return self._get_model(
            "security_approvals",
            "approval_id",
            approval_id,
            ApprovalRecord.model_validate_json,
        )

    def save_policy_decision(self, value: PolicyDecision) -> None:
        self._save(
            "security_policy_decisions",
            "decision_id",
            value.decision_id,
            value.model_dump_json(),
            extras=(("action_id", value.action_id), ("disposition", value.disposition.value)),
        )

    def list_policy_decisions(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[PolicyDecision, ...]:
        return self._list_models(
            "security_policy_decisions",
            PolicyDecision.model_validate_json,
            order_col="decision_id",
            limit=limit,
            offset=offset,
        )

    def get_policy_decision(self, decision_id: str) -> PolicyDecision | None:
        return self._get_model(
            "security_policy_decisions",
            "decision_id",
            decision_id,
            PolicyDecision.model_validate_json,
        )

    def save_egress_decision(self, value: EgressDecision) -> None:
        self._save(
            "security_egress_decisions",
            "decision_id",
            value.decision_id,
            value.model_dump_json(),
            extras=(("request_id", value.request_id), ("disposition", value.disposition.value)),
        )

    def list_egress_decisions(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[EgressDecision, ...]:
        return self._list_models(
            "security_egress_decisions",
            EgressDecision.model_validate_json,
            order_col="decision_id",
            limit=limit,
            offset=offset,
        )

    def get_egress_decision(self, decision_id: str) -> EgressDecision | None:
        return self._get_model(
            "security_egress_decisions",
            "decision_id",
            decision_id,
            EgressDecision.model_validate_json,
        )

    def save_secret_reference(self, value: SecretCapabilityReference) -> None:
        # References may contain secret locations, never secret plaintext.
        self._save(
            "security_secret_references",
            "secret_ref_id",
            value.secret_ref_id,
            value.model_dump_json(),
            extras=(("backend", value.backend.value),),
        )

    def get_secret_reference(self, secret_ref_id: str) -> SecretCapabilityReference | None:
        return self._get_model(
            "security_secret_references",
            "secret_ref_id",
            secret_ref_id,
            SecretCapabilityReference.model_validate_json,
        )

    def list_secret_references(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[SecretCapabilityReference, ...]:
        return self._list_models(
            "security_secret_references",
            SecretCapabilityReference.model_validate_json,
            order_col="secret_ref_id",
            limit=limit,
            offset=offset,
        )

    def save_secret_lease(self, value: SecretLease) -> None:
        self._save(
            "security_secret_leases",
            "lease_id",
            value.lease_id,
            value.model_dump_json(),
            extras=(
                ("secret_ref_id", value.secret_ref_id),
                ("identity_id", value.identity_id),
                ("expires_at_utc", value.expires_at_utc.isoformat()),
            ),
        )

    def list_secret_leases(self, *, limit: int = 50, offset: int = 0) -> tuple[SecretLease, ...]:
        return self._list_models(
            "security_secret_leases",
            SecretLease.model_validate_json,
            order_col="lease_id",
            limit=limit,
            offset=offset,
        )

    def get_secret_lease(self, lease_id: str) -> SecretLease | None:
        return self._get_model(
            "security_secret_leases",
            "lease_id",
            lease_id,
            SecretLease.model_validate_json,
        )

    def save_audit_event(self, value: SecurityAuditEvent) -> None:
        # Audit history is insert-only. PPDB-0019 also blocks direct UPDATE/DELETE at the
        # database boundary so application bugs cannot silently rewrite historical events.
        with self.db:
            self.db.execute(
                "INSERT INTO security_audit_events (audit_id,event_type,occurred_at_utc,payload_json) VALUES (?,?,?,?)",
                (
                    value.audit_id,
                    value.event_type,
                    value.occurred_at_utc.isoformat(),
                    value.model_dump_json(),
                ),
            )

    def list_audit_events(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[SecurityAuditEvent, ...]:
        return self._list_models(
            "security_audit_events",
            SecurityAuditEvent.model_validate_json,
            order_col="occurred_at_utc",
            limit=limit,
            offset=offset,
        )

    def get_audit_event(self, audit_id: str) -> SecurityAuditEvent | None:
        return self._get_model(
            "security_audit_events",
            "audit_id",
            audit_id,
            SecurityAuditEvent.model_validate_json,
        )

    def save_sbom(self, value: SoftwareBillOfMaterials) -> None:
        self._save(
            "security_sboms",
            "sbom_id",
            value.sbom_id,
            value.model_dump_json(),
            extras=(("project_id", value.project_id),),
        )

    def list_sboms(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[SoftwareBillOfMaterials, ...]:
        return self._list_models(
            "security_sboms",
            SoftwareBillOfMaterials.model_validate_json,
            order_col="sbom_id",
            limit=limit,
            offset=offset,
        )

    def get_sbom(self, sbom_id: str) -> SoftwareBillOfMaterials | None:
        return self._get_model(
            "security_sboms",
            "sbom_id",
            sbom_id,
            SoftwareBillOfMaterials.model_validate_json,
        )

    def save_supply_chain_gate(self, project_id: str, value: SupplyChainGateResult) -> None:
        self._save(
            "security_supply_chain_gates",
            "gate_id",
            value.gate_id,
            value.model_dump_json(),
            extras=(("project_id", project_id), ("state", value.state.value)),
        )

    def list_supply_chain_gates(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[SupplyChainGateResult, ...]:
        return self._list_models(
            "security_supply_chain_gates",
            SupplyChainGateResult.model_validate_json,
            order_col="gate_id",
            limit=limit,
            offset=offset,
        )

    def get_supply_chain_gate(self, gate_id: str) -> SupplyChainGateResult | None:
        return self._get_model(
            "security_supply_chain_gates",
            "gate_id",
            gate_id,
            SupplyChainGateResult.model_validate_json,
        )

    def save_root_of_trust(self, value: RootOfTrust) -> None:
        self._save(
            "security_root_trust",
            "root_id",
            value.root_id,
            value.model_dump_json(),
            extras=(("bootstrap_identity_id", value.bootstrap_identity_id),),
        )

    def get_root_of_trust(self, root_id: str) -> RootOfTrust | None:
        return self._get_model(
            "security_root_trust",
            "root_id",
            root_id,
            RootOfTrust.model_validate_json,
        )

    def list_root_of_trust(self, *, limit: int = 50, offset: int = 0) -> tuple[RootOfTrust, ...]:
        return self._list_models(
            "security_root_trust",
            RootOfTrust.model_validate_json,
            order_col="root_id",
            limit=limit,
            offset=offset,
        )

    def status(self) -> dict[str, int]:
        tables = (
            "security_identities",
            "security_capability_grants",
            "security_approvals",
            "security_policy_decisions",
            "security_egress_decisions",
            "security_secret_references",
            "security_secret_leases",
            "security_audit_events",
            "security_sboms",
            "security_supply_chain_gates",
            "security_root_trust",
        )
        return {
            table: int(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }
