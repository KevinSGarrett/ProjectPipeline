# Pass 23 Full End-to-End System Integration

Pass 23 binds the existing Project Pipeline subsystems into realistic operator journeys without creating a second control plane.

The canonical journey covers project intake, requirement loading, Jira reconciliation in dry-run mode, deterministic sequencing and scheduling, typed human-required gating, delegation/context compilation, provider failover, recommendation-authority conflict handling, independent review, local Git plus a mocked protected PR gate, durable unknown-outcome/restart recovery, incident/human repair, the independent Completion Gate, and Command Center projection.

`config/pass23_e2e_journey_matrix.json` is the declared acceptance matrix. `src/project_pipeline/verification/e2e.py` executes it and `scripts/run_pass23_e2e.py` persists `evidence/verification/pass23_full_e2e_report.json`.

Live Jira, GitHub, Hatchet, Pydantic AI, Schemathesis, Toxiproxy, SWE-ReX, Testcontainers, cloud, and provider side effects are not inferred from adapter existence. When the actual runtime, credentials, target, or authority is unavailable, the report uses `EXPECTED_BLOCK` / `BLOCKED_EXTERNAL` and keeps `live_external_mutation_performed=false`.

A full-project `NOT_COMPLETE` result is a passing Pass 23 observation when it is the truthful output of the independent Completion Gate. Pass 23 verifies integration; it does not override later hardening/release/final-audit passes.
