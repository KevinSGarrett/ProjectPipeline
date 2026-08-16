from __future__ import annotations

import io
import json
import logging
import unittest

from project_pipeline.configuration import LoggingSettings
from project_pipeline.observability import (
    CorrelationContext,
    configure_logging,
    correlation_scope,
    current_context,
    log_event,
    sanitize,
)


class ObservabilityTests(unittest.TestCase):
    def test_structured_log_contains_correlation_identity_and_redacts_fields(self) -> None:
        stream = io.StringIO()
        logger = configure_logging(LoggingSettings(include_process=False), stream=stream)
        with correlation_scope(project_id="PROJECT-PIPELINE", correlation_id="corr:one"):
            log_event(logger, logging.INFO, "example_event", token="secret-value", count=2)
        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["event"], "example_event")
        self.assertEqual(payload["project_id"], "PROJECT-PIPELINE")
        self.assertEqual(payload["correlation_id"], "corr:one")
        self.assertEqual(payload["attributes"]["token"], "<redacted>")
        self.assertEqual(payload["attributes"]["count"], 2)

    def test_correlation_scope_restores_prior_context(self) -> None:
        before = current_context()
        with correlation_scope(project_id="PROJECT-PIPELINE", task_id="task:one") as active:
            self.assertEqual(active.task_id, "task:one")
            self.assertEqual(current_context().project_id, "PROJECT-PIPELINE")
        self.assertEqual(current_context(), before)

    def test_sanitize_handles_nested_values_and_bytes(self) -> None:
        result = sanitize(
            {"nested": {"api_key": "abc", "blob": b"123"}},
            frozenset({"api_key"}),
        )
        self.assertEqual(result["nested"]["api_key"], "<redacted>")
        self.assertEqual(result["nested"]["blob"], "<bytes:3>")

    def test_invalid_correlation_field_is_rejected(self) -> None:
        with self.assertRaises(ValueError), correlation_scope(unknown="value"):
            self.fail("invalid correlation fields must not enter scope")

    def test_context_attribute_serialization_omits_unset_values(self) -> None:
        context = CorrelationContext(project_id="PROJECT-PIPELINE")
        self.assertEqual(context.as_attributes(), {"project_id": "PROJECT-PIPELINE"})
