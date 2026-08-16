# PLAN-INFRA-001 — Deployment and Infrastructure

- **Plan ID:** `PLAN-INFRA-001`
- **Status:** `PARTIALLY_IMPLEMENTED`
- **Authority:** source-derived requirements plus explicitly labeled implementation detail
- **Source basis:** `GOV-001:L000748-L000764`, `SRC-012:L000001-L000100`

## PLAN-INFRA-001:SEC-01 Local baseline

Windows/local operation remains the primary deployment baseline. The control-focused machine owns primary director/database responsibilities while a GPU-capable machine is an explicit worker plus fenced standby/recovery candidate. Containers remain optional rather than a requirement for Windows-native workers.

## PLAN-INFRA-001:SEC-02 Packaging

Release assets require reproducible installation, configuration validation, start/stop, upgrade, rollback, migration integrity, and archive verification. Environment state and secret material remain outside source control.

## PLAN-INFRA-001:SEC-03 Optional AWS topology

The selected architecture is a local-primary hybrid cloud spine: DynamoDB witness, SQS durable event queue, S3 recovery/event storage, optional Lambda ingress/watchdog, CloudWatch observability, AWS Budgets guardrails, Parameter Store configuration references, and optional bounded recovery/burst capacity. IaC is disabled by default and cannot move canonical authority to AWS without an explicit later decision and measured evidence.

## PLAN-INFRA-001:SEC-04 Environment and credential model

Development, test, staging, production, recovery, and synthetic certification have distinct state, credentials, policy, and data handling. Local/cloud functions use scoped role/profile credentials; cloud workers must use task/instance roles when available. No long-lived cloud key is embedded in repository configuration.

## PLAN-INFRA-001:SEC-05 Recovery and backup deployment

Canonical PostgreSQL backup is abstracted through pgBackRest; general encrypted backup through restic; content-addressed artifacts keep one local/cloud-compatible interface. Restore verification occurs only in an isolated target and has its own status/evidence. Cloud removal does not invalidate local truth.

## PLAN-INFRA-001:SEC-06 Remaining qualification

Live Windows service packaging, private network overlay, real AWS ingress/recovery activation, real backup repositories, destructive PostgreSQL restore exercises, and cloud burst workers remain environment-specific qualification work. The architecture decisions are resolved; operational readiness is not overclaimed.
