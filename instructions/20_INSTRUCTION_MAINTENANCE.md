# Instruction Maintenance

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-20` |
| Status | `ACTIVE` |
| Pack version | `1.0.1` |
| Primary domains | `instruction_maintenance` |
| Governing entry point | `AGENTS.md` |

## Instruction system is control-plane code

Changes to `AGENTS.md`, `/instructions`, `/.agents/skills`, instruction validation, or governing policy are high-impact self-modification. They require source/authority rationale, focused diff, validation, independent review, rollback material, and current manifest hashes.

## Ownership

`AGENTS.md` is the concise repository entry point. Each major domain has exactly one primary governing instruction in `INSTRUCTION_COVERAGE_MATRIX.json`. Supporting files explain or implement the primary rule; they do not create competing authority.

Do not duplicate the entire pack into `AGENTS.md`, skills, README, or templates.

## Change triggers

Update durable instructions when accepted project authority, architecture, workflow, safety, external mutation, recovery, completion, benchmark, machine, or recurring operator correction changes. Do not append every one-off comment. Promote a correction only when it is intended to recur, compatible with stronger authority, and placed at the correct scope.

## Versioning

Use semantic pack versions for meaningful contract compatibility:

- major: incompatible authority, lifecycle, or structure change;
- minor: new governed domain or backward-compatible material capability;
- patch: clarification or correction without behavioral incompatibility.

Do not increment for every wording edit. Maintain `CHANGELOG.md` with decisions and migration effects.

## Modification procedure

1. identify governing source and affected domains;
2. inspect existing primary authority and related machine policy;
3. avoid new files when an existing primary location suffices;
4. update prose and machine policy together where applicable;
5. update schemas, skills, templates, examples, and tests only when behavior requires;
6. run `python scripts/validate_instructions.py --root . --update-hashes`;
7. run validator normally, cold-start tool, scenario tests, repository validation, and applicable broader tests;
8. perform an independent review for contradiction, duplicate authority, stale paths, secrets, bureaucracy, unsafe loopholes, benchmark contamination, Git/Jira conflicts, and external mutation;
9. regenerate project manifest after all repository files are stable;
10. retain rollback material and update changelog.

## Size discipline

Keep root `AGENTS.md` below the validator limit and focused on durable invariants and routing. Split detailed content by stable domain. Avoid giant monolithic instruction files, ceremonial process, or machine-readable JSON without human explanation.

## Validator scope

The focused validator detects missing files, duplicate IDs, hash drift, invalid JSON/schema, broken links, stale paths, secret patterns, forbidden terminology, coverage conflicts, authority defects, branch/Jira inconsistency, unpinned actions, PPQS boundary defects, missing scenarios, and cold-start omissions.

It is not a new workflow engine and does not replace Project Control, Scheduler, Jira/GitHub Steward, Assurance, Verification, Security, or Completion Gate.

## Second independent review

Before release of an instruction version, review the entire pack as if entering cold: look for contradiction, duplicated authority, missing domains, stale paths, secret leakage, overloaded root context, process excess, dirty-clone loopholes, micro-PR incentives, false completion, weak loop controls, PPQS contamination, worktree ambiguity, remote-machine races, Jira/GitHub conflict, and unsafe writes. Correct findings before final validation.
