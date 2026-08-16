from __future__ import annotations

from project_pipeline.domain.scheduler import (
    BackpressureDecision,
    BackpressureMode,
    BackpressurePolicy,
    BackpressureSignals,
)


def evaluate_backpressure(
    signals: BackpressureSignals,
    policy: BackpressurePolicy | None = None,
) -> BackpressureDecision:
    policy = policy or BackpressurePolicy()
    reasons: list[str] = []

    halt = False
    if signals.queue_depth >= policy.halt_queue_depth:
        halt = True
        reasons.append("queue_depth_halt")
    if (
        signals.memory_used_percent is not None
        and signals.memory_used_percent >= policy.memory_halt_percent
    ):
        halt = True
        reasons.append("memory_pressure_halt")
    if (
        signals.disk_free_percent is not None
        and signals.disk_free_percent <= policy.disk_halt_free_percent
    ):
        halt = True
        reasons.append("disk_pressure_halt")
    if halt:
        return BackpressureDecision(
            mode=BackpressureMode.HALT_NEW_WORK,
            lane_fraction=0,
            admit_new_work=False,
            reasons=tuple(reasons),
        )

    brownout = False
    if signals.queue_depth >= policy.brownout_queue_depth:
        brownout = True
        reasons.append("queue_depth_brownout")
    if signals.scheduler_queue_lag_seconds >= policy.brownout_lag_seconds:
        brownout = True
        reasons.append("scheduler_lag_brownout")
    if (
        signals.memory_used_percent is not None
        and signals.memory_used_percent >= policy.memory_brownout_percent
    ):
        brownout = True
        reasons.append("memory_pressure_brownout")
    if (
        signals.disk_free_percent is not None
        and signals.disk_free_percent <= policy.disk_brownout_free_percent
    ):
        brownout = True
        reasons.append("disk_pressure_brownout")
    if signals.retry_storm_count >= policy.retry_storm_brownout_count:
        brownout = True
        reasons.append("retry_storm_brownout")
    if brownout:
        return BackpressureDecision(
            mode=BackpressureMode.BROWNOUT,
            lane_fraction=0,
            admit_new_work=False,
            reasons=tuple(reasons),
        )

    congested = False
    if signals.queue_depth >= policy.congested_queue_depth:
        congested = True
        reasons.append("queue_depth_congested")
    if signals.scheduler_queue_lag_seconds >= policy.congested_lag_seconds:
        congested = True
        reasons.append("scheduler_lag_congested")
    if congested:
        return BackpressureDecision(
            mode=BackpressureMode.CONGESTED,
            lane_fraction=policy.congested_lane_fraction,
            admit_new_work=True,
            reasons=tuple(reasons),
        )

    return BackpressureDecision(
        mode=BackpressureMode.NORMAL, lane_fraction=1, admit_new_work=True, reasons=()
    )
