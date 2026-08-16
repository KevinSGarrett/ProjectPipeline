from __future__ import annotations

from typing import Literal

from pydantic import Field

from project_pipeline.domain.base import DomainModel


class AssurancePolicy(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    default_evidence_max_age_seconds: int = Field(default=30 * 24 * 3600, gt=0)
    high_risk_min_distinct_methods: int = Field(default=2, ge=1, le=10)
    critical_risk_min_distinct_methods: int = Field(default=3, ge=2, le=10)
    require_independent_review_for_high_risk: bool = True
    loop_max_attempts: int = Field(default=5, ge=1, le=100)
    loop_max_same_failure: int = Field(default=2, ge=1, le=20)
    loop_max_unchanged_outputs: int = Field(default=2, ge=1, le=20)
    verification_max_attempts: int = Field(default=8, ge=1, le=100)
    verification_max_evidence_records: int = Field(default=40, ge=1, le=1000)
    default_scope_change_budget: int = Field(default=3, ge=0, le=100)
