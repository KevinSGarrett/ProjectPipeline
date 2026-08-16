from project_pipeline.upstream_integrations.resilience import activation_snapshot


def test_resilience_upstream_adapters_are_discovery_only():
    rows = activation_snapshot()
    assert {x["upstream_id"] for x in rows} == {
        "UPSTREAM-040",
        "UPSTREAM-068",
        "UPSTREAM-072",
        "UPSTREAM-082",
        "UPSTREAM-090",
        "UPSTREAM-093",
    }
    assert all(x["live_qualification_claim"] is False for x in rows)
