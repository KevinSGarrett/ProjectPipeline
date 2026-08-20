from project_pipeline.retrieval.benchmark import run_retrieval_benchmark
from project_pipeline.retrieval.service import (
    EXACT_FALLBACK_ENGINE,
    PGVECTOR_ENGINE,
    RetrievalService,
    SemanticEngineStatus,
    probe_pgvector,
)

__all__ = [
    "EXACT_FALLBACK_ENGINE",
    "PGVECTOR_ENGINE",
    "RetrievalService",
    "SemanticEngineStatus",
    "probe_pgvector",
    "run_retrieval_benchmark",
]
