from __future__ import annotations

import sqlite3
from pathlib import Path
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

    def __exit__(self, exc_type, exc, tb) -> None:
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

    def save_identity(self, value: SecurityIdentity) -> None:
        self._save(
            "security_identities",
            "identity_id",
            value.identity_id,
            value.model_dump_json(),
            extras=(("kind", value.kind.value), ("state", value.state.value)),
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

    def save_approval(self, value: ApprovalRecord) -> None:
        self._save(
            "security_approvals",
            "approval_id",
            value.approval_id,
            value.model_dump_json(),
            extras=(("action_id", value.action_id), ("decision", value.decision.value)),
        )

    def save_policy_decision(self, value: PolicyDecision) -> None:
        self._save(
            "security_policy_decisions",
            "decision_id",
            value.decision_id,
            value.model_dump_json(),
            extras=(("action_id", value.action_id), ("disposition", value.disposition.value)),
        )

    def save_egress_decision(self, value: EgressDecision) -> None:
        self._save(
            "security_egress_decisions",
            "decision_id",
            value.decision_id,
            value.model_dump_json(),
            extras=(("request_id", value.request_id), ("disposition", value.disposition.value)),
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

    def save_sbom(self, value: SoftwareBillOfMaterials) -> None:
        self._save(
            "security_sboms",
            "sbom_id",
            value.sbom_id,
            value.model_dump_json(),
            extras=(("project_id", value.project_id),),
        )

    def save_supply_chain_gate(self, project_id: str, value: SupplyChainGateResult) -> None:
        self._save(
            "security_supply_chain_gates",
            "gate_id",
            value.gate_id,
            value.model_dump_json(),
            extras=(("project_id", project_id), ("state", value.state.value)),
        )

    def save_root_of_trust(self, value: RootOfTrust) -> None:
        self._save(
            "security_root_trust",
            "root_id",
            value.root_id,
            value.model_dump_json(),
            extras=(("bootstrap_identity_id", value.bootstrap_identity_id),),
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
