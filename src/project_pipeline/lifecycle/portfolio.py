from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from project_pipeline.domain.lifecycle import PortfolioMode, ProjectPortfolioRegistration


@dataclass(frozen=True)
class PortfolioAllocation:
    project_id: str
    worker_slots: int
    share_percent: int
    score: float


class PortfolioGovernor:
    """Deterministic portfolio allocator. Project authority remains per-project."""

    def __init__(self, projects: tuple[ProjectPortfolioRegistration, ...]) -> None:
        ids = [p.project_id for p in projects]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate project_id")
        self.projects = projects

    @staticmethod
    def _score(p: ProjectPortfolioRegistration, now: datetime) -> float:
        deadline_pressure = 0.0
        if p.deadline_at_utc:
            seconds = max(1.0, (p.deadline_at_utc - now).total_seconds())
            deadline_pressure = min(50.0, 86400.0 / seconds * 20.0)
        return (
            p.priority * 1.8
            + p.operator_importance
            + min(50, p.starvation_age_seconds / 3600)
            + deadline_pressure
        )

    def allocate(
        self,
        *,
        total_worker_slots: int,
        mode: PortfolioMode = PortfolioMode.BALANCED_PORTFOLIO,
        favored_project_id: str | None = None,
    ) -> tuple[PortfolioAllocation, ...]:
        if total_worker_slots < 0:
            raise ValueError("total_worker_slots must be non-negative")
        if not self.projects:
            return ()
        now = datetime.now(UTC)
        scores = {p.project_id: max(1.0, self._score(p, now)) for p in self.projects}
        if mode in {PortfolioMode.DEADLINE_SPRINT, PortfolioMode.EXCLUSIVE}:
            if favored_project_id not in scores:
                raise ValueError("favored_project_id required and must exist")
            scores[favored_project_id] *= 2.5 if mode == PortfolioMode.DEADLINE_SPRINT else 8.0
        allocations = {
            p.project_id: min(p.guaranteed_worker_slots, total_worker_slots) for p in self.projects
        }
        used = sum(allocations.values())
        while used < total_worker_slots:
            candidates = []
            for p in self.projects:
                cap = max(
                    p.guaranteed_worker_slots,
                    int(total_worker_slots * p.max_worker_share_percent / 100),
                )
                if allocations[p.project_id] < cap:
                    candidates.append(p)
            if not candidates:
                break
            pick = max(
                candidates,
                key=lambda p: (
                    scores[p.project_id] / (allocations[p.project_id] + 1),
                    p.project_id,
                ),
            )
            allocations[pick.project_id] += 1
            used += 1
        result = []
        for p in sorted(self.projects, key=lambda x: x.project_id):
            slots = allocations[p.project_id]
            result.append(
                PortfolioAllocation(
                    p.project_id,
                    slots,
                    round(slots / max(1, total_worker_slots) * 100),
                    scores[p.project_id],
                )
            )
        return tuple(result)
