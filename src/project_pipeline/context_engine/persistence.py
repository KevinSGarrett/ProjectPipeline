from __future__ import annotations

import sqlite3
from pathlib import Path

from project_pipeline.domain.context import ContextPack, ContextReceipt, DelegationEnvelope
from project_pipeline.persistence.migrations import SQLiteMigrationRunner


class ContextStore:
    def __init__(self, database: Path | str, root: Path):
        self.root = root.resolve()
        self.database = database
        self.db = sqlite3.connect(str(database))
        self.db.row_factory = sqlite3.Row

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.db.close()

    def initialize(self):
        SQLiteMigrationRunner(self.db, self.root).apply_all()

    def save_delegation(self, item: DelegationEnvelope):
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO context_delegations(delegation_id,payload_json) VALUES(?,?)",
                (item.delegation_id, item.model_dump_json()),
            )
            existing = self.db.execute(
                "SELECT payload_json FROM context_delegations WHERE delegation_id=?",
                (item.delegation_id,),
            ).fetchone()[0]
            if existing != item.model_dump_json():
                raise ValueError("delegation identity collision")

    def save_pack(self, item: ContextPack):
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO context_packs(pack_id,delegation_id,content_sha256,payload_json,created_at_utc) VALUES(?,?,?,?,?)",
                (
                    item.pack_id,
                    item.delegation_id,
                    item.content_sha256,
                    item.model_dump_json(),
                    item.generated_at_utc.isoformat(),
                ),
            )
            existing = self.db.execute(
                "SELECT payload_json FROM context_packs WHERE pack_id=?", (item.pack_id,)
            ).fetchone()[0]
            if existing != item.model_dump_json():
                raise ValueError("immutable context pack identity collision")

    def save_receipt(self, item: ContextReceipt):
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO context_receipts(receipt_id,pack_id,status,payload_json,created_at_utc) VALUES(?,?,?,?,?)",
                (
                    item.receipt_id,
                    item.pack_id,
                    item.status.value,
                    item.model_dump_json(),
                    item.consumed_at_utc.isoformat(),
                ),
            )

    def get_pack(self, pack_id: str) -> ContextPack | None:
        row = self.db.execute(
            "SELECT payload_json FROM context_packs WHERE pack_id=?", (pack_id,)
        ).fetchone()
        return ContextPack.model_validate_json(row[0]) if row else None

    def get_receipt(self, receipt_id: str) -> ContextReceipt | None:
        row = self.db.execute(
            "SELECT payload_json FROM context_receipts WHERE receipt_id=?", (receipt_id,)
        ).fetchone()
        return ContextReceipt.model_validate_json(row[0]) if row else None

    def status(self) -> dict[str, int | str]:
        def c(t):
            return int(self.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])

        return {
            "schema_version": "1.0.0",
            "delegations": c("context_delegations"),
            "packs": c("context_packs"),
            "receipts": c("context_receipts"),
        }
