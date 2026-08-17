from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_pipeline.domain import TraceabilityLinkType, TraceabilityMutation
from project_pipeline.persistence import (
    ConcurrentStateChangeError,
    SQLiteStateStore,
    links_from_requirement,
)
from project_pipeline.services import RequirementTraceabilityService
from project_pipeline.services.traceability import load_typed_requirement_catalog

ROOT = Path(__file__).resolve().parents[1]


class TraceabilityStoreTests(unittest.TestCase):
    def test_authoritative_catalog_import_is_exact(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            SQLiteStateStore(Path(directory) / "state.db", ROOT) as store,
        ):
            service = RequirementTraceabilityService(store, ROOT)
            result = service.import_authoritative_catalog()
            expected_count = len(load_typed_requirement_catalog(ROOT))
            self.assertEqual(expected_count, 352)
            self.assertEqual(result["requirement_count"], expected_count)
            expected_links = sum(
                len(links_from_requirement(item)) for item in load_typed_requirement_catalog(ROOT)
            )
            self.assertEqual(result["link_count"], expected_links)
            self.assertEqual(service.verify_authoritative_equivalence(), [])

    def test_requirement_trace_is_grouped_and_bidirectional(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            SQLiteStateStore(Path(directory) / "state.db", ROOT) as store,
        ):
            service = RequirementTraceabilityService(store, ROOT)
            service.import_authoritative_catalog()
            trace = service.trace_requirement("REQ-ARCH-0008")
            assert trace is not None
            source = trace["links"]["SOURCE"][0]
            self.assertIn("REQ-ARCH-0008", service.requirements_for_source(source))
            plan = trace["links"]["PLAN"][0]
            self.assertIn(
                "REQ-ARCH-0008",
                service.requirements_for_target(TraceabilityLinkType.PLAN, plan),
            )

    def test_changed_and_noop_mutations_have_correct_revisions(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            SQLiteStateStore(Path(directory) / "state.db", ROOT) as store,
        ):
            service = RequirementTraceabilityService(store, ROOT)
            service.import_authoritative_catalog()
            no_op = service.mutate(
                TraceabilityMutation(
                    requirement_id="REQ-ARCH-0008",
                    operation="ADD",
                    link_type=TraceabilityLinkType.IMPLEMENTATION,
                    target="architecture/state_ownership.json",
                    expected_revision=1,
                    actor_id="actor:test",
                    correlation_id="corr:noop",
                    reason="Verify idempotent no-op handling.",
                )
            )
            self.assertFalse(no_op["changed"])
            self.assertEqual(no_op["resulting_revision"], 1)
            changed = service.mutate(
                TraceabilityMutation(
                    requirement_id="REQ-ARCH-0008",
                    operation="ADD",
                    link_type=TraceabilityLinkType.IMPLEMENTATION,
                    target="docs/data/traceability_projection.md",
                    expected_revision=1,
                    actor_id="actor:test",
                    correlation_id="corr:change",
                    reason="Exercise proposed-change projection.",
                )
            )
            self.assertTrue(changed["changed"])
            self.assertEqual(changed["resulting_revision"], 2)

    def test_stale_traceability_mutation_is_rejected(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            SQLiteStateStore(Path(directory) / "state.db", ROOT) as store,
        ):
            service = RequirementTraceabilityService(store, ROOT)
            service.import_authoritative_catalog()
            mutation = TraceabilityMutation(
                requirement_id="REQ-ARCH-0008",
                operation="ADD",
                link_type=TraceabilityLinkType.IMPLEMENTATION,
                target="docs/data/traceability_projection.md",
                expected_revision=1,
                actor_id="actor:test",
                correlation_id="corr:first",
                reason="Create revision two.",
            )
            service.mutate(mutation)
            with self.assertRaises(ConcurrentStateChangeError):
                service.mutate(mutation.model_copy(update={"correlation_id": "corr:stale"}))

    def test_projection_export_does_not_replace_authoritative_catalog(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            SQLiteStateStore(Path(directory) / "state.db", ROOT) as store,
        ):
            service = RequirementTraceabilityService(store, ROOT)
            service.import_authoritative_catalog()
            output = Path(directory) / "projection.jsonl"
            result = service.write_projection(output)
            self.assertEqual(result["authority"], "PROPOSED_CHANGE")
            self.assertEqual(result["requirement_count"], len(load_typed_requirement_catalog(ROOT)))
            self.assertTrue(output.exists())
            self.assertEqual(service.verify_authoritative_equivalence(), [])
