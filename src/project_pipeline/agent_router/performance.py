from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from project_pipeline.domain.agents import PerformanceObservation, PerformanceSummary


def summarize_performance(
    observations: Iterable[PerformanceObservation],
) -> dict[tuple[str, str], PerformanceSummary]:
    grouped: dict[tuple[str, str], list[PerformanceObservation]] = defaultdict(list)
    for item in observations:
        grouped[(item.target_id, item.capability_id)].append(item)
    result: dict[tuple[str, str], PerformanceSummary] = {}
    for key, items in grouped.items():
        n = len(items)
        costs = [item.cost_microunits for item in items if item.cost_microunits is not None]
        result[key] = PerformanceSummary(
            target_id=key[0],
            capability_id=key[1],
            sample_count=n,
            success_milli=round(sum(1 for item in items if item.success) * 1000 / n),
            quality_milli=round(sum(item.quality_milli for item in items) / n),
            mean_latency_ms=round(sum(item.latency_ms for item in items) / n),
            mean_cost_microunits=None if not costs else round(sum(costs) / len(costs)),
        )
    return result
