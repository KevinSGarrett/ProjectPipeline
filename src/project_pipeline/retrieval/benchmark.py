from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.persistence.migrations import SQLiteMigrationRunner
from project_pipeline.retrieval.service import (
    EXACT_FALLBACK_ENGINE,
    PGVECTOR_ENGINE,
    RetrievalService,
    probe_pgvector,
)

CORPUS_RELATIVE = "benchmarks/retrieval/corpus.jsonl"


def _load_corpus(root: Path) -> list[dict[str, Any]]:
    path = root / CORPUS_RELATIVE
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def run_retrieval_benchmark(
    root: Path,
    *,
    database: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Run the committed retrieval fixture against exact fallback, never inventing pgvector scores."""

    root = root.resolve()
    destination = (output_dir or (root / "benchmarks/retrieval")).resolve()
    db_path = database or (destination / "retrieval-benchmark.sqlite")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    try:
        SQLiteMigrationRunner(connection, root).apply_all()
        service = RetrievalService(connection)
        corpus = _load_corpus(root)
        for row in corpus:
            service.upsert_chunk(
                chunk_id=str(row["chunk_id"]),
                source_reference=str(row["source_reference"]),
                start_line=int(row["start_line"]),
                end_line=int(row["end_line"]),
                text=str(row["text"]),
            )
        ranked: list[dict[str, Any]] = []
        hits_at_1 = 0
        for row in corpus:
            results = service.search(str(row["query"]))
            top = results[0].chunk_id if results else None
            if top == row["chunk_id"]:
                hits_at_1 += 1
            ranked.append(
                {
                    "query": row["query"],
                    "expected_chunk_id": row["chunk_id"],
                    "top_chunk_id": top,
                    "method": results[0].method if results else None,
                }
            )
        backup = service.backup(destination / "backup.json")
        restore = service.restore_and_verify(destination / "backup.json")
        semantic = probe_pgvector()
        recall = hits_at_1 / len(corpus) if corpus else 0.0
        report = {
            "schema_version": "1.0.0",
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "default_engine": PGVECTOR_ENGINE,
            "observed_engine": EXACT_FALLBACK_ENGINE,
            "semantic_status": semantic.value,
            "indexes": [
                "idx_retrieval_chunks_source",
                "postgresql:idx_retrieval_chunks_embedding",
            ],
            "exact_recall_at_1": recall,
            "query_count": len(corpus),
            "ranked": ranked,
            "backup": {**backup, "restore_verified": restore["verified"]},
            "standalone_vector_service": "DEFERRED_UNTIL_BENCHMARK_JUSTIFIES",
        }
        output = destination / "latest.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report["report_path"] = output.as_posix()
        return report
    finally:
        connection.close()
