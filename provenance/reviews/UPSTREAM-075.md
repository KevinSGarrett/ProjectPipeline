# UPSTREAM-075 — openbao/openbao

- **Canonical URL:** `https://github.com/openbao/openbao`
- **Inspected revision:** `9c17d73cb4a71690d32d7ed223f9bc8f241f9157`
- **Inspection state:** `DEEPLY_REVIEWED`
- **License:** `MPL-2.0`
- **Disposition:** `EVALUATE_LATER`
- **Dependency activation eligible:** `false`
- **Source incorporation approved:** `false`

## Project Pipeline role

Optional later secret broker for dynamic credentials, certificates, leases, and revocation.

## Useful concepts

- dynamic secrets
- PKI and certificates
- leases and revocation
- central audit

## Reviewed files and surfaces

- `README.md`
- `vault`
- `api`
- `LICENSE`

## Integration boundary

- Add only when multi-user or dynamic credential requirements justify an operated secrets service.

The integration remains behind the Project Pipeline component and port named in the architecture registry. The upstream implementation does not own project truth, policy enforcement, completion, budget, or evidence semantics.

## Architectural lessons

Dynamic credentials reduce standing privilege but create a critical availability and recovery dependency.

## Risk and operability review

- **Security:** Root tokens, unseal or recovery keys, storage integrity, and audit access require human-governed procedures.
- **Portability:** Self-hosted service works across environments but increases operational burden.
- **Maintenance:** MPL distribution boundaries and upgrade compatibility require review.
- **Maturity:** `ACTIVE_INFRASTRUCTURE_PLATFORM`
- **Compatibility:** `EVALUATED_ADVANCED_PROFILE`

## License and provenance boundary

MPL-2.0 dependency use; modifications and distribution require file-level notice/compliance review.

**Disposition rationale:** Reviewed and retained as a qualified alternative or later-profile candidate; it is not selected for initial activation.

**Dependency implications:** No initial activation; re-review only when a documented profile or measured need justifies it.

No upstream source was copied into Project Pipeline by this review.

## Evidence sources

- `https://github.com/openbao/openbao`
- `https://openbao.org/`

## Project Pipeline disposition after source chronology review

- Source strategy: `QUALIFIED_FALLBACK_OR_LATER_PROFILE`
- Disposition: `EVALUATE_LATER`
- Dependency activation eligible: `false`
- Source incorporation approved: `false`
- Rationale: Reviewed and retained behind an internal port for a measured future trigger; it is not selected for initial activation and source incorporation is not approved.
