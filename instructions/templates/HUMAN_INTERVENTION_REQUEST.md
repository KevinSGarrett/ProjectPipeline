# Human Intervention Request

- Escalation ID: `[ESC-UNIQUE-ID]`
- Classification: `[class from policies/ESCALATION_CLASSIFICATIONS.json]`
- Owning Jira item: `[PP-...]`
- Correlation ID: `[correlation]`
- Created at UTC: `[timestamp]`
- Expires/revalidate after: `[timestamp or condition]`

## Failed operation

`[exact operation and target]`

## Why automation cannot resolve it

`[specific capability, permission, legal, account, physical, cost, or authority boundary]`

## Impact

- Affected scope: `[scope]`
- Critical-path effect: `[none / local / global]`
- Consequence if not completed: `[consequence]`

## Preserved state

- Branch/worktree/base SHA: `[identity]`
- Changed files/artifacts: `[paths and digests]`
- Pending external intents: `[IDs or none]`
- Safety actions already taken: `[actions]`

## Exact human action

1. `[bounded action]`
2. `[bounded action]`

Do not include secret values in this record.

## Verification after action

`[safe read-only command or observable state]`

Expected result: `[specific result]`

## Resume point

- Next command/action: `[exact next safe action]`
- Required assumptions to revalidate: `[assumptions]`
- Stop condition: `[condition]`

## Unaffected work continuation

`[eligible work that continues, or exact reason for global pause]`
