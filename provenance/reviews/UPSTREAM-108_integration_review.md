# UPSTREAM-108 — UKGovernmentBEIS/inspect_ai Integration Review

- License: `MIT`
- Inspected revision: `d482209d573cdde116cc0f28abfb01712e91e80c`
- Candidate subsystem: `model_evaluation`
- Review state: `SOURCE_LEVEL_REVIEW_COMPLETE`
- Integration outcome: `OPTIONAL_ADAPTER_IMPLEMENTED` or `EXTERNAL_CLI_ADAPTER_IMPLEMENTED`
- Live qualification: `NOT_LIVE_VERIFIED`

## Source areas inspected

- `README.md`
- `pyproject.toml`
- `src/inspect_ai/_cli/eval.py`

## Useful concepts

- model evaluation framework
- model-graded evaluations
- tool-use evaluation
- structured eval logs

## Integration decision

- Expose Inspect AI through a bounded evaluation CLI adapter; networked model calls remain explicitly gated.

## Engineering findings

- Architecture: Evaluation should remain an independent verification capability rather than a control authority.
- Security: Evaluations may invoke hosted models/tools; provider/network usage must be explicitly allowed.
- Portability: Python >=3.10 and OS-independent package according to upstream metadata.
- Maintenance: Version and evaluation contract must be qualified before live CI use.
- Maturity: UK AI Security Institute evaluation framework with extensive built-in evaluations.
- Compatibility: Strong fit for later independent AI/model verification.
- Dependency implications: Optional inspect CLI/package; not mandatory runtime dependency.

## Evidence

- `GitHub:UKGovernmentBEIS/inspect_ai@d482209d573cdde116cc0f28abfb01712e91e80c`
- `README.md`
- `pyproject.toml`
- `src/inspect_ai/_cli/eval.py`
