from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from project_pipeline.domain.verification import VerificationCategory


class VerificationPolicy(BaseModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    project_id: str = "PROJECT-PIPELINE"
    profile: str = "local-pass16"
    required_categories: tuple[VerificationCategory, ...]
    browser_required_when_available: bool = True
    no_silent_required_skips: bool = True
    max_test_seconds: int = Field(default=1800, ge=30, le=7200)
    browser_load_p95_budget_ms: int = Field(default=2500, ge=50, le=60000)
    cli_help_p95_budget_ms: int = Field(default=1500, ge=50, le=60000)
    property_case_count: int = Field(default=100, ge=10, le=10000)
    property_seed: int = 16016
    performance_samples: int = Field(default=7, ge=3, le=100)
    screenshot_viewports: tuple[tuple[int, int], ...] = ((1280, 720), (390, 844))
    system_chromium_candidates: tuple[str, ...] = (
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
    )

    @model_validator(mode="after")
    def validate_policy(self) -> VerificationPolicy:
        if len(self.required_categories) != len(set(self.required_categories)):
            raise ValueError("verification required categories must be unique")
        if not self.required_categories:
            raise ValueError("verification requires at least one category")
        return self


def load_verification_policy(root: Path) -> VerificationPolicy:
    path = root / "config" / "verification_policy.json"
    if not path.exists():
        raise FileNotFoundError("config/verification_policy.json is missing")
    return VerificationPolicy.model_validate(json.loads(path.read_text(encoding="utf-8")))
