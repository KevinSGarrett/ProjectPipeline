from __future__ import annotations

import json
import unittest
from pathlib import Path

from project_pipeline.architecture import (
    build_decision_map,
    find_components,
    summarize_architecture,
    validate_architecture,
)

ROOT = Path(__file__).resolve().parents[1]


class ArchitectureRegistryTests(unittest.TestCase):
    def test_architecture_catalog_is_complete_and_valid(self) -> None:
        self.assertEqual([], validate_architecture(ROOT))
        summary = summarize_architecture(ROOT)
        self.assertEqual(summary["component_count"], 35)
        self.assertEqual(summary["technology_count"], 34)
        self.assertEqual(summary["trust_boundary_count"], 6)
        self.assertEqual(summary["deployment_profile_count"], 3)

    def test_authority_and_state_ownership_are_explicit(self) -> None:
        catalog = json.loads(
            (ROOT / "architecture/component_catalog.json").read_text(encoding="utf-8")
        )
        states = json.loads(
            (ROOT / "architecture/state_ownership.json").read_text(encoding="utf-8")
        )
        self.assertIn("deterministic", catalog["authority_model"].casefold())
        entities = [item["entity"] for item in states["entities"]]
        self.assertEqual(len(entities), len(set(entities)))
        owners = {item["component_id"] for item in catalog["components"]}
        self.assertTrue(all(item["authoritative_owner"] in owners for item in states["entities"]))

    def test_technology_stack_preserves_latest_source_chronology(self) -> None:
        stack = json.loads(
            (ROOT / "architecture/technology_stack.json").read_text(encoding="utf-8")
        )
        technologies = {item["technology_id"]: item for item in stack["technologies"]}
        self.assertEqual(technologies["TECH-WORKFLOW-001"]["selection"], "Hatchet")
        self.assertEqual(technologies["TECH-WORKFLOW-001"]["lifecycle_status"], "SELECTED")
        self.assertEqual(
            technologies["TECH-WORKFLOW-002"]["lifecycle_status"], "QUALIFIED_FALLBACK"
        )
        self.assertEqual(
            technologies["TECH-WORKFLOW-003"]["lifecycle_status"], "QUALIFIED_FALLBACK"
        )
        self.assertIn("PostgreSQL", stack["canonical_state_owner"])
        self.assertFalse(
            any(
                "DBOS" in value
                for value in [stack["durable_execution_backend"]]
                if value.startswith("DBOS")
            )
        )

    def test_diagrams_and_profiles_match_selected_backend(self) -> None:
        diagrams = ROOT / "architecture/diagrams"
        for name in ("system_context.mmd", "durable_command_flow.mmd", "deployment_profiles.mmd"):
            text = (diagrams / name).read_text(encoding="utf-8")
            self.assertIn("Hatchet", text)
            self.assertNotIn("DBOS Adapter", text)
        profiles = json.loads(
            (ROOT / "architecture/deployment_profiles.json").read_text(encoding="utf-8")
        )
        local = next(item for item in profiles["profiles"] if item["profile_id"] == "LOCAL_CORE")
        self.assertIn("Hatchet", local["external_dependencies"])

    def test_architecture_queries_and_decision_map_are_deterministic(self) -> None:
        first = find_components(ROOT, layer="DETERMINISTIC_CONTROL")
        second = find_components(ROOT, layer="deterministic_control")
        self.assertEqual(first, second)
        observed = json.loads((ROOT / "architecture/decision_map.json").read_text(encoding="utf-8"))
        self.assertEqual(observed, build_decision_map(ROOT))

    def test_component_query_is_bounded(self) -> None:
        rows = find_components(ROOT, layer="DETERMINISTIC_CONTROL")
        self.assertTrue(rows)
        self.assertTrue(all(item["layer"] == "DETERMINISTIC_CONTROL" for item in rows))

    def test_architecture_registry_is_cross_linked_and_current(self) -> None:
        stack = json.loads(
            (ROOT / "architecture/technology_stack.json").read_text(encoding="utf-8")
        )
        self.assertEqual(stack["technology_count"], len(stack["technologies"]))
        self.assertEqual([], validate_architecture(ROOT))
        self.assertTrue((ROOT / "architecture/requirement_component_map.jsonl").exists())
        self.assertTrue((ROOT / "architecture/component_requirement_map.jsonl").exists())

    def test_local_artifact_store_deduplicates_and_detects_corruption(self) -> None:
        import tempfile

        from project_pipeline.artifacts import LocalContentAddressedStore

        with tempfile.TemporaryDirectory() as directory:
            store = LocalContentAddressedStore(Path(directory))
            first = store.put(b"same bytes", "text/plain")
            second = store.put(b"same bytes", "text/plain")
            self.assertEqual(first, second)
            self.assertTrue(store.verify(first))
            path = Path(directory) / first.digest[:2] / first.digest[2:4] / first.digest
            path.write_bytes(b"changed")
            self.assertFalse(store.verify(first))
