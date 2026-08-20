from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_pipeline.verification.containers import (
    docker_engine_ready,
    postgres_vector_container,
)

ROOT = Path(__file__).resolve().parents[2]
PGVECTOR_UP = (
    ROOT / "database/migrations/postgresql/PPDB-0025_retrieval_pgvector_and_exact_fallback.up.sql"
)


def test_docker_engine_probe_is_structured() -> None:
    probe = docker_engine_ready()
    assert "ready" in probe
    assert probe["reason"] in {
        "DOCKER_CLI_MISSING",
        "DOCKER_ENGINE_UNREACHABLE",
        "DOCKER_ENGINE_NOT_RUNNING",
        "DOCKER_ENGINE_READY",
    }
    if not probe["ready"]:
        pytest.skip(json.dumps(probe))


def test_pgvector_container_persists_across_kill_and_records_image_identity() -> None:
    probe = docker_engine_ready()
    if not probe["ready"]:
        pytest.skip(json.dumps(probe))

    sql = PGVECTOR_UP.read_text(encoding="utf-8")
    with postgres_vector_container() as container:
        identity = container.inspect_identity()
        assert identity["image_id"].startswith("sha256:")
        assert identity["requested_image"] == "pgvector/pgvector:pg16"
        container.exec_sql(sql)
        container.exec_sql(
            """
            INSERT INTO retrieval_chunks(
                chunk_id, source_reference, start_line, end_line, text,
                embedding_model, embedding_version, embedding, recorded_at_utc
            ) VALUES (
                'CHK-E2E-001',
                'SRC-011:L000601-L000652',
                601,
                652,
                'PostgreSQL plus pgvector is the default semantic retrieval boundary.',
                'sha256-8dim',
                '1',
                '[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8]',
                NOW()
            );
            """
        )
        before = container.exec_sql(
            "SELECT chunk_id FROM retrieval_chunks WHERE chunk_id = 'CHK-E2E-001';"
        )
        assert "CHK-E2E-001" in before
        exact = container.exec_sql(
            "SELECT chunk_id FROM retrieval_chunks "
            "WHERE source_reference = 'SRC-011:L000601-L000652';"
        )
        assert "CHK-E2E-001" in exact
        container.kill()
        container.resume()
        after = container.exec_sql(
            "SELECT chunk_id FROM retrieval_chunks WHERE chunk_id = 'CHK-E2E-001';"
        )
        assert "CHK-E2E-001" in after
        recovered = container.inspect_identity()
        assert recovered["image_id"] == identity["image_id"]
        assert recovered["container_id"] == identity["container_id"]
