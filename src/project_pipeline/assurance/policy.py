from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from project_pipeline.domain.base import DomainModel


class DeliveryProgressPolicy(DomainModel):
    objective_progress_required: bool = True
    lifecycle_transitions_are_progress: bool = False
    lifecycle_only_pull_requests: Literal["DENY"] = "DENY"
    minimum_reconciliation_batch_items: int = Field(default=3, ge=2, le=100)
    maximum_noncritical_administrative_ratio_milli: int = Field(default=100, ge=0, le=1000)
    already_implemented_selection: Literal["RECONCILIATION_REQUIRED"] = "RECONCILIATION_REQUIRED"
    expensive_gate_boundary: Literal["COHESIVE_VERTICAL_SLICE"] = "COHESIVE_VERTICAL_SLICE"


class CycleWorkloadPolicy(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    baseline_id: Literal["CURSOR_CYCLES_001_015_HIGH_WATER"] = "CURSOR_CYCLES_001_015_HIGH_WATER"
    independently_validated_baseline_score: int = Field(default=24, ge=1, le=1000)
    independently_validated_baseline_units: int = Field(default=7, ge=1, le=1000)
    multiplier_milli: Literal[2000] = 2000
    minimum_score: int = Field(default=48, ge=1, le=4000)
    minimum_units: int = Field(default=14, ge=1, le=4000)
    maximum_unit_weight: Literal[4] = 4
    non_compounding: Literal[True] = True
    administrative_credit: Literal[0] = 0
    endgame_saturation_required_when_below_minimum: Literal[True] = True

    @model_validator(mode="after")
    def validate_noncompounding_double(self) -> CycleWorkloadPolicy:
        expected_score = (
            self.independently_validated_baseline_score * self.multiplier_milli
        ) // 1000
        expected_units = (
            self.independently_validated_baseline_units * self.multiplier_milli
        ) // 1000
        if self.minimum_score != expected_score:
            raise ValueError("minimum_score must equal the mechanically doubled baseline score")
        if self.minimum_units != expected_units:
            raise ValueError("minimum_units must equal the mechanically doubled baseline units")
        return self


class AssurancePolicy(DomainModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    default_evidence_max_age_seconds: int = Field(default=30 * 24 * 3600, gt=0)
    high_risk_min_distinct_methods: int = Field(default=2, ge=1, le=10)
    critical_risk_min_distinct_methods: int = Field(default=3, ge=2, le=10)
    require_independent_review_for_high_risk: bool = True
    loop_max_attempts: int = Field(default=5, ge=1, le=100)
    loop_max_same_failure: int = Field(default=2, ge=1, le=20)
    loop_max_unchanged_outputs: int = Field(default=2, ge=1, le=20)
    loop_max_progressless_cycles: int = Field(default=2, ge=1, le=20)
    verification_max_attempts: int = Field(default=8, ge=1, le=100)
    verification_max_evidence_records: int = Field(default=40, ge=1, le=1000)
    default_scope_change_budget: int = Field(default=3, ge=0, le=100)
    delivery_progress: DeliveryProgressPolicy = Field(default_factory=DeliveryProgressPolicy)
    cycle_workload: CycleWorkloadPolicy = Field(default_factory=CycleWorkloadPolicy)
