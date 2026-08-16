from datetime import UTC, datetime

import pytest

from project_pipeline.domain.context import (
    ContextCandidate,
    ContextSourceKind,
    ContextTrust,
    CoverageReport,
    DelegationEnvelope,
)


def test_delegation_id_is_deterministic():
    a = DelegationEnvelope.create(
        objective="Implement context",
        return_protocol="Return evidence",
        required_context_keys=("requirements",),
        expected_revisions={"requirements": "r1"},
    )
    b = DelegationEnvelope.create(
        objective="Implement context",
        return_protocol="Return evidence",
        required_context_keys=("requirements",),
        expected_revisions={"requirements": "r1"},
    )
    assert a.delegation_id == b.delegation_id


def test_delegation_rejects_overlapping_keys():
    with pytest.raises(ValueError):
        DelegationEnvelope.create(
            objective="x",
            return_protocol="y",
            required_context_keys=("a",),
            optional_context_keys=("a",),
        )


def test_coverage_validates_score():
    with pytest.raises(ValueError):
        CoverageReport(required_count=2, represented_count=1, score=1.0)


def test_models_are_immutable():
    item = ContextCandidate(
        context_key="x",
        kind=ContextSourceKind.OTHER,
        content="x",
        revision_id="1",
        observed_at_utc=datetime.now(UTC),
        trust=ContextTrust.AUTHORITATIVE,
    )
    with pytest.raises((AttributeError, TypeError, ValueError)):
        item.content = "y"
