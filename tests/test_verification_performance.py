from project_pipeline.verification.performance import measure_callable


def test_performance_measurement_enforces_budget():
    result = measure_callable("noop", lambda: None, samples=3, p95_budget_ms=1000)
    assert result.passed is True
    assert result.sample_count == 3
    assert result.p50_ms <= result.p95_ms <= result.max_ms
