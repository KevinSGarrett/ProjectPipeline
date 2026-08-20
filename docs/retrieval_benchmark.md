# Retrieval benchmark and exact fallback

PostgreSQL plus pgvector is the default semantic profile (`ADR-0018`, `ADR-0021`). This repository still starts from a local SQLite control plane, so the committed benchmark proves the **exact source-address fallback** and records when pgvector is unavailable instead of inventing semantic scores.

## What the slice qualifies

| Concern | Evidence |
|---|---|
| Migrations | `PPDB-0025` adds `retrieval_chunks` and `retrieval_backup_receipts` for SQLite and PostgreSQL. PostgreSQL enables `vector`, stores `embedding vector(8)` for the fixture dimension, and creates `idx_retrieval_chunks_embedding` (`ivfflat` cosine). |
| Indexes | SQLite and PostgreSQL both index `(source_reference, start_line, end_line)`. PostgreSQL adds the pgvector ANN index. |
| Exact fallback | Queries that match `SRC-NNN:Lxxxxxx-Lxxxxxx` return that chunk with score `1.0`. Other queries use deterministic lexical overlap. Semantic ranking never replaces exact identity. |
| Backup / restore | `project-pipeline retrieval benchmark` dumps chunks to `benchmarks/retrieval/backup.json`, stores a receipt, and verifies the live table still contains those chunk IDs. PostgreSQL production backups remain `pg_dump` of `retrieval_chunks` plus the same JSON dump. |
| Quality | `benchmarks/retrieval/corpus.jsonl` is the fixture. `exact_recall_at_1` must be `1.0` on that fixture. `semantic_status` is `MEASURED` only after a live PostgreSQL connection proves the `vector` extension; a set `PROJECT_PIPELINE_PGVECTOR_DSN` is not itself a measurement. |
| Standalone vector DBs | Qdrant and peers stay deferred until this benchmark, plus measured scale, justifies a separately operated service. |

## Commands

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m project_pipeline retrieval benchmark --root .
```

The command writes `benchmarks/retrieval/latest.json`. It does not claim live PostgreSQL/pgvector quality from SQLite.

## Rollback

`PPDB-0025` is reversible. Rolling it back drops retrieval tables only; prior migrations stay intact.
