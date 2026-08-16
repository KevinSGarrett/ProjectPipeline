# Release Procedure

A release candidate is an immutable identity over source/configuration/dependency/migration inputs plus separately recorded archive/SBOM/provenance evidence. `release/release_candidate_r24.json` is intentionally labeled a local hardening candidate and **not production ready**.

Before production release: the resolver lock must be READY; Completion Gate must be COMPLETE; current functional/golden/performance/security/resilience evidence must pass; target installation, upgrade, rollback, and uninstall must be qualified; external blockers must be explicit; manifests/SBOM/provenance must be refreshed; the final archive must open under the exact root, pass CRC, preserve prior cumulative members, and pass clean-extraction validation.

If any required runtime or target is unavailable, record `NOT_QUALIFIED`/blocked state. Adapter existence, source packaging, or a mocked/dry-run result cannot be promoted into a live deployment claim.

Rollback follows `runbooks/release_upgrade_and_rollback.md`. Handoff must include architecture, configuration, procedures, known risks/blockers, credential-reference guidance, recovery, support/triage, Jira/requirements/evidence state, and continuation instructions without depending on chat history.
