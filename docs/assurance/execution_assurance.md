# Execution Assurance

Project Pipeline treats implementation success as a claim until objective evidence establishes a verified fact. Execution assurance sits above worker/provider output and below final completion authority.

The subsystem compiles Jira acceptance criteria into immutable verification criteria, enforces bounded attempts and evidence ceilings, tracks evidence freshness, requires independent review where risk demands it, detects non-progressing loops, and prevents silent scope expansion. It never changes project truth because a worker says that work is finished.

## Authority boundary

The Project Control Kernel remains canonical for project state. The assurance layer evaluates whether evidence is sufficient to advance completion claims. Promptfoo, Inspect AI, Hypothesis, Playwright, Schemathesis, Toxiproxy, accessibility/performance tools, mutation tools, and browser agents can produce verification evidence; none may set `final_complete`.

## Truth states

`CLAIM` is an assertion from an implementation or operator path. `EVIDENCE` is an artifact/observation. `VERIFIED_FACT` requires linked evidence. `UNKNOWN` is preserved when evidence is missing, stale, unverified, or inapplicable. `CONTRADICTED` records disagreement that must be resolved rather than averaged away.

## Evidence freshness

The default local policy treats evidence older than thirty days as stale unless a later policy revision states otherwise. Freshness is evaluated independently from the original evidence result: a verified PASS can still become stale.

## Risk

High-risk and critical criteria require multiple distinct verification methods and independent review. This policy is deliberately stronger than simply rerunning the same test twice.
