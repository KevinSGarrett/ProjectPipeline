# Contributing to ProjectPipeline

Thanks for helping improve ProjectPipeline. Small, well-explained contributions are welcome.

## Before you begin

- Search existing issues and discussions before opening a new one.
- Use Issues for defects and concrete feature proposals; use Discussions for questions and design conversations.
- Do not include credentials, private project exports, customer data, screenshots with sensitive information, or generated local state in a contribution.

## Development setup

ProjectPipeline supports Python 3.11–3.13.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pytest -q
```

Keep changes focused, add or update tests when behavior changes, and explain the user-facing result in the pull request. Please do not bundle unrelated formatting or generated files with a functional change.

## Pull requests

1. Fork the repository and create a focused branch.
2. Describe the problem, the solution, and how you verified it.
3. Keep secrets and machine-specific files out of the diff.
4. Be respectful and constructive in review.

By contributing, you agree that your contribution may be maintained and distributed under this repository's license terms. See [SECURITY.md](SECURITY.md) for vulnerability reporting and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community expectations.
