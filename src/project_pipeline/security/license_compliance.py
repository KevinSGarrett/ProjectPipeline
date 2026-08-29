"""Deterministic license-compliance authority for release SBOM components.

Compliance records are derived only from machine-verifiable inputs: the
component identity, the SPDX policy, a resolvable provenance digest, and a
generated notice record. A component that cannot satisfy every one of those
inputs receives no record at all, so release-mode evaluation keeps failing
closed rather than accepting a fabricated legal approval.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_pipeline.domain.security import SBOMComponentCompliance

PUBLIC_POLICY_PATH = "config/license_policy.json"
PRIVATE_POLICY_PATH = "provenance/license_policy.json"
PUBLIC_NOTICE_PATH = "third_party/NOTICES.generated.json"
PRIVATE_NOTICE_PATH = "provenance/upstream_notices.generated.json"

# SPDX identifiers accepted by long-standing policy. Anything beyond this set is
# a Tier-I policy change and must carry executable evidence before the gate will
# treat it as automatically approved.
BASELINE_AUTOMATIC_APPROVAL_SPDX = frozenset(
    {
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "MIT",
        "MIT OR Apache-2.0",
        "PostgreSQL",
    }
)

REQUIRED_TIER_ONE_EVIDENCE_FIELDS = (
    "spdx_id",
    "tier",
    "metadata_authority",
    "license_text_authority",
    "obligations",
)

# Tier-I evidence must name a license text committed to the repository so its
# recorded digest can be recomputed at gate time. A digest that only describes a
# file inside somebody's virtual environment proves nothing here.
REQUIRED_LICENSE_TEXT_AUTHORITY_FIELDS = ("repository_path", "sha256", "bytes")

_FIELD_SEPARATOR = "\x1f"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def notice_key(component_type: str, name: str, version: str) -> str:
    return f"{component_type}:{name}@{version}"


@dataclass(frozen=True)
class LicenseComplianceAuthority:
    """Resolves compliance records from policy and notice authority."""

    policy_sha256: str
    notices_sha256: str
    automatic_approval_spdx: frozenset[str]
    review_required_spdx: frozenset[str]
    prohibited_spdx: frozenset[str]
    rules: tuple[str, ...]
    notices: dict[str, dict[str, Any]]

    def is_automatically_approved(self, license_expression: str) -> bool:
        """Approve an SPDX expression only through accepted automatic policy.

        A disjunction is approved when every alternative is independently
        approved, because the recipient may elect any single branch. No other
        expression form is widened.
        """

        expression = (license_expression or "").strip()
        if not expression:
            return False
        if expression in self.prohibited_spdx or expression in self.review_required_spdx:
            return False
        if expression in self.automatic_approval_spdx:
            return True
        if " OR " in expression and " AND " not in expression:
            alternatives = [part.strip().strip("()") for part in expression.split(" OR ")]
            return bool(alternatives) and all(
                alternative in self.automatic_approval_spdx for alternative in alternatives
            )
        return False

    def resolve_notice(self, reference: str) -> dict[str, Any] | None:
        _, _, key = reference.partition("#")
        return self.notices.get(key)

    def modification_obligation(self, license_expression: str) -> str:
        """Return the obligation class the policy assigns to an approved license."""

        if license_expression.startswith("Apache-2.0"):
            return "RETAIN_NOTICE_AND_STATE_CHANGES"
        if license_expression == "PostgreSQL":
            return "RETAIN_NOTICE"
        return "RETAIN_NOTICE_AND_COPYRIGHT"

    def _identity_digest(
        self,
        *,
        name: str,
        version: str,
        component_type: str,
        license_expression: str,
        source: str,
        digest: str,
    ) -> str:
        return _sha256(
            _FIELD_SEPARATOR.join(
                (
                    self.policy_sha256,
                    self.notices_sha256,
                    component_type,
                    name,
                    version,
                    license_expression,
                    source,
                    digest,
                )
            )
        )

    def compliance_for(
        self,
        *,
        name: str,
        version: str,
        component_type: str,
        license_expression: str,
        source: str | None,
        digest: str | None,
    ) -> SBOMComponentCompliance | None:
        """Build a compliance record, or return None so the gate fails closed."""

        expression = (license_expression or "").strip()
        if not self.is_automatically_approved(expression):
            return None
        if not source or not digest:
            return None
        key = notice_key(component_type, name, version)
        notice = self.notices.get(key)
        if notice is None:
            return None
        if notice.get("license") != expression:
            return None
        # The notice must describe the same artifact the SBOM evaluated.
        if notice.get("digest") != digest:
            return None
        if notice.get("source") != source:
            return None
        identity = self._identity_digest(
            name=name,
            version=version,
            component_type=component_type,
            license_expression=expression,
            source=source,
            digest=digest,
        )
        obligation = self.modification_obligation(expression)
        return SBOMComponentCompliance(
            notice_reference=f"{PUBLIC_NOTICE_PATH}#{key}",
            permitted_use_record_id=f"LPUR-{identity[:40].upper()}",
            modification_obligation_record_id=(
                f"LMOR-{obligation}-{_sha256(obligation + identity)[:24].upper()}"
            ),
            provenance_reference_id=f"LPRV-{_sha256(source + _FIELD_SEPARATOR + digest)[:40].upper()}",
        )

    def verify(
        self,
        record: SBOMComponentCompliance,
        *,
        name: str,
        version: str,
        component_type: str,
        license_expression: str,
        source: str | None,
        digest: str | None,
    ) -> bool:
        """Recompute the record and reject any tampered field."""

        expected = self.compliance_for(
            name=name,
            version=version,
            component_type=component_type,
            license_expression=license_expression,
            source=source,
            digest=digest,
        )
        if expected is None:
            return False
        return (
            record.notice_reference == expected.notice_reference
            and record.permitted_use_record_id == expected.permitted_use_record_id
            and record.modification_obligation_record_id
            == expected.modification_obligation_record_id
            and record.provenance_reference_id == expected.provenance_reference_id
        )


def _load_policy(root: Path) -> tuple[dict[str, Any], str]:
    # The tracked public policy is canonical: it is reviewed, tested, and
    # identical for public and provisioned checkouts. A private copy may exist
    # for historical reasons but must not silently diverge from it.
    for relative in (PUBLIC_POLICY_PATH, PRIVATE_POLICY_PATH):
        path = root / relative
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            return json.loads(text), _sha256(_canonical(json.loads(text)))
    # Without a policy there is no authority to approve anything, so return an
    # empty one. Every component then fails closed instead of raising, which
    # keeps synthetic and partial roots evaluable.
    return {}, _sha256("no-license-policy")


def _load_notices(root: Path) -> tuple[dict[str, dict[str, Any]], str]:
    notices: dict[str, dict[str, Any]] = {}
    for relative in (PUBLIC_NOTICE_PATH, PRIVATE_NOTICE_PATH):
        path = root / relative
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        for entry in document.get("entries", []):
            key = notice_key(entry["component_type"], entry["name"], entry["version"])
            notices[key] = entry
    # Hash the full entry bodies, not just their keys. Hashing keys alone would
    # leave compliance records verifiable after notice metadata was edited.
    return notices, _sha256(_canonical([(key, notices[key]) for key in sorted(notices)]))


def _license_text_matches(root: Path, text_authority: dict[str, Any]) -> bool:
    """Recompute the recorded license-text digest from the committed bytes."""

    relative = str(text_authority["repository_path"])
    # A path that escapes the repository is not repository-controlled authority.
    # Rejecting only "absolute" and ".." would still admit a Windows
    # drive-relative path such as "C:license.txt", or a symlink whose target
    # lives outside the tree, so containment is confirmed after resolution.
    candidate = Path(relative)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        return False
    if ".." in candidate.parts:
        return False
    artifact = root / candidate
    if not artifact.is_file():
        return False
    try:
        resolved = artifact.resolve(strict=True)
    except OSError:
        return False
    if not resolved.is_relative_to(root.resolve()):
        return False
    payload = resolved.read_bytes()
    if len(payload) != int(text_authority["bytes"]):
        return False
    return hashlib.sha256(payload).hexdigest() == str(text_authority["sha256"])


def _evidenced_automatic_approvals(root: Path, policy: dict[str, Any]) -> frozenset[str]:
    """Return approvals the policy may actually exercise.

    A declared approval beyond the baseline is only honoured when the referenced
    evidence document records it as a Tier-I change with metadata authority,
    license-text authority, and obligations. Declaring an identifier in policy
    alone is therefore not sufficient to approve it.
    """

    declared = {str(item).strip() for item in policy.get("automatic_approval_spdx", [])}
    beyond_baseline = declared - BASELINE_AUTOMATIC_APPROVAL_SPDX
    if not beyond_baseline:
        return frozenset(declared)

    reference = policy.get("automatic_approval_evidence")
    evidence_path = root / str(reference) if reference else None
    if evidence_path is None or not evidence_path.is_file():
        return frozenset(declared - beyond_baseline)

    document = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidenced = set()
    for record in document.get("automatic_approval_additions", []):
        if any(not record.get(field) for field in REQUIRED_TIER_ONE_EVIDENCE_FIELDS):
            continue
        if record.get("tier") != "TIER_I_POLICY_CHANGE":
            continue
        text_authority = record.get("license_text_authority") or {}
        if any(not text_authority.get(field) for field in REQUIRED_LICENSE_TEXT_AUTHORITY_FIELDS):
            continue
        if not _license_text_matches(root, text_authority):
            continue
        evidenced.add(str(record["spdx_id"]).strip())
    return frozenset((declared - beyond_baseline) | (beyond_baseline & evidenced))


def _policy_authority_digest(root: Path, policy: dict[str, Any], policy_sha256: str) -> str:
    """Fold the referenced evidence document into the policy identity.

    Compliance ids are derived from this digest, so editing Tier-I evidence
    invalidates every record that depended on it instead of silently swapping
    the justification underneath an already-verifiable approval.
    """

    reference = policy.get("automatic_approval_evidence")
    if not reference:
        return policy_sha256
    evidence_path = root / str(reference)
    if not evidence_path.is_file():
        return _sha256(_canonical([policy_sha256, "missing-evidence"]))
    evidence_sha256 = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    return _sha256(_canonical([policy_sha256, evidence_sha256]))


def license_compliance_authority(root: Path) -> LicenseComplianceAuthority:
    policy, policy_sha256 = _load_policy(root)
    notices, notices_sha256 = _load_notices(root)
    return LicenseComplianceAuthority(
        policy_sha256=_policy_authority_digest(root, policy, policy_sha256),
        notices_sha256=notices_sha256,
        automatic_approval_spdx=_evidenced_automatic_approvals(root, policy),
        review_required_spdx=frozenset(
            str(item).strip() for item in policy.get("review_required_spdx", [])
        ),
        prohibited_spdx=frozenset(str(item).strip() for item in policy.get("prohibited_spdx", [])),
        rules=tuple(str(item).strip() for item in policy.get("rules", [])),
        notices=notices,
    )


def build_notice_document(*, entries: list[dict[str, Any]], scope: str) -> dict[str, Any]:
    """Build the deterministic notice document written to disk."""

    ordered = sorted(
        entries, key=lambda item: (item["component_type"], item["name"], item["version"])
    )
    return {
        "schema_version": "1.0.0",
        "scope": scope,
        "entries": ordered,
        "entries_sha256": _sha256(_canonical(ordered)),
    }
