# PLAN-ARCH-003 — Runtime and Deployment Topology

- **Plan ID:** `PLAN-ARCH-003`
- **Status:** `ACTIVE`
- **Authority:** accepted local-first, Windows, optional AWS, resilience, and security decisions
- **Source basis:** `SRC-009:L000003-L000020`, `SRC-016:L000803-L001010`, `GOV-001:L000748-L000780`

## PLAN-ARCH-003:SEC-01 Local core profile

The local core profile runs the control API, deterministic control modules, durable workers, scheduler, context services, evidence services, and operator application on the Windows control machine. PostgreSQL is the canonical dependency. Hatchet, OPA, Docker MCP Gateway, and other Linux-oriented dependencies may run in Docker or WSL2 after version and recovery qualification.

## PLAN-ARCH-003:SEC-02 Offline portable profile

The offline profile supports repository inspection, source retrieval, requirement and Jira compilation, graph analysis, context compilation, and evidence packaging without remote mutation. Remote effects remain queued and must be reconciled after connectivity returns. Reduced services may not weaken source provenance or evidence identity.

## PLAN-ARCH-003:SEC-03 Hybrid AWS profile

AWS may add encrypted backup, artifact replication, authenticated ingress, notifications, witness functions, or burst workers. No AWS service becomes mandatory for local deterministic control unless a later ADR changes the product boundary. Cloud credentials remain scoped and local degraded operation is explicit.

## PLAN-ARCH-003:SEC-04 Windows service model

Long-running native services may be supervised by WinSW after binary provenance, service identity, recovery, installation, upgrade, rollback, and uninstall are tested. The Tauri desktop shell is a client and cannot be the only owner or supervisor of critical backend processes.

## PLAN-ARCH-003:SEC-05 Operator delivery

The Command Center is a React and TypeScript web application served locally or over authenticated private connectivity. A Tauri shell adds tray, notification, installer, and updater behavior while reusing the same API contracts and web client. Accessibility and browser operation remain mandatory.

## PLAN-ARCH-003:SEC-06 Network and secret boundaries

Database, workflow, policy, tool, and worker endpoints are private by default. Remote access uses authenticated private connectivity. SOPS with age encrypts repository-managed configuration; plaintext secrets are injected only into the process that requires them and are excluded from logs, context packs, and evidence.

## PLAN-ARCH-003:SEC-07 Profile qualification

Each profile declares required components, external dependencies, network rules, degraded behavior, configuration schema, installation procedure, health checks, backup and restore expectations, and rollback. A profile is eligible only after its acceptance tests pass.
