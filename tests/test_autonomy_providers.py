from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_pipeline.autonomy_runtime.providers import (
    AutonomyProviderRuntime,
    BudgetDecision,
    ProviderQualification,
    contains_secret_shaped,
    fake_provider,
    local_test_provider,
)


def _budget(allowed: bool = True) -> BudgetDecision:
    return BudgetDecision(
        allowed=allowed, reason="ok" if allowed else "denied", decision_id="BUD-1"
    )


def test_local_provider_success_and_replay(tmp_path: Path) -> None:
    runtime = AutonomyProviderRuntime(tmp_path / "provider.db")
    provider = local_test_provider()
    kwargs = {
        "provider": provider,
        "command": [sys.executable, "-c", "print('provider-ok')"],
        "working_directory": tmp_path,
        "task_id": "PP-TASK-000384",
        "worker_id": "worker-1",
        "model_or_tool": "local-python",
        "budget": _budget(),
        "lease_fence": "fence-1",
        "expected_fence": "fence-1",
        "idempotency_key": "pp384-1",
    }
    first = runtime.dispatch(**kwargs)
    second = runtime.dispatch(**kwargs)
    assert first["status"] == "SUCCEEDED"
    assert first["receipt_sha256"] == second["receipt_sha256"]
    assert first["live_qualification"] is True
    runtime.close()


def test_provider_denials(tmp_path: Path) -> None:
    runtime = AutonomyProviderRuntime(tmp_path / "provider.db")
    expired = ProviderQualification(
        provider_id="provider:expired",
        label="local",
        qualified=True,
        expires_at_utc=datetime.now(UTC) - timedelta(hours=1),
        attestation_id="ATT-OLD",
        capabilities=("local-subprocess",),
    )
    with pytest.raises(ValueError, match="expired"):
        runtime.dispatch(
            provider=expired,
            command=[sys.executable, "-c", "print('x')"],
            working_directory=tmp_path,
            task_id="T",
            worker_id="w",
            model_or_tool="local",
            budget=_budget(),
            lease_fence="f",
            expected_fence="f",
            idempotency_key="exp",
        )
    with pytest.raises(ValueError, match="budget denied"):
        runtime.dispatch(
            provider=local_test_provider(),
            command=[sys.executable, "-c", "print('x')"],
            working_directory=tmp_path,
            task_id="T",
            worker_id="w",
            model_or_tool="local",
            budget=_budget(False),
            lease_fence="f",
            expected_fence="f",
            idempotency_key="bud",
        )
    with pytest.raises(ValueError, match="stale fence"):
        runtime.dispatch(
            provider=local_test_provider(),
            command=[sys.executable, "-c", "print('x')"],
            working_directory=tmp_path,
            task_id="T",
            worker_id="w",
            model_or_tool="local",
            budget=_budget(),
            lease_fence="old",
            expected_fence="new",
            idempotency_key="fence",
        )
    with pytest.raises(ValueError, match="secret-shaped"):
        runtime.dispatch(
            provider=local_test_provider(),
            command=[sys.executable, "-c", "print('x')"],
            working_directory=tmp_path,
            task_id="T",
            worker_id="w",
            model_or_tool="local",
            budget=_budget(),
            lease_fence="f",
            expected_fence="f",
            idempotency_key="secret",
            extra={"token": "sk-abcdefghijklmnopqrstuvwxyz"},
        )
    with pytest.raises(ValueError, match="fake provider cannot satisfy live"):
        runtime.dispatch(
            provider=fake_provider(),
            command=[sys.executable, "-c", "print('x')"],
            working_directory=tmp_path,
            task_id="T",
            worker_id="w",
            model_or_tool="fake",
            budget=_budget(),
            lease_fence="f",
            expected_fence="f",
            idempotency_key="fake",
            extra={"claim_live": True},
        )
    runtime.close()


def test_conflicting_idempotency_and_redaction(tmp_path: Path) -> None:
    assert contains_secret_shaped({"api_key": "abc"})
    assert not contains_secret_shaped({"note": "ok"})
    runtime = AutonomyProviderRuntime(tmp_path / "provider.db")
    runtime.dispatch(
        provider=local_test_provider(),
        command=[sys.executable, "-c", "print('one')"],
        working_directory=tmp_path,
        task_id="T",
        worker_id="w",
        model_or_tool="local",
        budget=_budget(),
        lease_fence="f",
        expected_fence="f",
        idempotency_key="same",
    )
    with pytest.raises(ValueError, match="idempotency key conflict"):
        runtime.dispatch(
            provider=local_test_provider(),
            command=[sys.executable, "-c", "print('two')"],
            working_directory=tmp_path,
            task_id="T",
            worker_id="w",
            model_or_tool="local",
            budget=_budget(),
            lease_fence="f",
            expected_fence="f",
            idempotency_key="same",
        )
    runtime.close()
