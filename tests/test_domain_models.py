from __future__ import annotations

import unittest
from pathlib import Path

from pydantic import ValidationError

from project_pipeline.domain import (
    ProjectLifecycleState,
    RequirementRecord,
    TaskLifecycleState,
    ensure_project_transition,
    ensure_task_transition,
    task_state_from_jira,
)
from project_pipeline.io import read_jsonl
from project_pipeline.services.state import (
    task_records_from_jira,
    validate_project_domain_manifest,
    write_project_domain_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


class DomainModelTests(unittest.TestCase):
    def test_all_authoritative_requirements_parse_as_strict_entities(self) -> None:
        rows = read_jsonl(ROOT / "plans" / "_traceability" / "requirements.jsonl")
        records = [RequirementRecord.model_validate(row) for row in rows]
        self.assertEqual(len(records), 352)
        self.assertEqual(len({record.requirement_id for record in records}), 352)

    def test_requirement_unknown_fields_are_rejected(self) -> None:
        row = read_jsonl(ROOT / "plans" / "_traceability" / "requirements.jsonl")[0]
        with self.assertRaises(ValidationError):
            RequirementRecord.model_validate({**row, "unexpected": True})

    def test_domain_project_manifest_is_idempotent_and_valid(self) -> None:
        first = write_project_domain_manifest(ROOT)
        second = write_project_domain_manifest(ROOT)
        self.assertEqual(first.model_dump(mode="json"), second.model_dump(mode="json"))
        self.assertEqual(validate_project_domain_manifest(ROOT), [])
        self.assertEqual(
            first.primary_repository().canonical_url,
            "https://github.com/KevinSGarrett/ProjectPipeline",
        )

    def test_jira_work_items_compile_to_typed_task_state(self) -> None:
        records = task_records_from_jira(ROOT, "PROJECT-PIPELINE")
        expected = __import__("json").loads(
            (ROOT / "jira/BOARD_MANIFEST.json").read_text(encoding="utf-8")
        )["issue_count"]
        self.assertEqual(len(records), expected)
        self.assertEqual(len({record.task_id for record in records}), expected)
        self.assertTrue(all(isinstance(record.state, TaskLifecycleState) for record in records))
        self.assertTrue(any(record.state is TaskLifecycleState.BACKLOG for record in records))

    def test_jira_validation_state_maps_to_internal_validating_state(self) -> None:
        self.assertIs(task_state_from_jira("VALIDATION"), TaskLifecycleState.VALIDATING)

    def test_invalid_project_and_task_transitions_are_rejected(self) -> None:
        ensure_project_transition(ProjectLifecycleState.REGISTERED, ProjectLifecycleState.COMPILING)
        ensure_task_transition(TaskLifecycleState.BACKLOG, TaskLifecycleState.READY)
        with self.assertRaises(ValueError):
            ensure_project_transition(
                ProjectLifecycleState.REGISTERED, ProjectLifecycleState.COMPLETED
            )
        with self.assertRaises(ValueError):
            ensure_task_transition(TaskLifecycleState.BACKLOG, TaskLifecycleState.DONE)
