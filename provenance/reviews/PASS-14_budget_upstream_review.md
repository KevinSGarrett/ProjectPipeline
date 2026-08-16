# Pass 14 upstream review — Budget Governor

## Gate decision

The mapped Budget Governor upstream set was reviewed before material implementation. Project Pipeline retains deterministic budget authority. Upstream systems may supply cost, usage, pricing, or observability evidence, but they cannot reserve spend, authorize work, release protected reserve, change pressure mode, or override canonical admission decisions.

## UPSTREAM-012 — BerriAI/litellm

- Current source area inspected: `litellm/cost_calculator.py` at `87abb8781ee2e586858c9e9943ecb789e316af96`.
- Budget behavior inspected: `tests/test_litellm/proxy/test_budget_reservation.py` at the same revision.
- Reuse decision: keep the existing provider adapter and use normalized model/provider cost evidence as an estimate input. Mine the reservation/release race-protection pattern, but do not delegate Project Pipeline budget authority to LiteLLM.
- Enterprise-only source remains excluded. No source incorporation is approved.

## UPSTREAM-053 — infracost/infracost

- Source revision inspected: `0c473ade0fd0d725fe8f5edd719ef634d9594690`.
- License: Apache-2.0.
- Source areas inspected: `schema/infracost.schema.json` and `cmd/infracost/testdata/output_terraform_out_file_json/infracost_output.golden`.
- Reuse decision: implement a bounded external-CLI adapter for Terraform/IaC cost preflight. It consumes JSON estimates and unknown-price markers only. It never applies infrastructure and never authorizes AWS spend.

## UPSTREAM-059 — langfuse/langfuse

- Existing focused review remains valid at `ab58010c81339ffb3e19fc491d71733cf4f10f6a`.
- Additional budget source inspected: `fern/apis/server/definition/commons.yml`.
- Reuse decision: adopt the architecture pattern of separately named usage dimensions and USD cost dimensions at observation granularity. OpenTelemetry/OpenLIT remain the telemetry baseline; Langfuse is not added as a runtime dependency.

## UPSTREAM-065 — mlflow/mlflow

- Source revision inspected: `9355281ca38ff7e288161f0a71022400f8197175`.
- License: Apache-2.0.
- Source area inspected: `docs/docs/genai/tracing/token-usage-cost/index.mdx`.
- Reuse decision: adopt the implementation pattern of span/trace cost aggregation and explicit unknown pricing. Project Pipeline is not made an MLflow tracking deployment and does not add MLflow as a dependency.

## UPSTREAM-077 — openlit/openlit

- Existing deep review remains valid at `24224bdfad8628c639742e49fddc303675067416`.
- Additional source inspected: `sdk/python/src/openlit/semcov/__init__.py`.
- Reuse decision: keep the existing optional OpenLIT/OTLP bridge and use OpenTelemetry GenAI usage semantics for observability. Project Pipeline budget ledgers remain canonical and provider-independent.

## Resulting architecture

1. Project Pipeline owns budget hierarchy, hard caps, protected reserve, quota/shadow-cost accounting, spend leases, settlement, pressure modes, forecasts, and admission.
2. LiteLLM can contribute provider/model cost estimates through the existing adapter boundary.
3. Infracost can contribute IaC cost-preflight evidence through a new non-mutating CLI adapter.
4. Langfuse/MLflow patterns inform flexible usage/cost dimensions and aggregation without becoming dependencies.
5. OpenLIT remains the optional telemetry export boundary.
6. Missing or unpriced cost evidence is `UNKNOWN`, never silently treated as zero.
