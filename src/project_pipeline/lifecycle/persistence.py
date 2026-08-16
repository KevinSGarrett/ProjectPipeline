from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from project_pipeline.persistence.migrations import SQLiteMigrationRunner


class LifecycleStore:
    def __init__(self, path: Path, root: Path) -> None:
        self.path = path
        self.root = root
        self.db: sqlite3.Connection | None = None

    def __enter__(self) -> LifecycleStore:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        SQLiteMigrationRunner(self.db, self.root).apply_all()
        return self

    def __exit__(self, *_exc: object) -> None:
        if self.db is not None:
            self.db.close()
            self.db = None

    def _conn(self) -> sqlite3.Connection:
        if self.db is None:
            raise RuntimeError("store is not open")
        return self.db

    def save_json(
        self,
        table: str,
        key_column: str,
        key: str,
        columns: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        allowed = {
            "lifecycle_portfolio_projects",
            "lifecycle_environments",
            "lifecycle_test_data_assets",
            "lifecycle_contract_evolutions",
            "lifecycle_qualifications",
            "lifecycle_project_closures",
        }
        if table not in allowed:
            raise ValueError("unsupported lifecycle table")
        data = {
            key_column: key,
            **columns,
            "payload_json": json.dumps(payload, sort_keys=True, default=str),
        }
        names = tuple(data)
        qs = ",".join("?" for _ in names)
        updates = ",".join(f"{n}=excluded.{n}" for n in names if n != key_column)
        self._conn().execute(
            f"INSERT INTO {table} ({','.join(names)}) VALUES ({qs}) ON CONFLICT({key_column}) DO UPDATE SET {updates}",
            tuple(data[n] for n in names),
        )
        self._conn().commit()

    def status(self) -> dict[str, int]:
        c = self._conn()
        result = {}
        for table in (
            "lifecycle_portfolio_projects",
            "lifecycle_environments",
            "lifecycle_test_data_assets",
            "lifecycle_contract_evolutions",
            "lifecycle_qualifications",
            "lifecycle_project_closures",
        ):
            result[table] = int(c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return result
