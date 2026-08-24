from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from project_pipeline.context_engine.firewall import evaluate_candidate
from project_pipeline.domain.context import (
    ContextCandidate,
    ContextItem,
    ContextPack,
    ContextPolicy,
    ContextSelection,
    ContextSourceKind,
    ContextTelemetry,
    CoverageReport,
    DelegationEnvelope,
    ProviderEgress,
    ReviewerPackage,
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")


def _id(prefix: str, *parts: str) -> str:
    return f"{prefix}-{hashlib.sha256(chr(31).join(parts).encode()).hexdigest()[:20].upper()}"


class ContextCompilationError(RuntimeError):
    """Raised when context cannot satisfy deterministic compilation policy."""


class ContextCompiler:
    def compile(
        self,
        envelope: DelegationEnvelope,
        selection: ContextSelection,
        candidates: tuple[ContextCandidate, ...],
        policy: ContextPolicy,
        *,
        provider_egress: ProviderEgress = ProviderEgress.LOCAL_ONLY,
        generated_at_utc: datetime | None = None,
    ) -> ContextPack:
        generated = generated_at_utc or datetime.now(UTC)
        by_key = {c.context_key: c for c in candidates}
        items = []
        omissions = list(selection.omitted_keys)
        stale = []
        warnings = []
        redactions = 0
        for key in selection.selected_keys:
            candidate = by_key[key]
            expected = envelope.expected_revisions.get(key)
            is_stale = bool(expected and expected != candidate.revision_id)
            if not is_stale:
                age = (generated - candidate.observed_at_utc).total_seconds()
                is_stale = age > policy.max_age_seconds
            if is_stale:
                stale.append(key)
                if key in envelope.required_context_keys or not policy.allow_stale_optional:
                    omissions.append(key)
                    continue
                warnings.append(f"STALE_OPTIONAL_INCLUDED:{key}")
            fw = evaluate_candidate(candidate, policy, provider_egress=provider_egress)
            redactions += fw.redaction_count
            warnings.extend(f"{key}:{r}" for r in fw.reasons)
            if not fw.allowed:
                omissions.append(key)
                continue
            item = ContextItem.from_candidate(candidate, content=fw.content)
            items.append(item)
        # Required coverage is about usable included context, not merely selection.
        included = {i.context_key for i in items}
        missing = tuple(k for k in envelope.required_context_keys if k not in included)
        required_count = len(envelope.required_context_keys)
        represented = required_count - len(missing)
        coverage = CoverageReport(
            required_count=required_count,
            represented_count=represented,
            missing_keys=missing,
            score=1.0 if required_count == 0 else represented / required_count,
        )
        if coverage.score < policy.min_coverage_score:
            raise ContextCompilationError(
                f"required context coverage {coverage.score:.3f} below policy minimum {policy.min_coverage_score:.3f}: {missing}"
            )
        total_chars = sum(len(i.content) for i in items)
        if total_chars > policy.max_chars:
            raise ContextCompilationError(
                f"context pack size {total_chars} exceeds maximum {policy.max_chars}"
            )
        payload = {
            "delegation_id": envelope.delegation_id,
            "policy_version": policy.policy_version,
            "items": [i.model_dump(mode="json") for i in items],
            "coverage": coverage.model_dump(mode="json"),
            "stale_keys": stale,
            "redaction_count": redactions,
            "omissions": sorted(set(omissions)),
            "warnings": warnings,
            "total_chars": total_chars,
        }
        digest = hashlib.sha256(_canonical(payload)).hexdigest()
        return ContextPack(
            pack_id=_id("CTXPACK", digest),
            delegation_id=envelope.delegation_id,
            policy_version=policy.policy_version,
            generated_at_utc=generated,
            items=tuple(items),
            coverage=coverage,
            stale_keys=tuple(stale),
            redaction_count=redactions,
            omissions=tuple(sorted(set(omissions))),
            warnings=tuple(warnings),
            total_chars=total_chars,
            content_sha256=digest,
        )

    def telemetry(self, pack: ContextPack) -> ContextTelemetry:
        trusts = Counter(i.trust.value for i in pack.items)
        return ContextTelemetry(
            pack_id=pack.pack_id,
            item_count=len(pack.items),
            total_chars=pack.total_chars,
            source_count=len({i.source_reference or i.context_key for i in pack.items}),
            coverage_score=pack.coverage.score,
            trust_counts=dict(sorted(trusts.items())),
            stale_count=len(pack.stale_keys),
            redaction_count=pack.redaction_count,
            omission_count=len(pack.omissions),
        )

    def reviewer_package(self, pack: ContextPack) -> ReviewerPackage:
        def keys(kinds: set[ContextSourceKind]) -> tuple[str, ...]:
            return tuple(i.context_key for i in pack.items if i.kind in kinds)

        diff = keys({ContextSourceKind.DIFF})
        sources = keys(
            {
                ContextSourceKind.SOURCE,
                ContextSourceKind.SOURCE_FILE,
                ContextSourceKind.REQUIREMENT,
                ContextSourceKind.PLAN,
            }
        )
        tests = keys({ContextSourceKind.TEST})
        evidence = keys({ContextSourceKind.EVIDENCE})
        rubric = keys({ContextSourceKind.REVIEW_RUBRIC})
        if not (diff and sources and tests and evidence and rubric):
            missing = [
                n
                for n, v in (
                    ("diff", diff),
                    ("sources", sources),
                    ("tests", tests),
                    ("evidence", evidence),
                    ("rubric", rubric),
                )
                if not v
            ]
            raise ContextCompilationError(f"disconnected reviewer package lacks: {missing}")
        rid = _id(
            "CTXREVIEW", pack.pack_id, "|".join([*diff, *sources, *tests, *evidence, *rubric])
        )
        return ReviewerPackage(
            review_package_id=rid,
            context_pack_id=pack.pack_id,
            diff_keys=diff,
            source_keys=sources,
            test_keys=tests,
            evidence_keys=evidence,
            rubric_keys=rubric,
        )
