from __future__ import annotations

import json
from pathlib import Path

_REQUIRED = (
    "src/project_pipeline/domain/security.py",
    "src/project_pipeline/security/identity.py",
    "src/project_pipeline/security/policy.py",
    "src/project_pipeline/security/secrets.py",
    "src/project_pipeline/security/backends.py",
    "src/project_pipeline/security/supply_chain.py",
    "src/project_pipeline/security/persistence.py",
    "config/security_policy.json",
    "config/root_of_trust.json",
    "provenance/pass_17_security_upstream_gate.json",
    "database/migrations/sqlite/PPDB-0014_security_identity_policy_secrets_supply_chain.up.sql",
    "database/migrations/postgresql/PPDB-0014_security_identity_policy_secrets_supply_chain.up.sql",
    "database/migrations/sqlite/PPDB-0019_audit_immutability.up.sql",
    "database/migrations/postgresql/PPDB-0019_audit_immutability.up.sql",
    "docs/security/security_authority_model.md",
    "docs/security/secrets_and_egress.md",
    "docs/security/supply_chain.md",
    "runbooks/security_root_of_trust_and_secret_recovery.md",
    "plans/09_security_identity_and_policy/PLAN-SEC-002_security_authority_secrets_supply_chain.md",
)
_EXPECTED = {
    "UPSTREAM-007",
    "UPSTREAM-029",
    "UPSTREAM-035",
    "UPSTREAM-039",
    "UPSTREAM-043",
    "UPSTREAM-047",
    "UPSTREAM-075",
    "UPSTREAM-078",
    "UPSTREAM-079",
    "UPSTREAM-081",
    "UPSTREAM-094",
    "UPSTREAM-100",
    "UPSTREAM-116",
}


def validate_security_foundation(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in _REQUIRED:
        if not (root / relative).exists():
            errors.append(f"security required path missing: {relative}")
    gate_path = root / "provenance/pass_17_security_upstream_gate.json"
    if gate_path.exists():
        try:
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
            if gate.get("status") not in {
                "REVIEW_COMPLETE_MATERIAL_IMPLEMENTATION_ALLOWED",
                "INTEGRATED",
            }:
                errors.append("Pass 17 security upstream gate is not open/integrated")
            if not gate.get("material_implementation_allowed"):
                errors.append("Pass 17 material implementation is not allowed")
            if set(gate.get("candidate_upstream_ids", ())) != _EXPECTED:
                errors.append("Pass 17 security upstream candidate set drifted")
            if gate.get("correction_rounds_repeated"):
                errors.append("Pass 17 incorrectly repeated historical corrective program")
        except Exception as exc:
            errors.append(f"Pass 17 security upstream gate invalid: {exc}")
    adoption = root / "provenance/upstream_adoption_gate.json"
    if adoption.exists():
        doc = json.loads(adoption.read_text(encoding="utf-8"))
        subsystem = doc.get("subsystems", {}).get("security_supply_chain", {})
        if set(subsystem.get("candidate_upstream_ids", ())) != _EXPECTED:
            errors.append("security/supply-chain candidate set drifted")
        if subsystem.get("review_state") not in {"FOCUSED_REVIEW_COMPLETE", "INTEGRATED"}:
            errors.append("security/supply-chain upstream review is incomplete")
    catalog = root / "database/MIGRATION_CATALOG.json"
    if catalog.exists():
        data = json.loads(catalog.read_text(encoding="utf-8"))
        ids = {x.get("migration_id") for x in data.get("migrations", ())}
        if "PPDB-0014" not in ids:
            errors.append("PPDB-0014 is missing from migration catalog")
        if "PPDB-0019" not in ids:
            errors.append("PPDB-0019 audit immutability is missing from migration catalog")
    policy = root / "config/security_policy.json"
    if policy.exists():
        try:
            p = json.loads(policy.read_text(encoding="utf-8"))
            for key in (
                "policy_version",
                "high_impact_requires_independent_approval",
                "data_classifications",
                "external_egress",
            ):
                if key not in p:
                    errors.append(f"security policy missing {key}")
        except Exception as exc:
            errors.append(f"security policy invalid: {exc}")
    root_trust = root / "config/root_of_trust.json"
    if root_trust.exists():
        try:
            t = json.loads(root_trust.read_text(encoding="utf-8"))
            serialized = root_trust.read_text(encoding="utf-8").lower()
            if "private_key" in serialized or "api_token" in serialized:
                errors.append("root-of-trust config appears to contain plaintext secret material")
            if not t.get("trusted_key_references"):
                errors.append("root of trust lacks key references")
        except Exception as exc:
            errors.append(f"root of trust invalid: {exc}")
    return errors
