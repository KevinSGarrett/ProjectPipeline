from __future__ import annotations

from pathlib import Path
from typing import Any

from project_pipeline.domain import (
    RequirementRecord,
    TraceabilityLinkType,
    TraceabilityMutation,
)
from project_pipeline.io import read_jsonl, write_jsonl
from project_pipeline.persistence import SQLiteStateStore, catalog_sha256

REQUIREMENT_CATALOG_PATH = Path("plans/_traceability/requirements.jsonl")


def load_typed_requirement_catalog(root: Path) -> tuple[RequirementRecord, ...]:
    rows = read_jsonl(root / REQUIREMENT_CATALOG_PATH)
    return tuple(RequirementRecord.model_validate(item) for item in rows)


class RequirementTraceabilityService:
    """Transactional traceability projection with explicit source-catalog authority."""

    def __init__(self, store: SQLiteStateStore, root: Path) -> None:
        self.store = store
        self.root = root.resolve()

    def import_authoritative_catalog(self) -> dict[str, int | str]:
        self.store.initialize()
        path = self.root / REQUIREMENT_CATALOG_PATH
        records = load_typed_requirement_catalog(self.root)
        return self.store.import_requirements(
            records,
            source_path=REQUIREMENT_CATALOG_PATH.as_posix(),
            catalog_sha256=catalog_sha256(path),
        )

    def verify_authoritative_equivalence(self) -> list[str]:
        return self.store.verify_requirement_equivalence(load_typed_requirement_catalog(self.root))

    def trace_requirement(self, requirement_id: str) -> dict[str, Any] | None:
        record = self.store.get_requirement(requirement_id)
        if record is None:
            return None
        links = self.store.list_requirement_links(requirement_id)
        grouped: dict[str, list[str]] = {}
        for link in links:
            grouped.setdefault(link.link_type.value, []).append(link.target)
        return {
            "schema_version": "1.0.0",
            "authority": "PERSISTED_PROJECTION",
            "catalog_authority": REQUIREMENT_CATALOG_PATH.as_posix(),
            "requirement": record.as_registry_row(),
            "revision": self.store.requirement_revision(requirement_id),
            "links": {key: sorted(values) for key, values in sorted(grouped.items())},
        }

    def requirements_for_source(self, source_reference: str) -> tuple[str, ...]:
        return self.store.requirements_for_target(TraceabilityLinkType.SOURCE, source_reference)

    def requirements_for_target(
        self, link_type: TraceabilityLinkType, target: str
    ) -> tuple[str, ...]:
        return self.store.requirements_for_target(link_type, target)

    def mutate(self, mutation: TraceabilityMutation) -> dict[str, Any]:
        result = self.store.apply_traceability_mutation(mutation)
        return result.model_dump(mode="json")

    def write_projection(self, output: Path) -> dict[str, Any]:
        rows = self.store.export_requirement_projection()
        write_jsonl(output, rows)
        payload = output.read_bytes()
        return {
            "schema_version": "1.0.0",
            "output": str(output),
            "requirement_count": len(rows),
            "sha256": __import__("hashlib").sha256(payload).hexdigest(),
            "authority": "PROPOSED_CHANGE",
            "note": "The projection does not replace the authoritative catalog automatically.",
        }

    def status(self) -> dict[str, Any]:
        records = self.store.list_requirements()
        links = sum(len(self.store.list_requirement_links(item.requirement_id)) for item in records)
        return {
            "schema_version": "1.0.0",
            "catalog_path": REQUIREMENT_CATALOG_PATH.as_posix(),
            "catalog_sha256": catalog_sha256(self.root / REQUIREMENT_CATALOG_PATH),
            "persisted_requirement_count": len(records),
            "persisted_link_count": links,
            "equivalence_errors": self.verify_authoritative_equivalence(),
        }
