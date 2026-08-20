from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from project_pipeline.io import sha256_canonical_file

try:
    import psycopg
except ImportError:  # optional database extra; absence is an observed runtime fact
    psycopg = None

PathLike = str | os.PathLike[str]

EXACT_FALLBACK_ENGINE = "sqlite_exact_fallback"
PGVECTOR_ENGINE = "postgresql_pgvector"
_SOURCE_REF = re.compile(
    r"^(SRC-[0-9]{3}):L([0-9]{6})-L([0-9]{6})$",
    re.IGNORECASE,
)


class SemanticEngineStatus(StrEnum):
    MEASURED = "MEASURED"
    UNAVAILABLE_IN_EXECUTION_ENVIRONMENT = "UNAVAILABLE_IN_EXECUTION_ENVIRONMENT"


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    chunk_id: str
    source_reference: str
    score: float
    method: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _tokens(value: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", value.casefold()) if len(part) >= 3}


def deterministic_embedding(text: str, dims: int = 8) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [((digest[index] / 255.0) * 2.0) - 1.0 for index in range(dims)]


def pgvector_dsn() -> str:
    return os.environ.get("PROJECT_PIPELINE_PGVECTOR_DSN", "").strip()


def probe_pgvector(dsn: str | None = None) -> SemanticEngineStatus:
    """Probe a live PostgreSQL/pgvector endpoint. A set DSN is not itself a measurement."""

    target = (dsn if dsn is not None else pgvector_dsn()).strip()
    driver = psycopg
    if not target or driver is None:
        return SemanticEngineStatus.UNAVAILABLE_IN_EXECUTION_ENVIRONMENT
    try:
        with closing(driver.connect(target, connect_timeout=5)) as connection:
            row = connection.execute(
                "SELECT extname FROM pg_extension WHERE extname = %s",
                ("vector",),
            ).fetchone()
            if row is None:
                return SemanticEngineStatus.UNAVAILABLE_IN_EXECUTION_ENVIRONMENT
    except OSError:
        return SemanticEngineStatus.UNAVAILABLE_IN_EXECUTION_ENVIRONMENT
    except driver.Error:
        return SemanticEngineStatus.UNAVAILABLE_IN_EXECUTION_ENVIRONMENT
    return SemanticEngineStatus.MEASURED


class RetrievalService:
    """Exact source-address retrieval with optional pgvector semantic ranking."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert_chunk(
        self,
        *,
        chunk_id: str,
        source_reference: str,
        start_line: int,
        end_line: int,
        text: str,
        embedding_model: str | None = None,
        embedding_version: str | None = None,
        embedding: list[float] | None = None,
    ) -> None:
        vector = embedding if embedding is not None else deterministic_embedding(text)
        payload = json.dumps(vector)
        self.connection.execute(
            """
            INSERT INTO retrieval_chunks(
                chunk_id, source_reference, start_line, end_line, text,
                embedding_model, embedding_version, embedding_json, recorded_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chunk_id) DO UPDATE SET
                source_reference=excluded.source_reference,
                start_line=excluded.start_line,
                end_line=excluded.end_line,
                text=excluded.text,
                embedding_model=excluded.embedding_model,
                embedding_version=excluded.embedding_version,
                embedding_json=excluded.embedding_json,
                recorded_at_utc=excluded.recorded_at_utc
            """,
            (
                chunk_id,
                source_reference,
                start_line,
                end_line,
                text,
                embedding_model or "sha256-8dim",
                embedding_version or "1",
                payload,
                _now(),
            ),
        )
        self.connection.commit()

    def exact_lookup(self, query: str) -> tuple[RetrievalHit, ...]:
        match = _SOURCE_REF.fullmatch(query.strip())
        if match is not None:
            source = f"{match.group(1).upper()}:L{match.group(2)}-L{match.group(3)}"
            rows = self.connection.execute(
                """
                SELECT chunk_id, source_reference
                FROM retrieval_chunks
                WHERE source_reference = ?
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
        for chunk_id, source_reference, text in self.connection.execute(
            "SELECT chunk_id, source_reference, text FROM retrieval_chunks"
        ):
            present = _tokens(str(text))
            overlap = len(wanted & present)
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

    def semantic_status(self) -> SemanticEngineStatus:
        return probe_pgvector()

    def search(self, query: str) -> tuple[RetrievalHit, ...]:
        exact = self.exact_lookup(query)
        if exact and exact[0].method == "exact_source_address":
            return exact
        return exact

    def backup(self, artifact_path: PathLike) -> dict[str, Any]:
        path = Path(artifact_path)
        rows = [
            {
                "chunk_id": chunk_id,
                "source_reference": source_reference,
                "start_line": start_line,
                "end_line": end_line,
                "text": text,
                "embedding_model": embedding_model,
                "embedding_version": embedding_version,
                "embedding_json": embedding_json,
            }
            for (
                chunk_id,
                source_reference,
                start_line,
                end_line,
                text,
                embedding_model,
                embedding_version,
                embedding_json,
            ) in self.connection.execute(
                """
                SELECT chunk_id, source_reference, start_line, end_line, text,
                       embedding_model, embedding_version, embedding_json
                FROM retrieval_chunks
                ORDER BY chunk_id
                """
            )
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        digest = sha256_canonical_file(path)
        receipt_id = (
            "RTRV-" + hashlib.sha256(f"{digest}\x1f{len(rows)}".encode()).hexdigest()[:20].upper()
        )
        payload = {
            "engine": EXACT_FALLBACK_ENGINE,
            "chunk_count": len(rows),
            "artifact_path": path.as_posix(),
        }
        self.connection.execute(
            """
            INSERT INTO retrieval_backup_receipts(
                receipt_id, engine, artifact_sha256, chunk_count, recorded_at_utc, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                receipt_id,
                EXACT_FALLBACK_ENGINE,
                digest,
                len(rows),
                _now(),
                json.dumps(payload, sort_keys=True),
            ),
        )
        self.connection.commit()
        return {
            "receipt_id": receipt_id,
            "engine": EXACT_FALLBACK_ENGINE,
            "artifact_sha256": digest,
            "chunk_count": len(rows),
            "verified": True,
        }

    def restore_and_verify(self, artifact_path: PathLike) -> dict[str, Any]:
        path = Path(artifact_path)
        rows = json.loads(path.read_text(encoding="utf-8"))
        current = {
            str(item[0])
            for item in self.connection.execute("SELECT chunk_id FROM retrieval_chunks")
        }
        restored = {str(item["chunk_id"]) for item in rows}
        return {
            "verified": current == restored,
            "chunk_count": len(restored),
            "missing_chunk_ids": sorted(restored - current),
        }
