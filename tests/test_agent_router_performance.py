from datetime import UTC, datetime, timedelta

import pytest

from project_pipeline.agent_router.performance import summarize_performance
from project_pipeline.domain import PerformanceObservation


def test_performance_registry_summarizes_measured_outcomes():
    now = datetime.now(UTC)
    observations = (
        PerformanceObservation(
            observation_id="PERF-A",
            target_id="agent:test",
            capability_id="code_review",
            task_class="review",
            success=True,
            latency_ms=100,
            cost_microunits=20,
            retry_count=1,
            rework_count=2,
            review_findings=3,
            quality_milli=900,
            observed_at_utc=now,
        ),
        PerformanceObservation(
            observation_id="PERF-B",
            target_id="agent:test",
            capability_id="code_review",
            task_class="review",
            success=False,
            latency_ms=300,
            cost_microunits=40,
            retry_count=2,
            rework_count=1,
            review_findings=4,
            quality_milli=500,
            observed_at_utc=now,
        ),
    )
    summary = summarize_performance(observations)[("agent:test", "code_review")]
    assert summary.sample_count == 2
    assert summary.success_milli == 500
    assert summary.quality_milli == 700
    assert summary.mean_latency_ms == 200
    assert summary.mean_cost_microunits == 30
    assert observations[0].retry_count == 1
    assert observations[0].rework_count == 2
    assert observations[0].review_findings == 3


def test_performance_registry_rejects_synthetic_and_ages_out_stale_samples():
    now = datetime(2026, 8, 17, tzinfo=UTC)
    synthetic = PerformanceObservation(
        observation_id="PERF-SYNTH",
        target_id="agent:test",
        capability_id="code_review",
        task_class="review",
        success=True,
        latency_ms=1,
        observed_at_utc=now,
        synthetic=True,
    )
    with pytest.raises(ValueError, match="synthetic"):
        summarize_performance((synthetic,), now=now)
    stale = PerformanceObservation(
        observation_id="PERF-OLD",
        target_id="agent:test",
        capability_id="code_review",
        task_class="review",
        success=True,
        latency_ms=10,
        observed_at_utc=now - timedelta(days=30),
    )
    fresh = PerformanceObservation(
        observation_id="PERF-NEW",
        target_id="agent:test",
        capability_id="code_review",
        task_class="review",
        success=False,
        latency_ms=50,
        observed_at_utc=now,
    )
    summary = summarize_performance((stale, fresh), now=now)[("agent:test", "code_review")]
    assert summary.sample_count == 1
    assert summary.success_milli == 0
