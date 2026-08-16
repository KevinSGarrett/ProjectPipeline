from __future__ import annotations

import re

REQUIREMENT_ID = re.compile(r"^REQ-[A-Z]+-[0-9]{4}$")
PLAN_ID = re.compile(r"^PLAN-[A-Z]+-[0-9]{3}$")
PLAN_SECTION_ID = re.compile(r"^(PLAN-[A-Z]+-[0-9]{3}):SEC-[0-9]{2}$")
ISSUE_ID = re.compile(r"^PP-(EPIC|STORY|TASK|SUBTASK|BUG|SPIKE)-[0-9]{6}$")
ACCEPTANCE_ID = re.compile(r"^AC-PP-[0-9]{6}-[0-9]{2}$")
EVIDENCE_ID = re.compile(r"^EVID-[0-9]{6}$")
DECISION_ID = re.compile(r"^ADR-[0-9]{4}$")
SOURCE_REFERENCE = re.compile(r"^(?:SRC-[0-9]{3}|GOV-[0-9]{3}):L[0-9]{6}(?:-L[0-9]{6})?$")


def require_match(pattern: re.Pattern[str], value: str, label: str) -> None:
    if not pattern.fullmatch(value):
        raise ValueError(f"Invalid {label}: {value}")
