# Anti-Loop and Anti-Overengineering

| Field | Value |
|---|---|
| Instruction ID | `PP-INST-11` |
| Status | `ACTIVE` |
| Pack version | `1.0.1` |
| Primary domains | `anti_loop`, `anti_overengineering` |
| Governing entry point | `AGENTS.md` |

## Attempt budgets are canonical

Use `config/assurance_policy.json`; do not invent competing limits. At pack creation it defines a maximum of five loop attempts, two occurrences of the same failure, two unchanged outputs, eight verification attempts, forty evidence records, and a default scope-change budget of three. Always read the current file rather than copying these numbers into new control logic.

## Repeated failure response

After each failure, record a normalized fingerprint, command/input, environment, output digest, hypothesis, and change made. When the same fingerprint or unchanged output reaches the canonical limit:

1. stop the repeated strategy;
2. compare what actually changed;
3. perform root-cause analysis in the relevant source, test, config, data, or environment;
4. choose a materially different strategy;
5. retry within the remaining budget;
6. preserve work and block/escalate when exhausted.

Rerunning the same command with no relevant change is not a new strategy.

## Progress invariant

A sustained cycle produces one or more of:

- accepted implementation;
- dependency or blocker reduction;
- valid new evidence;
- corrected diagnosis;
- integrated change;
- verified defect represented as actionable work;
- exact scoped escalation.

Repeated rereading, status rewriting, branch recreation, cloning, formatting, report generation, or unchanged tests are not progress.

## Stuck-work escape hatch

Capture owning item, exact error, fingerprint, attempts, current hypothesis, preserved changes, blocker class, dependency/critical-path impact, and next safe experiment or human action. Mark the lane blocked, release only safe resources, and continue independent work.

## Smallest production-quality implementation

Continually ask: what is the smallest implementation that satisfies accepted requirement, architecture, risk, operability, and verification?

Do not create abstractions without a real consumer, generic frameworks for hypothetical future scale, multiple interfaces around one stable internal function, infrastructure unsupported by plans, excessive low-risk permutations, broad rewrites of working subsystems, plans for plans, or bookkeeping for bookkeeping.

YAGNI does not permit ignoring accepted ProjectPipeline requirements. It prevents speculative scope.

## Scope-change control

When a change exceeds the accepted item, classify it as necessary implementation detail, discovered defect, follow-up, or unrelated enhancement. Use the assurance scope-change guard. Fold only behavior necessary for the cohesive acceptance/rollback boundary; create traceable follow-up for independent work.

## Housekeeping budget

Cleanup follows merge, real hygiene risk, periodic bounded maintenance, or release preparation. Set a clear objective and stop condition. Do not spend an autonomous session continuously reorganizing while implementation remains ready.

## Review-loop limit

For review findings, determine validity and materiality. Correct valid material findings, explain invalid findings, rerun applicable checks, and stop cosmetic oscillation. A reviewer preference is not higher authority than accepted project conventions.
