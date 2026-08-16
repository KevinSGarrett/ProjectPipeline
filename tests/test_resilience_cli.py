import os
import subprocess
import sys


def run(root, *args):
    return subprocess.run(
        [sys.executable, "-m", "project_pipeline", "resilience", *args, "--root", str(root)],
        cwd=root,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(root / "src")},
    )


def test_resilience_cli_simulation_and_aws_plan(project_root):
    a = run(project_root, "simulate", "--scenario", "split-brain")
    assert a.returncode == 0 and "deterministic_authority_preserved" in a.stdout
    b = run(project_root, "aws-plan")
    assert b.returncode == 0 and "LOCAL" in b.stdout and "live_cloud_mutation_performed" in b.stdout


def test_resilience_cli_backup_and_restore_plans(project_root):
    a = run(project_root, "backup-plan", "--domain", "canonical_state", "--source", "postgres")
    assert a.returncode == 0 and "PGBACKREST" in a.stdout
    b = run(
        project_root,
        "restore-plan",
        "--domain",
        "canonical_state",
        "--target",
        ".local/recovery/test-db",
    )
    assert b.returncode == 0 and "verification_required" in b.stdout


def test_resilience_cli_status_applies_migration(project_root, tmp_path):
    r = run(project_root, "status", "--database", str(tmp_path / "resilience.db"))
    assert r.returncode == 0 and "resilience_recovery_objectives" in r.stdout
