from datetime import UTC, datetime, timedelta

import pytest

from project_pipeline.context_engine import ContextBroker, ContextCompilationError, ContextCompiler
from project_pipeline.domain.context import (
    ContextCandidate,
    ContextPolicy,
    ContextSourceKind,
    ContextTrust,
    DelegationEnvelope,
    Sensitivity,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def cand(key, **kw):
    base = dict(
        context_key=key,
        kind=ContextSourceKind.SOURCE_FILE,
        content=key,
        revision_id="r1",
        observed_at_utc=NOW,
        trust=ContextTrust.SOURCE_CONTROLLED,
        sensitivity=Sensitivity.INTERNAL,
    )
    base.update(kw)
    return ContextCandidate(**base)


def env(required=("a",), optional=("b",), **kw):
    return DelegationEnvelope.create(
        objective="do",
        return_protocol="return",
        required_context_keys=required,
        optional_context_keys=optional,
        **kw,
    )


def policy(**kw):
    return ContextPolicy(policy_version="CTX-POLICY-1.0", max_age_seconds=3600, **kw)


def test_broker_never_adds_unrequested_context():
    s = ContextBroker().select(env(), (cand("a"), cand("b"), cand("extra")), policy())
    assert s.selected_keys == ("a", "b") and "extra" not in s.selected_keys


def test_broker_reports_unknown_required():
    s = ContextBroker().select(env(required=("missing",), optional=()), (cand("a"),), policy())
    assert s.unknown_keys == ("missing",)


def test_compiler_is_content_addressed_for_same_semantics():
    e = env(required=("a",), optional=(), expected_revisions={"a": "r1"})
    cs = (cand("a"),)
    sel = ContextBroker().select(e, cs, policy())
    a = ContextCompiler().compile(e, sel, cs, policy(), generated_at_utc=NOW)
    b = ContextCompiler().compile(e, sel, cs, policy(), generated_at_utc=NOW + timedelta(seconds=1))
    assert a.pack_id == b.pack_id and a.content_sha256 == b.content_sha256


def test_required_stale_context_fails_coverage():
    e = env(required=("a",), optional=(), expected_revisions={"a": "r2"})
    cs = (cand("a"),)
    sel = ContextBroker().select(e, cs, policy())
    with pytest.raises(ContextCompilationError):
        ContextCompiler().compile(e, sel, cs, policy(), generated_at_utc=NOW)


def test_optional_stale_context_can_be_disclosed_when_allowed():
    e = env(required=(), optional=("a",), expected_revisions={"a": "r2"})
    cs = (cand("a"),)
    p = policy(allow_stale_optional=True)
    sel = ContextBroker().select(e, cs, p)
    pack = ContextCompiler().compile(e, sel, cs, p, generated_at_utc=NOW)
    assert pack.stale_keys == ("a",) and len(pack.items) == 1


def test_pack_size_fails_closed():
    e = env(required=("a",), optional=())
    cs = (cand("a", content="x" * 2000),)
    p = ContextPolicy(policy_version="CTX-POLICY-1.0", max_chars=1024, max_age_seconds=3600)
    sel = ContextBroker().select(e, cs, p)
    with pytest.raises(ContextCompilationError):
        ContextCompiler().compile(e, sel, cs, p, generated_at_utc=NOW)


def test_telemetry_reports_required_metrics():
    e = env(required=("a",), optional=())
    cs = (cand("a"),)
    p = policy()
    pack = ContextCompiler().compile(
        e, ContextBroker().select(e, cs, p), cs, p, generated_at_utc=NOW
    )
    t = ContextCompiler().telemetry(pack)
    assert t.item_count == 1 and t.coverage_score == 1.0 and t.source_count == 1


def test_disconnected_reviewer_package_requires_all_categories():
    kinds = [
        ContextSourceKind.DIFF,
        ContextSourceKind.SOURCE_FILE,
        ContextSourceKind.TEST,
        ContextSourceKind.EVIDENCE,
        ContextSourceKind.REVIEW_RUBRIC,
    ]
    cs = tuple(cand(str(i), kind=k) for i, k in enumerate(kinds))
    e = env(required=tuple(str(i) for i in range(5)), optional=())
    p = policy()
    pack = ContextCompiler().compile(
        e, ContextBroker().select(e, cs, p), cs, p, generated_at_utc=NOW
    )
    rp = ContextCompiler().reviewer_package(pack)
    assert rp.diff_keys and rp.rubric_keys
