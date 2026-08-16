
# Validate the Repository

1. Open a terminal at the repository root.
2. Run `PYTHONPATH=src python -m project_pipeline validate --root .`.
3. Run `PYTHONPATH=src python -m unittest discover -s tests -v`.
4. Review every error. Warnings require disposition before release even when they do not fail the command.
5. Regenerate maps and manifests after any file change.
6. Repeat validation until results correspond to the exact archive candidate.
