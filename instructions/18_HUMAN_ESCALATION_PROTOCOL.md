# External Preconditions and Autonomous Continuation Protocol

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-18` |
| Status | `ACTIVE` |
| Pack version | `1.2.0` |
| Primary domains | `human_escalation` (stable compatibility identifier) |
| Governing entry point | `AGENTS.md` |

## No operator-work terminal

This stable numbered path is retained for compatibility, but it no longer authorizes requests for human work during normal development. Do not ask the operator to approve, review, merge, transition Jira, clean branches, run tests, install routine dependencies, format files, provision generated artifacts, or execute any other automatable project action.

Any legacy runtime enum, database field, schema property, or evidence key named `HUMAN_REQUIRED` is a compatibility alias for `BLOCKED_EXTERNAL` until migrated. It must be projected and reported as an external precondition, never rendered as a request for human work, and never treated as a cycle-completion or voluntary-stop condition.

When MFA/CAPTCHA, an unavailable credential reference, unresolved legal authority, exhausted budget capacity, account capability, physical hardware access, or irreconcilable higher authority makes an action objectively impossible, fail closed only for that action. Record a typed external precondition, assign no action to the operator, continue unaffected work, and schedule deterministic autonomous recheck. Never fabricate the missing capability.

## Required external-precondition record

Use `templates/HUMAN_INTERVENTION_REQUEST.md` (stable compatibility path; its content is an external-precondition record) and the classifications in `policies/ESCALATION_CLASSIFICATIONS.json`. Include:

- unique escalation and owning Jira item;
- what failed and exact operation;
- why automation cannot resolve it;
- affected scope and consequence;
- preserved state and safety actions already taken;
- exact missing external condition and safe acquisition/observation boundary;
- how ProjectPipeline verifies the condition without exposing secrets;
- deterministic resume point and next command;
- unaffected work that will continue;
- expiry or assumptions that must be revalidated.

Do not address the record to a person or express it as an instruction for the operator. State the smallest machine-verifiable condition that permits autonomous resumption.

## Credential precondition

Never include the credential value. Name the approved reference, provider/account, required permission, and a safe autonomous availability check that does not print the secret. Treat previously exposed credentials as compromised. Missing credentials do not authorize invention, disclosure, or an operator task.

## Authority precondition

Preserve the governing sources, exact conflict, bounded options, consequences, reversibility, and default safe state. Resolve through accepted authority when deterministic; otherwise keep the scope fail-closed without turning a routine preference into an operator decision.

## Physical precondition

Identify the machine by declared identity, unavailable physical capability, expected observable recovery state, safety constraints, autonomous probe, and resume criteria. Do not issue physical or destructive instructions to the operator.

## Continue independent work

Mark the affected lane blocked and preserve claims needed to protect work. Release only safe resources. Re-run Project Control and select other independent ready work unless the escalation blocks the global critical path.

## Closing an external precondition

Read the resulting external/local state; do not rely on a verbal confirmation where deterministic verification exists. Record evidence, invalidate stale assumptions, reconcile pending intent, resume at the recorded point, and close the condition only after verification.
