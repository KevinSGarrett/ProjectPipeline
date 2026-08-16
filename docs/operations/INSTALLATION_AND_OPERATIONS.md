# Installation and Operations Guide

## Local Python
Create the environment using `scripts/bootstrap_dev.py` or the documented `uv` workflow, validate configuration, then run `python -m project_pipeline validate --root .`. The resolver-generated `uv.lock` remains a release prerequisite; the current resolver-lock state is recorded in `config/dependency_policy.json` and must be `READY` before a production release.

The bounded Command Center service can be source-checked with `PYTHONPATH=src python scripts/run_command_center_service.py --root . --check`. Starting the service requires an operator-provided `PROJECT_PIPELINE_COMMAND_CENTER_TOKEN` and the optional API dependencies.

## Windows
Use `infrastructure/windows/ProjectPipelineService.xml` with a separately acquired and digest-verified WinSW executable. Installation, verification, upgrade, rollback, and uninstall sources are under `scripts/windows/`. They are not runtime-qualified until exercised on an authorized Windows target.

## Docker
Use `infrastructure/docker/`. An immutable base-image digest must be supplied explicitly. No default mutable tag is committed. Docker runtime qualification is currently outstanding.

## AWS
The local-primary recovery-spine Terraform under `infrastructure/aws/terraform/` remains disabled by default. Live apply requires an authorized AWS target, scoped credentials, cost review, Terraform validation/plan evidence, and rollback/cleanup evidence.

## Backup and recovery
Follow `runbooks/backup_restore_verification.md`, `runbooks/control_machine_failover.md`, and `runbooks/release_upgrade_and_rollback.md`. Restore verification is a separate state from backup success.
