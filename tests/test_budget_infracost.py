import json
from pathlib import Path

import pytest

from project_pipeline.budget.infracost import InfracostAdapter, parse_infracost_json


def test_parse_infracost_machine_readable_totals():
    payload = json.dumps(
        {
            "version": "0.2",
            "currency": "USD",
            "projects": [
                {
                    "breakdown": {
                        "totalMonthlyUsageCost": "2.25",
                        "resources": [{"costComponents": [{"priceNotFound": False}]}],
                    }
                }
            ],
            "totalHourlyCost": "1.25",
            "totalMonthlyCost": "100.50",
        }
    )
    result = parse_infracost_json(payload)
    assert result.available and result.complete
    assert result.total_monthly_microunits == 100_500_000
    assert result.total_monthly_usage_microunits == 2_250_000


def test_parse_infracost_unknown_price_is_incomplete_not_zero():
    payload = json.dumps(
        {
            "currency": "USD",
            "projects": [
                {"breakdown": {"resources": [{"costComponents": [{"priceNotFound": True}]}]}}
            ],
            "totalMonthlyCost": "5",
        }
    )
    result = parse_infracost_json(payload)
    assert result.available and not result.complete
    assert result.unknown_price_components == 1
    assert "unknown_price_components:1" in result.reasons


def test_parse_infracost_rejects_missing_currency():
    result = parse_infracost_json('{"totalMonthlyCost":"10"}')
    assert result.available and not result.complete
    assert result.total_monthly_microunits is None


def test_infracost_command_is_fixed_argv_and_root_confined(tmp_path: Path):
    target = tmp_path / "infra"
    target.mkdir()
    output = tmp_path / "out.json"
    adapter = InfracostAdapter()
    argv = adapter.build_command(tmp_path, target, output)
    assert argv[:2] == ("infracost", "breakdown")
    assert "--format=json" in argv
    with pytest.raises(ValueError):
        adapter.build_command(tmp_path, tmp_path.parent, output)


def test_infracost_live_read_is_deny_by_default(tmp_path: Path):
    target = tmp_path / "infra"
    target.mkdir()
    result = InfracostAdapter().estimate(tmp_path, target)
    assert not result.available
    assert result.reasons == ("external_cost_read_not_authorized",)
