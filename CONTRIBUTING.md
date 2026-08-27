# Contributing to ProjectPipeline

Thank you for taking the time to improve ProjectPipeline. Bug reports, design feedback, documentation corrections, and feature proposals are welcome.

> **Contribution authorization:** ProjectPipeline is source-available, not open source. Contact the copyright holder before creating a fork or preparing a code contribution. Code pull requests are accepted only from explicitly authorized contributors under the terms in [LICENSE](LICENSE).

## Choose the right channel

- Use [GitHub Discussions](https://github.com/KevinSGarrett/ProjectPipeline/discussions) for questions, early ideas, and design conversations.
- Use the [bug report form](https://github.com/KevinSGarrett/ProjectPipeline/issues/new?template=bug_report.yml) for reproducible defects.
- Use the [feature request form](https://github.com/KevinSGarrett/ProjectPipeline/issues/new?template=feature_request.yml) for concrete product improvements.
- Use GitHub's [private vulnerability reporting](https://github.com/KevinSGarrett/ProjectPipeline/security/advisories/new) for suspected security issues.

Please search existing issues and discussions first. Do not publish credentials, private project exports, customer data, unredacted logs, sensitive screenshots, or local generated state.

## Development setup

ProjectPipeline supports Python 3.11–3.13.

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# macOS/Linux: . .venv/bin/activate

python -m pip install -r requirements/runtime.txt
python -m pip install -r requirements/development.txt
python -m pip install --no-deps -e .
python scripts/bootstrap_dev.py --root .
```

On Windows, `.\scripts\bootstrap_dev.ps1 -Root .` provides the PowerShell bootstrap path.

## Make a focused change

1. Confirm the problem and expected result.
2. Keep the change scoped to one cohesive outcome.
3. Add or update tests when behavior changes.
4. Update public documentation and contracts when users or integrations are affected.
5. Avoid unrelated formatting, generated output, local state, and machine-specific files.
6. Preserve compatibility, accessibility, security, and rollback behavior where applicable.

## Verify locally

Run the checks appropriate to the change. The full local quality contract is:

```bash
PYTHONPATH=src python -m project_pipeline quality --root . --strict-tools --coverage
```

At minimum, run the affected tests and public-checkout validation:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m project_pipeline validate --root .
python scripts/validate_public_repository.py --root .
```

## Open a pull request

Use a clear title and complete the pull request template. Explain:

- the problem and user-facing result;
- the important implementation choices;
- tests and manual checks performed;
- security, migration, compatibility, or rollback considerations;
- known limitations or follow-up work.

By contributing, you agree that your contribution may be maintained and distributed under this repository's license terms. Participation is also governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
