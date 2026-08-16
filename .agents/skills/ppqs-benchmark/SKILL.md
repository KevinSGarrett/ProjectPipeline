---
name: ppqs-benchmark
description: Execute a registered PPQS benchmark without changing canonical seeds or contaminating candidate-visible work.
---

# PPQS Benchmark

1. Read instruction `13` and the registered pack entry.
2. Read only candidate-visible manifest, brief, runtime contract, boundary, visible tests, and declared inputs.
3. Verify pack identity/integrity without searching for evaluator-only material.
4. Copy to a new isolated run workspace; keep canonical seed read-only.
5. Restrict reads/writes to the declared boundary and namespace all test Jira/GitHub resources.
6. Treat dirty state, malformed files, empty logs, canaries, conflicts, and failures as inputs.
7. Refuse Oracle, hidden test, gold, reference solution, evaluator score, or private acceptance access.
8. Preserve run manifest, outputs, logs, evidence, and digest; clean only disposable workspace/resources after retention checks.
