from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from project_pipeline.ids import (
    ACCEPTANCE_ID,
    DECISION_ID,
    EVIDENCE_ID,
    ISSUE_ID,
    PLAN_ID,
    PLAN_SECTION_ID,
    REQUIREMENT_ID,
)

PROJECT_ID = re.compile(r"^PROJECT-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
MIGRATION_ID = re.compile(r"^PPDB-[0-9]{4}$")
TRACE_LINK_ID = re.compile(r"^TRACE-[A-F0-9]{20}$")
TRANSITION_ID = re.compile(r"^TRANS-[A-F0-9]{20}$")
CATALOG_IMPORT_ID = re.compile(r"^IMPORT-[A-F0-9]{20}$")
MUTATION_ID = re.compile(r"^MUT-[A-F0-9]{20}$")
COMPILATION_ID = re.compile(r"^COMP-[A-F0-9]{20}$")
BOOTSTRAP_ID = re.compile(r"^BOOT-[A-F0-9]{20}$")
GAP_ID = re.compile(r"^GAP-[A-F0-9]{20}$")


class IdentifierKind(StrEnum):
    PROJECT = "PROJECT"
    REQUIREMENT = "REQUIREMENT"
    ISSUE = "ISSUE"
    PLAN = "PLAN"
    PLAN_SECTION = "PLAN_SECTION"
    ACCEPTANCE = "ACCEPTANCE"
    EVIDENCE = "EVIDENCE"
    DECISION = "DECISION"
    MIGRATION = "MIGRATION"
    TRACE_LINK = "TRACE_LINK"
    TRANSITION = "TRANSITION"
    CATALOG_IMPORT = "CATALOG_IMPORT"
    MUTATION = "MUTATION"
    COMPILATION = "COMPILATION"
    BOOTSTRAP = "BOOTSTRAP"
    GAP = "GAP"


_PATTERNS: dict[IdentifierKind, re.Pattern[str]] = {
    IdentifierKind.PROJECT: PROJECT_ID,
    IdentifierKind.REQUIREMENT: REQUIREMENT_ID,
    IdentifierKind.ISSUE: ISSUE_ID,
    IdentifierKind.PLAN: PLAN_ID,
    IdentifierKind.PLAN_SECTION: PLAN_SECTION_ID,
    IdentifierKind.ACCEPTANCE: ACCEPTANCE_ID,
    IdentifierKind.EVIDENCE: EVIDENCE_ID,
    IdentifierKind.DECISION: DECISION_ID,
    IdentifierKind.MIGRATION: MIGRATION_ID,
    IdentifierKind.TRACE_LINK: TRACE_LINK_ID,
    IdentifierKind.TRANSITION: TRANSITION_ID,
    IdentifierKind.CATALOG_IMPORT: CATALOG_IMPORT_ID,
    IdentifierKind.MUTATION: MUTATION_ID,
    IdentifierKind.COMPILATION: COMPILATION_ID,
    IdentifierKind.BOOTSTRAP: BOOTSTRAP_ID,
    IdentifierKind.GAP: GAP_ID,
}


@dataclass(frozen=True, slots=True)
class DomainIdentifier:
    kind: IdentifierKind
    value: str

    def __post_init__(self) -> None:
        pattern = _PATTERNS[self.kind]
        if not pattern.fullmatch(self.value):
            raise ValueError(f"Invalid {self.kind.value.lower()} identifier: {self.value}")

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, value: str, *, expected_kind: IdentifierKind | None = None) -> DomainIdentifier:
        if expected_kind is not None:
            return cls(expected_kind, value)
        matches = [kind for kind, pattern in _PATTERNS.items() if pattern.fullmatch(value)]
        if len(matches) != 1:
            raise ValueError(f"Identifier is unknown or ambiguous: {value}")
        return cls(matches[0], value)


def normalize_identifier_component(value: str) -> str:
    value = re.sub(r"[‐‑‒–—―−]+", "-", value)  # noqa: RUF001 - normalize Unicode dashes
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    component = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").upper()
    if not component:
        raise ValueError("identifier component cannot be empty after normalization")
    return component


def project_identifier(name: str) -> DomainIdentifier:
    component = normalize_identifier_component(name)
    if component.startswith("PROJECT-"):
        component = component.removeprefix("PROJECT-")
    return DomainIdentifier(IdentifierKind.PROJECT, f"PROJECT-{component}")


def deterministic_identifier(kind: IdentifierKind, *parts: str) -> DomainIdentifier:
    if kind not in {
        IdentifierKind.TRACE_LINK,
        IdentifierKind.TRANSITION,
        IdentifierKind.CATALOG_IMPORT,
        IdentifierKind.MUTATION,
        IdentifierKind.COMPILATION,
        IdentifierKind.BOOTSTRAP,
        IdentifierKind.GAP,
    }:
        raise ValueError(f"Deterministic digest identifiers are unsupported for {kind.value}")
    canonical = "\x1f".join(part.strip() for part in parts)
    if not canonical or any(not part.strip() for part in parts):
        raise ValueError("deterministic identifier parts must be non-empty")
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20].upper()
    prefix = {
        IdentifierKind.TRACE_LINK: "TRACE",
        IdentifierKind.TRANSITION: "TRANS",
        IdentifierKind.CATALOG_IMPORT: "IMPORT",
        IdentifierKind.MUTATION: "MUT",
        IdentifierKind.COMPILATION: "COMP",
        IdentifierKind.BOOTSTRAP: "BOOT",
        IdentifierKind.GAP: "GAP",
    }[kind]
    return DomainIdentifier(kind, f"{prefix}-{digest}")


def validate_identifier(value: str, kind: IdentifierKind) -> str:
    return DomainIdentifier(kind, value).value
