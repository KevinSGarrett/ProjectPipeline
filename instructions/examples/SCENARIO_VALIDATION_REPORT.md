# Instruction Scenario Validation Report

The governing behavior for scenarios A through L is encoded in `policies/VALIDATION_SCENARIOS.json` and asserted by `tests/test_instruction_system.py`.

| Scenario | Required behavior represented | Governing location |
|---|---|---|
| A Fresh session | Entry point, cold start, preflight, control-based selection | `AGENTS.md`, `00`, `03` |
| B Dirty repository | Preserve, inspect, reconcile; no escape clone | `07`, `08`, `17` |
| C Jira disagreement | Snapshot and reconcile; no silent overwrite | `06` |
| D Overlapping workers | Atomic claims and scheduler conflict control | `10` |
| E Repeated failure | Fingerprint limit forces new strategy or block | `11` |
| F Intentional dirty seed | Immutable source and isolated execution copy | `13` |
| G Hidden material | Refuse access and fail contaminated lane | `13` |
| H Unknown remote write | Read/reconcile before retry | `15`, `17` |
| I Low-risk docs | Fast-path validation | `09` |
| J High-risk change | Independent review and stronger evidence | `09`, `12` |
| K CPU worker loss | Fence, reconcile, preserve, then reassign | `16`, `17` |
| L Human action | Actionable request and unaffected-work continuation | `18` |

A passing structural scenario test means the instruction route is present and consistent. It does not claim that live GitHub, Jira, or remote-machine activation has been exercised.
