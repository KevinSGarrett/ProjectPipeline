
# Recover from a Validation Failure

1. Preserve the failing command and output.
2. Identify the validator check and affected stable IDs.
3. Determine whether the defect is implementation, registry, traceability, documentation, or generated-state drift.
4. Correct the authoritative source rather than suppressing the check without justification.
5. Add or strengthen a regression test when the failure exposed a missing guard.
6. Regenerate derived artifacts and re-run the complete local quality gate.
