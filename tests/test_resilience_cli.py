import hashlib
import json
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


def test_resilience_cli_backup_and_restore_plans(project_root, tmp_path):
    a = run(project_root, "backup-plan", "--domain", "canonical_state", "--source", "postgres")
    assert a.returncode == 0 and "PGBACKREST" in a.stdout
    isolated = tmp_path / "recovery" / "test-db"
    isolated.mkdir(parents=True)
    b = run(
        project_root,
        "restore-plan",
        "--domain",
        "canonical_state",
        "--target",
        str(isolated),
    )
    assert b.returncode == 0 and "verification_required" in b.stdout
    denied = run(
        project_root,
        "restore-plan",
        "--domain",
        "canonical_state",
        "--target",
        ".local/recovery/test-db",
    )
    assert denied.returncode != 0
    assert "isolated target" in denied.stdout


def test_resilience_cli_restore_apply_requires_approval_and_isolated_root(project_root, tmp_path):
    allow = tmp_path / "isolate"
    source = tmp_path / "backup"
    target = allow / "restored"
    allow.mkdir()
    source.mkdir()
    payload = b"state"
    (source / "state.db").write_bytes(payload)
    manifest = tmp_path / "manifest.json"
    digest = hashlib.sha256(payload).hexdigest()
    manifest.write_text(
        json.dumps(
            {
                "entries": [{"path": "state.db", "sha256": digest, "size_bytes": len(payload)}],
            }
        ),
        encoding="utf-8",
    )
    denied = run(
        project_root,
        "restore-apply",
        "--allow-root",
        str(allow),
        "--intent-id",
        "missing",
        "--source",
        str(source),
        "--database",
        str(tmp_path / "restore.db"),
    )
    assert denied.returncode != 0
    recorded = run(
        project_root,
        "restore-intent",
        "--allow-root",
        str(allow),
        "--target",
        str(target),
        "--domain",
        "canonical_state",
        "--idempotency-key",
        "cli-restore-1",
        "--manifest",
        str(manifest),
        "--database",
        str(tmp_path / "restore.db"),
    )
    assert recorded.returncode == 0
    intent_id = json.loads(recorded.stdout)["restore_intent"]["intent_id"]
    applied = run(
        project_root,
        "restore-apply",
        "--allow-root",
        str(allow),
        "--intent-id",
        intent_id,
        "--source",
        str(source),
        "--database",
        str(tmp_path / "restore.db"),
        "--apply",
        "--approve",
    )
    assert applied.returncode == 0
    verified = run(
        project_root,
        "restore-verify",
        "--allow-root",
        str(allow),
        "--intent-id",
        intent_id,
        "--manifest",
        str(manifest),
        "--database",
        str(tmp_path / "restore.db"),
    )
    assert verified.returncode == 0
    assert "VERIFY_PASSED" in verified.stdout


def test_resilience_cli_status_applies_migration(project_root, tmp_path):
    r = run(project_root, "status", "--database", str(tmp_path / "resilience.db"))
    assert r.returncode == 0 and "resilience_recovery_objectives" in r.stdout
