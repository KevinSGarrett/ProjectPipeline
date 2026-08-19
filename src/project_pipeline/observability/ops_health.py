from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from project_pipeline.command_center.models import HealthDimension, HealthState
from project_pipeline.observability.ops_models import (
    DEFAULT_FRESHNESS_SECONDS,
    REQUIRED_HEALTH_LAYERS,
    CostSample,
    HealthCalculation,
    HealthFactor,
    HealthLayerObservation,
    LayerState,
    WorkerResult,
    WorkerRunRecord,
)
from project_pipeline.observability.ops_store import OpsIntelligenceStore

_ORDER = {
    LayerState.UNKNOWN: 0,
    LayerState.HEALTHY: 1,
    LayerState.DEGRADED: 2,
    LayerState.UNHEALTHY: 3,
    LayerState.CRITICAL: 4,
}


def _parse_layer(payload_json: str) -> HealthLayerObservation:
    return HealthLayerObservation.model_validate(json.loads(payload_json))


def _parse_worker(payload_json: str) -> WorkerRunRecord:
    return WorkerRunRecord.model_validate(json.loads(payload_json))


def _parse_cost(payload_json: str) -> CostSample:
    return CostSample.model_validate(json.loads(payload_json))


def calculate_health(
    store: OpsIntelligenceStore,
    *,
    as_of_utc: datetime | None = None,
    freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS,
) -> HealthCalculation:
    as_of = (as_of_utc or datetime.now(UTC)).astimezone(UTC)
    freshness = timedelta(seconds=freshness_seconds)
    layers = [_parse_layer(str(row["payload_json"])) for row in store.list_kind("layer")]
    workers = [_parse_worker(str(row["payload_json"])) for row in store.list_kind("worker")]
    costs = [_parse_cost(str(row["payload_json"])) for row in store.list_kind("cost")]
    factors: list[HealthFactor] = []
    for layer_name in REQUIRED_HEALTH_LAYERS:
        current = [item for item in layers if item.layer == layer_name]
        if not current:
            factors.append(
                HealthFactor(
                    layer=layer_name,
                    state=LayerState.UNKNOWN,
                    stale=True,
                    missing=True,
                    contradictory=False,
                    reason="no current observation for required layer",
                    factors=("missing_observation",),
                )
            )
            continue
        latest_time = max(item.recorded_at_utc for item in current)
        latest = [item for item in current if item.recorded_at_utc == latest_time]
        states = {item.state for item in latest}
        contradictory = len(states) > 1
        stale = latest_time + freshness < as_of
        if contradictory:
            state = LayerState.UNHEALTHY
            reason = "contradictory current observations for the same layer"
            extra: tuple[str, ...] = ("contradictory_observations",)
        elif stale:
            state = LayerState.UNKNOWN
            reason = "latest observation exceeds freshness threshold"
            extra = ("stale_observation",)
        else:
            state = max(states, key=_ORDER.__getitem__)
            reason = latest[0].reason
            extra = latest[0].factors
        derived: list[str] = list(extra)
        if layer_name == "component" and any(
            item.result is WorkerResult.FAILED for item in workers
        ):
            if _ORDER[state] < _ORDER[LayerState.UNHEALTHY]:
                state = LayerState.UNHEALTHY
            derived.append("failed_worker_run")
            reason = "a recorded worker run failed"
        if layer_name == "budget" and costs:
            latest_cost = max(costs, key=lambda item: item.recorded_at_utc)
            if latest_cost.quota > 0 and (
                latest_cost.spend + latest_cost.reserved_lease > latest_cost.quota
            ):
                if _ORDER[state] < _ORDER[LayerState.UNHEALTHY]:
                    state = LayerState.UNHEALTHY
                derived.append("quota_exceeded")
                reason = "spend plus reserved lease exceeds quota"
        factors.append(
            HealthFactor(
                layer=layer_name,
                state=state,
                stale=stale,
                missing=False,
                contradictory=contradictory,
                reason=reason,
                factors=tuple(sorted(set(derived))),
            )
        )
    known = [item.state for item in factors if not item.missing and not item.stale]
    if any(item.missing or item.stale or item.contradictory for item in factors):
        if not known:
            overall = LayerState.UNKNOWN
        else:
            worst = max(known, key=_ORDER.__getitem__)
            overall = worst if _ORDER[worst] >= _ORDER[LayerState.UNHEALTHY] else LayerState.UNKNOWN
    else:
        overall = max((item.state for item in factors), key=_ORDER.__getitem__)
    return HealthCalculation(
        overall=overall,
        as_of_utc=as_of,
        freshness_seconds=freshness_seconds,
        layers=tuple(factors),
    )


def health_dimensions(calculation: HealthCalculation) -> tuple[HealthDimension, ...]:
    mapping = {
        LayerState.HEALTHY: HealthState.HEALTHY,
        LayerState.DEGRADED: HealthState.DEGRADED,
        LayerState.UNHEALTHY: HealthState.UNHEALTHY,
        LayerState.CRITICAL: HealthState.CRITICAL,
        LayerState.UNKNOWN: HealthState.UNKNOWN,
    }
    return tuple(
        HealthDimension(
            name=f"ops-{item.layer}",
            state=mapping[item.state],
            reason=item.reason,
            observed_at_utc=calculation.as_of_utc,
            stale=item.stale or item.missing,
        )
        for item in calculation.layers
    )
