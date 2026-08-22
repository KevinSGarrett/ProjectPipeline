from __future__ import annotations

from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from typing import Any

from project_pipeline.persistence.migrations import load_migration_catalog, split_sql_statements
from project_pipeline.retrieval.service import (
    _SOURCE_REF,
    RetrievalHit,
    SemanticEngineStatus,
    _tokens,
    deterministic_embedding,
    probe_pgvector,
)

try:
    import psycopg as _psycopg  # type: ignore[import-not-found]
except ImportError:  # optional database extra; absence is an observed runtime fact
    _psycopg = None
psycopg: Any = _psycopg


def apply_postgresql_migrations(
    dsn: str,
    root: Path,
    *,
    migration_ids: Sequence[str] | None = None,
) -> tuple[str, ...]:
    driver = psycopg
    if driver is None:
        raise RuntimeError("psycopg is required to apply PostgreSQL migrations")
    catalog = load_migration_catalog(root)
    wanted = set(migration_ids) if migration_ids is not None else None
    applied: list[str] = []
    with closing(driver.connect(dsn)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_id TEXT PRIMARY KEY,
                sequence INTEGER NOT NULL UNIQUE,
                name TEXT NOT NULL,
                applied_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        for migration in catalog.migrations:
            if wanted is not None and migration.migration_id not in wanted:
                continue
            existing = connection.execute(
                "SELECT migration_id FROM schema_migrations WHERE migration_id = %s",
                (migration.migration_id,),
            ).fetchone()
            if existing is not None:
                applied.append(migration.migration_id)
                continue
            sql = (root / migration.postgresql_up_path).read_text(encoding="utf-8")
            for statement in split_sql_statements(sql):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(migration_id, sequence, name) VALUES (%s, %s, %s)",
                (migration.migration_id, migration.sequence, migration.name),
            )
            applied.append(migration.migration_id)
        connection.commit()
    return tuple(applied)


class PostgresRetrievalService:
    """PostgreSQL/pgvector semantic retrieval with exact source-address fallback."""

    def __init__(self, dsn: str) -> None:
        driver = psycopg
        if driver is None:
            raise RuntimeError("psycopg is required for PostgreSQL retrieval")
        self.dsn = dsn
        self._driver = driver

    def upsert_chunk(
        self,
        *,
        chunk_id: str,
        source_reference: str,
        start_line: int,
        end_line: int,
        text: str,
        embedding: list[float] | None = None,
    ) -> None:
        vector = embedding or deterministic_embedding(text)
        literal = "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
        with closing(self._driver.connect(self.dsn)) as connection:
            connection.execute(
                """
                INSERT INTO retrieval_chunks(
                    chunk_id, source_reference, start_line, end_line, text,
                    embedding_model, embedding_version, embedding, recorded_at_utc
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, NOW())
                ON CONFLICT (chunk_id) DO UPDATE SET
                    source_reference = EXCLUDED.source_reference,
                    start_line = EXCLUDED.start_line,
                    end_line = EXCLUDED.end_line,
                    text = EXCLUDED.text,
                    embedding = EXCLUDED.embedding,
                    recorded_at_utc = EXCLUDED.recorded_at_utc
                """,
                (
                    chunk_id,
                    source_reference,
                    start_line,
                    end_line,
                    text,
                    "sha256-8dim",
                    "1",
                    literal,
                ),
            )
            connection.commit()

    def exact_lookup(self, query: str) -> tuple[RetrievalHit, ...]:
        match = _SOURCE_REF.fullmatch(query.strip())
        with closing(self._driver.connect(self.dsn)) as connection:
            if match is not None:
                source = f"{match.group(1).upper()}:L{match.group(2)}-L{match.group(3)}"
                rows = connection.execute(
                    """
                    SELECT chunk_id, source_reference
                    FROM retrieval_chunks
                    WHERE source_reference = %s
                    ORDER BY chunk_id
                    """,
                    (source,),
                ).fetchall()
                return tuple(
                    RetrievalHit(
                        chunk_id=str(row[0]),
                        source_reference=str(row[1]),
                        score=1.0,
                        method="exact_source_address",
                    )
                    for row in rows
                )
            wanted = _tokens(query)
            if not wanted:
                return ()
            hits: list[RetrievalHit] = []
            for chunk_id, source_reference, text in connection.execute(
                "SELECT chunk_id, source_reference, text FROM retrieval_chunks"
            ):
                overlap = len(wanted & _tokens(str(text)))
                if overlap == 0:
                    continue
                hits.append(
                    RetrievalHit(
                        chunk_id=str(chunk_id),
                        source_reference=str(source_reference),
                        score=overlap / len(wanted),
                        method="exact_lexical_fallback",
                    )
                )
            hits.sort(key=lambda item: (-item.score, item.chunk_id))
            return tuple(hits)

    def semantic_search(self, query: str) -> tuple[RetrievalHit, ...]:
        vector = deterministic_embedding(query)
        literal = "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
        with closing(self._driver.connect(self.dsn)) as connection:
            rows = connection.execute(
                """
                SELECT chunk_id, source_reference,
                       1 - (embedding <=> %s::vector) AS score
                FROM retrieval_chunks
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT 8
                """,
                (literal, literal),
            ).fetchall()
        return tuple(
            RetrievalHit(
                chunk_id=str(row[0]),
                source_reference=str(row[1]),
                score=float(row[2]),
                method="pgvector_cosine",
            )
            for row in rows
        )

    def search(self, query: str) -> tuple[RetrievalHit, ...]:
        exact = self.exact_lookup(query)
        if exact and exact[0].method == "exact_source_address":
            return exact
        semantic = self.semantic_search(query)
        return semantic or exact

    def semantic_status(self) -> SemanticEngineStatus:
        return probe_pgvector(self.dsn)


__all__ = [
    "PostgresRetrievalService",
    "apply_postgresql_migrations",
    "probe_pgvector",
]
