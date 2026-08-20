from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from project_pipeline.cli import main
from project_pipeline.persistence.migrations import SQLiteMigrationRunner
from project_pipeline.retrieval import (
    EXACT_FALLBACK_ENGINE,
    RetrievalService,
    SemanticEngineStatus,
    run_retrieval_benchmark,
)
from project_pipeline.retrieval.postgres import probe_pgvector

ROOT = Path(__file__).resolve().parents[1]


def test_ppdb_0025_applies_retrieval_tables(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "state.db")
    runner = SQLiteMigrationRunner(connection, ROOT)
    status = runner.apply_all()
    assert status.latest_applied == "PPDB-0025"
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='retrieval_chunks'"
    ).fetchone()
    after = runner.rollback_last()
    assert after.latest_applied == "PPDB-0024"
    assert (
        connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='retrieval_chunks'"
        ).fetchone()
        is None
    )
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='evidence_observations'"
    ).fetchone()
    connection.close()


def test_exact_source_address_and_lexical_fallback(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "state.db")
    SQLiteMigrationRunner(connection, ROOT).apply_all()
    service = RetrievalService(connection)
    service.upsert_chunk(
        chunk_id="CHK-A",
        source_reference="SRC-011:L000601-L000652",
        start_line=601,
        end_line=652,
        text="PostgreSQL plus pgvector is the default semantic retrieval boundary.",
    )
    service.upsert_chunk(
        chunk_id="CHK-B",
        source_reference="SRC-009:L000075-L000087",
        start_line=75,
        end_line=87,
        text="Optional profile services remain disabled unless required.",
    )
    exact = service.exact_lookup("SRC-011:L000601-L000652")
    assert [item.chunk_id for item in exact] == ["CHK-A"]
    assert exact[0].method == "exact_source_address"
    lexical = service.exact_lookup("profile services remain disabled")
    assert lexical[0].chunk_id == "CHK-B"
    assert lexical[0].method == "exact_lexical_fallback"
    assert service.semantic_status() is SemanticEngineStatus.UNAVAILABLE_IN_EXECUTION_ENVIRONMENT
    assert probe_pgvector() is SemanticEngineStatus.UNAVAILABLE_IN_EXECUTION_ENVIRONMENT
    connection.close()


def test_backup_restore_and_benchmark_recall(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("PROJECT_PIPELINE_PGVECTOR_DSN", raising=False)
    db = tmp_path / "retrieval.sqlite"
    report = run_retrieval_benchmark(ROOT, database=db, output_dir=tmp_path)
    assert report["observed_engine"] == EXACT_FALLBACK_ENGINE
    assert report["default_engine"] == "postgresql_pgvector"
    assert report["exact_recall_at_1"] == 1.0
    assert report["semantic_status"] == "UNAVAILABLE_IN_EXECUTION_ENVIRONMENT"
    assert report["backup"]["verified"] is True
    assert report["backup"]["restore_verified"] is True
    assert report["standalone_vector_service"] == "DEFERRED_UNTIL_BENCHMARK_JUSTIFIES"
    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert latest["exact_recall_at_1"] == 1.0


def test_retrieval_cli_benchmark(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.delenv("PROJECT_PIPELINE_PGVECTOR_DSN", raising=False)
    db = tmp_path / "cli.sqlite"
    code = main(
        [
            "retrieval",
            "benchmark",
            "--root",
            str(ROOT),
            "--database",
            str(db),
            "--output-dir",
            str(tmp_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["exact_recall_at_1"] == 1.0
    assert payload["observed_engine"] == EXACT_FALLBACK_ENGINE


def test_benchmark_rerun_on_same_database_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("PROJECT_PIPELINE_PGVECTOR_DSN", raising=False)
    db = tmp_path / "idempotent.sqlite"
    first = run_retrieval_benchmark(ROOT, database=db, output_dir=tmp_path / "one")
    second = run_retrieval_benchmark(ROOT, database=db, output_dir=tmp_path / "two")
    assert first["exact_recall_at_1"] == 1.0
    assert second["exact_recall_at_1"] == 1.0
    assert first["backup"]["receipt_id"] == second["backup"]["receipt_id"]


def test_semantic_status_ignores_unset_or_dead_dsn(monkeypatch) -> None:
    monkeypatch.delenv("PROJECT_PIPELINE_PGVECTOR_DSN", raising=False)
    connection = sqlite3.connect(":memory:")
    SQLiteMigrationRunner(connection, ROOT).apply_all()
    service = RetrievalService(connection)
    assert service.semantic_status() is SemanticEngineStatus.UNAVAILABLE_IN_EXECUTION_ENVIRONMENT
    monkeypatch.setenv("PROJECT_PIPELINE_PGVECTOR_DSN", "postgresql://127.0.0.1:1/missing")
    assert service.semantic_status() is SemanticEngineStatus.UNAVAILABLE_IN_EXECUTION_ENVIRONMENT
    connection.close()


def test_postgresql_retrieval_sql_enables_vector_and_indexes() -> None:
    up = (
        ROOT
        / "database/migrations/postgresql/PPDB-0025_retrieval_pgvector_and_exact_fallback.up.sql"
    ).read_text(encoding="utf-8")
    down = (
        ROOT
        / "database/migrations/postgresql/PPDB-0025_retrieval_pgvector_and_exact_fallback.down.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE EXTENSION IF NOT EXISTS vector" in up
    assert "embedding vector(8)" in up
    assert "USING ivfflat (embedding vector_cosine_ops)" in up
    assert "DROP TABLE IF EXISTS retrieval_chunks" in down
