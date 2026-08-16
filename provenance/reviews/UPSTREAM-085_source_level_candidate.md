# UPSTREAM-085 — promptfoo/promptfoo

- Disposition: `ADOPT_DEPENDENCY`
- Inspection state: `SOURCE_LEVEL_REVIEW_COMPLETE`
- Inspected revision: `b934a30305f8a2694683d78dbf281265b22d083a`
- License: `MIT`
- Candidate subsystem: `model_evaluation`

## Purpose

Qualify promptfoo for model/agent evaluation and red-team scenarios behind Project Pipeline evidence policy.

## Source-level paths reviewed

- `test/providers/testProvider.test.ts`
- `test/redteam/providers/goat.test.ts`
- `test/evaluator/trace-integration.test.ts`

## Integration decision

Qualify promptfoo for model/agent evaluation and red-team scenarios behind Project Pipeline evidence policy.

## Security / portability / maintenance

- Security: Requires focused threat/dependency review before activation or source adaptation.
- Portability: Compatibility with Windows-first and offline/degraded profiles must be qualified before activation.
- Maintenance: Current metadata review does not replace release-pinning and maintenance qualification.

## Evidence sources

- https://github.com/promptfoo/promptfoo
- https://github.com/promptfoo/promptfoo/blob/b934a30305f8a2694683d78dbf281265b22d083a/test/providers/testProvider.test.ts
- https://github.com/promptfoo/promptfoo/blob/b934a30305f8a2694683d78dbf281265b22d083a/test/redteam/providers/goat.test.ts
- https://github.com/promptfoo/promptfoo/blob/b934a30305f8a2694683d78dbf281265b22d083a/test/evaluator/trace-integration.test.ts

No upstream source is incorporated by this review. Any future adaptation requires the bounded source-incorporation gate.
