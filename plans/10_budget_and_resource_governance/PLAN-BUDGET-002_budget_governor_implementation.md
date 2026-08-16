# PLAN-BUDGET-002 — Budget Governor Implementation

- **Plan ID:** `PLAN-BUDGET-002`
- **Status:** `ACTIVE`
- **Authority:** deterministic Project Pipeline budget contracts, source-derived spend constraints, and the permanent Upstream Adoption Gate
- **Source basis:** `SRC-004:L000050-L000251`, `SRC-004:L000253-L000513`, `SRC-004:L000572-L000936`, `SRC-004:L000937-L000977`, `SRC-012:L000780-L000816`, `GOV-001:L000607-L000619`

## PLAN-BUDGET-002:SEC-01 Upstream-first cost-evidence gate

Pass 14 evaluates LiteLLM, Infracost, Langfuse, MLflow, and OpenLIT before material Budget Governor implementation. Upstream systems may calculate, estimate, or transport cost and usage evidence, but Project Pipeline remains the sole deterministic authority for admission, reservation, settlement, pressure, reserve use, and hard-stop behavior. Missing price information remains unknown rather than being converted to zero.

## PLAN-BUDGET-002:SEC-02 Unified immutable cost and quota ledger

Budget accounting uses immutable entries denominated in integer USD microunits plus separately typed quota and usage dimensions. Entries carry project, task, provider, model, resource, tool, outcome, evidence state, verified/merged outcome flags, and retry-waste attribution. Credits remain explicit entries; historical spend is never rewritten to make a later reconciliation appear cheaper.

## PLAN-BUDGET-002:SEC-03 Hierarchical limits, soft envelopes, and protected reserve

Budget limits support global, portfolio, project, phase, task, provider, and resource scopes with hard caps, soft envelopes, and protected reserve. Provider soft envelopes may be rebalanced deterministically from observed demand without changing hard caps. Protected reserve requires an allowed reason tied to critical, recovery, security, deadline-protection, or required-verification work.

## PLAN-BUDGET-002:SEC-04 Spend leases, settlement, and uncertain outcomes

Potentially paid or quota-consuming work obtains an atomic spend lease before execution. The store rechecks current spend, active commitments, limits, and quotas inside the reservation transaction so stale admission decisions cannot create aggregate overspend. Settlement replaces reservation with immutable observed cost. Unknown provider outcomes hold the reservation until explicit reconciliation and are never blindly released or retried.

## PLAN-BUDGET-002:SEC-05 Pressure, hard stop, anomaly, and admission policy

Deterministic GREEN, YELLOW, ORANGE, RED, and HARD_STOP pressure states use committed spend, forecast P90, and pace. Increasing pressure favors lower-cost capable, subscription, or local execution while preserving recovery and required verification. HARD_STOP rejects incremental paid work without stopping non-paid control/local work. Observed cost far above expected P90 creates warning or blocking anomalies rather than silently consuming runaway spend.

## PLAN-BUDGET-002:SEC-06 Forecasting, deadline reserve, and outcome economics

Historical observations produce deterministic P50/P90 estimates with explicit low/medium/high confidence. Forecasts include queued demand, burn rate, pace, and runway without inventing provider prices. Deadline-protection reserve can be authorized only for explicit deadline-bound work. Efficiency reporting measures cost per verified outcome, cost per merged outcome, and retry waste instead of rewarding cheap but unsuccessful attempts.

## PLAN-BUDGET-002:SEC-07 Scheduler, router, context, and verification coupling

Budget admission is an input to scheduler eligibility and paid-lane ceilings. Agent routing enforces task cost ceilings when historical cost evidence exists, while unknown price remains subject to Budget Governor admission rather than being treated as free. Context and verification costs are attributable ledger classes; review and required verification are not removed merely to reduce spend.

## PLAN-BUDGET-002:SEC-08 Infracost, LiteLLM, OpenLIT, Langfuse, and MLflow boundaries

Infracost is wrapped as a read-only external CLI preflight for IaC estimates with root confinement, fixed argv, explicit external-read permission, exact decimal-to-microunit conversion, and unknown-price propagation. LiteLLM cost/reservation behavior informs provider evidence and concurrency-safe reservation patterns. OpenLIT remains the OpenTelemetry GenAI usage boundary. Langfuse and MLflow contribute usage/cost dimensional and aggregation patterns without becoming required runtime authorities.

## PLAN-BUDGET-002:SEC-09 Persistence, CLI, schemas, simulations, and change impact

`PPDB-0011_budget_governor` persists limits, quotas, ledger entries, leases, admission decisions, history, forecasts, and anomalies with reversible SQLite and PostgreSQL-oriented DDL. The CLI exposes status, limit/quota configuration, admission, reservation, settlement, uncertain-outcome reconciliation, forecast, metrics, anomaly analysis, budget-change impact, Infracost preflight, and deterministic simulations. Local mutations require explicit apply and approval flags.

## PLAN-BUDGET-002:SEC-10 Verification and external truth boundary

Pass 14 verification covers immutable identities, hierarchy and reserve rules, atomic cash/quota races, settlement and overspend, unknown outcomes, pressure transitions, hard-stop local continuation, anomaly thresholds, forecasts, outcome economics, soft-envelope reallocation, scheduler/router coupling, Infracost safety, migration rollback, CLI approval gates, schemas, provenance, Jira/traceability, and cumulative regression. The Budget Governor advances locally while live provider billing reconciliation, live Infracost execution against production IaC, and AWS account budget/alarm qualification remain external or later-pass work.
