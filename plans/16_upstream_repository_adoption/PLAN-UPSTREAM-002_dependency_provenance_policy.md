# PLAN-UPSTREAM-002 — Dependency, License, and Provenance Policy

- **Plan ID:** `PLAN-UPSTREAM-002`
- **Status:** `ACTIVE`
- **Authority:** accepted architecture decision and supply-chain requirements
- **Source basis:** `GOV-001:L000855-L000876`, `GOV-001:L001364-L001385`, `SRC-016:L001625-L001640`, `SRC-016:L002181-L002195`

## PLAN-UPSTREAM-002:SEC-01 Separate approval decisions

Installing or linking an upstream dependency and copying, adapting, or vendoring source are separate decisions. Dependency eligibility never grants source-incorporation permission. The default for both is deny until the applicable evidence is recorded.

## PLAN-UPSTREAM-002:SEC-02 Dependency activation gate

Activation requires canonical URL, inspected revision, compatible license classification, bounded subsystem role, explicit disposition, review artifact, version lock, integrity verification, vulnerability review, SBOM entry, notice handling, and representative tests. Runtime services also require configuration, health, recovery, upgrade, and rollback evidence.

## PLAN-UPSTREAM-002:SEC-03 Source-incorporation gate

Source incorporation requires a separately approved record naming exact files, license obligations, copyright and notice preservation, modification boundaries, provenance annotations, security review, and maintenance ownership. No source incorporation is approved by the current upstream registry.

## PLAN-UPSTREAM-002:SEC-04 License classes

Permissive licenses may proceed through the automated policy after all technical gates. MPL-family dependencies require notice and file-level compliance review. AGPL, source-available, custom, conflicting, or unknown terms require explicit human legal approval before incorporation or a deployment decision that may trigger obligations.

## PLAN-UPSTREAM-002:SEC-05 Repository subtrees and mixed terms

Repository-level license metadata does not automatically cover enterprise, examples, models, data, plugins, or separately licensed subdirectories. Such content is excluded until separately inspected. LiteLLM enterprise-only content is excluded from the selected core dependency boundary.

## PLAN-UPSTREAM-002:SEC-06 Continuous assurance

Dependency manifests, locks, notices, SBOMs, vulnerability results, signatures or checksums, and provenance are regenerated for releases. Material upstream changes reopen the review. A selected dependency that fails security, maintenance, compatibility, or conformance gates is disabled or replaced through its internal port.
