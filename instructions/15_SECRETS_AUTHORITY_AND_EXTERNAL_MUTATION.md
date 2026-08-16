# Secrets, Authority, and External Mutation

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-15` |
| Status | `ACTIVE` |
| Pack version | `1.0.1` |
| Primary domains | `external_mutation`, `secrets` |
| Governing entry point | `AGENTS.md` |

## Default posture

External mutation is denied by default. `policies/EXTERNAL_MUTATION_AUTHORITY.json`, `config/repository_policy.json`, and `config/security_policy.json` jointly define authorization. Fully autonomous does not mean blindly destructive.

## Any remote write requires

- unique action and idempotency identity;
- authenticated actor and exact target;
- bounded operation and scope;
- authorization or standing project grant;
- current policy and budget decision;
- approved credential reference;
- dry-run or plan where supported;
- audit record and expected effect;
- reconciliation method for uncertain outcomes.

Do not broaden a grant by inference. High-impact merge, deploy, spend, external model, secret access, instruction/policy modification, project completion, or emergency action requires independent approval under security policy.

## Authority classes

- Autonomously authorized within policy: bounded local edits/tests/generation, registered branches/worktrees/commits, dry runs, and normal project remote operations only when a standing grant plus all write preconditions exist.
- Policy-gated: remote deletion, protection/rules changes, CI permissions, cloud creation, major upgrades, releases, production-like deployment, secrets, policy/instruction changes, and material spend.
- Human required: legal/license ambiguity, MFA/CAPTCHA, owner secret action, material over-budget cost, irreconcilable requirements, account intervention, or physical hardware action.
- Prohibited: secret exposure, hidden benchmark access, evidence fabrication, gate bypass, deletion of unpreserved work, credential invention, blind uncertain-outcome retry, or unreviewed upstream execution.

## Secret handling

Secret-bearing local configuration may exist outside the public repository, including `C:\Project_X\Github_Repo\.env`. Never copy it into the repository or archive. Instruction files identify environment variable or secret-reference names, never values.

Expected references include `JIRA_BASE_URL`, `JIRA_USER_EMAIL`, `JIRA_API_TOKEN_REF`, `GITHUB_TOKEN_REF`, and `AWS_PROFILE`. Secret values are leased at runtime for the minimum scope and duration and are not persisted in logs, Jira, PRs, issues, screenshots, evidence, or generated documentation.

A credential revealed in chat, output, commit, screenshot, or public system is exposed. Stop affected use, contain, rotate, inspect history/logs, and record a security incident without reproducing the value.

## Pre-publication check

Inspect staged and generated files, run instruction and repository validators, run secret scanning, inspect archive members, and confirm no local runtime data or credentials are included. `.gitignore` is a convenience, not a security gate.

## Unknown outcome

When a write may have succeeded:

```text
STOP WRITE RETRIES
→ READ EXTERNAL STATE
→ RECONCILE INTENDED EFFECT
→ DETERMINE WHETHER IT OCCURRED
→ RETRY ONLY IF ABSENT AND STILL AUTHORIZED
```

This applies to Jira, GitHub, cloud, release, provider, spend, and remote-worker operations.

## Degraded mode

When an external service is unavailable, record outage, preserve pending intents, enter an appropriate degraded/local-first mode, continue unrelated local work, and reconcile before later replay. Do not hammer the provider.
