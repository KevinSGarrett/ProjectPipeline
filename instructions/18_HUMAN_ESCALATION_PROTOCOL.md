# Human Escalation Protocol

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-18` |
| Status | `ACTIVE` |
| Pack version | `1.1.0` |
| Primary domains | `human_escalation` |
| Governing entry point | `AGENTS.md` |

## Escalate only genuine human work

Do not ask about routine names, folders, ordinary tests, compatible fixes, or common engineering choices. Use accepted source, plans, ADRs, policies, and professional judgment.

Human action is appropriate for MFA/CAPTCHA, owner-only credential provisioning or rotation, material cost approval, unresolved legal/license status, irreconcilable higher authority, account/identity intervention, out-of-scope destructive action, or physical hardware work.

## Required escalation record

Use `templates/HUMAN_INTERVENTION_REQUEST.md` and the classifications in `policies/ESCALATION_CLASSIFICATIONS.json`. Include:

- unique escalation and owning Jira item;
- what failed and exact operation;
- why automation cannot resolve it;
- affected scope and consequence;
- preserved state and safety actions already taken;
- exact human action with target and boundaries;
- how the human and Codex verify success;
- deterministic resume point and next command;
- unaffected work that will continue;
- expiry or assumptions that must be revalidated.

Avoid vague requests such as asking what to do. Provide the smallest exact intervention.

## Credential intervention

Never include the credential value. Name the approved reference, provider/account, required permission, rotation/creation action, and a safe verification command that does not print the secret. Treat previously exposed credentials as compromised.

## Decision intervention

Present the governing sources, exact conflict, options, consequences, recommendation, reversibility, and default safe state. Do not frame a routine preference as a material decision.

## Physical intervention

Identify machine by declared identity, exact physical/GUI action, expected observable state, safety constraints, and how the automation resumes. Do not ask the operator to run broad destructive cleanup.

## Continue independent work

Mark the affected lane blocked and preserve claims needed to protect work. Release only safe resources. Re-run Project Control and select other independent ready work unless the escalation blocks the global critical path.

## Closing an escalation

Read the resulting external/local state; do not trust a verbal confirmation alone where deterministic verification exists. Record evidence, invalidate stale assumptions, reconcile pending intent, resume at the recorded point, and close the escalation only after verification.
