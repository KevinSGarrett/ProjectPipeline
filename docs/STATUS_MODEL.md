
# Status and Truth Model

Project Pipeline separates three concepts:

- **Claim** — an assertion that may still be unverified.
- **Evidence** — an observed artifact, output, state, or review result.
- **Verified fact** — a claim supported by applicable, current evidence and accepted verification policy.

Implementation state is independently recorded as `IMPLEMENTED`, `PARTIALLY_IMPLEMENTED`, `MOCK_VERIFIED`, `LIVE_VERIFIED`, `BLOCKED_EXTERNAL`, or `PLANNED_ONLY`.

A ticket status, generated summary, or passing unrelated test is not sufficient evidence of completion. Unknown values must remain explicit rather than being inferred into facts.
