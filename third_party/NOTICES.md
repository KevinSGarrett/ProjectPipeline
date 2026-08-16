# Third-Party Notices and Upstream Use

Project Pipeline uses, wraps, or derives bounded data contracts from reviewed upstream projects. Upstream code does not receive Project Pipeline control authority. Dependency activation and source adaptation remain separately governed.

## Active and implemented upstream use

- **NetworkX** (`networkx/networkx`, BSD-3-Clause) — active runtime graph algorithms behind Project Pipeline-owned dependency/conflict semantics.
- **Google OR-Tools** (`google/or-tools`, Apache-2.0) — optional CP-SAT safe-set optimizer; every result is revalidated by Project Pipeline before acceptance.
- **Worktrunk** (`max-sixty/worktrunk`, MIT OR Apache-2.0) — optional external CLI bridge for worktree creation/list/removal; mutating execution remains approval-gated.
- **Pydantic AI** (`pydantic/pydantic-ai`, MIT) — optional typed advisory-agent adapter. A bounded provider-compatibility data contract derived from v2.31.0 is retained under `src/project_pipeline/upstream_data/`; MIT notice obligations apply.
- **LiteLLM** (`BerriAI/litellm`, MIT outside `enterprise/`) — optional OpenAI-compatible proxy adapter. Project Pipeline explicitly excludes `enterprise/` and retains routing/policy authority.
- **Docker MCP Gateway** (`docker/mcp-gateway`, MIT) — optional tool gateway adapter. A bounded security-default contract derived from the reviewed command reference is retained under `src/project_pipeline/upstream_data/`; MIT notice obligations apply.
- **OpenLIT** (`openlit/openlit`, Apache-2.0) — optional OpenTelemetry-native AI instrumentation bridge.

## Bounded adapted assets

### Pydantic AI
Source: `pydantic_ai_slim/pydantic_ai/models/__init__.py`, v2.31.0 / observed commit `25a70926cfafdfc63b3d32c1b5f2c7f139e2c58c`.
Copyright and license: Pydantic contributors, MIT License. The adapted JSON contains only reviewed provider-compatibility identifiers and Project Pipeline provenance fields.

### Docker MCP Gateway
Source: `docs/generator/reference/mcp_gateway_run.md`, commit `24b028f4f9aac85ce1a1057c5e8d739836e7c18d`.
Copyright and license: Docker MCP Gateway contributors, MIT License. The adapted JSON contains only reviewed command-option defaults relevant to Project Pipeline's secure gateway boundary.

Exact adaptation reviews, hashes, source revisions, and project paths are recorded under `provenance/source_incorporation_reviews/`. Remaining selected upstreams are not represented as active until their usage ledger records a concrete integration.
