from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_pipeline.configuration import load_runtime_configuration
from project_pipeline.runtime import BootstrapState, run_bootstrap, run_foundation_smoke

ROOT = Path(__file__).resolve().parents[1]


class RuntimeFoundationTests(unittest.TestCase):
    def test_bootstrap_reports_required_foundation_ready(self) -> None:
        configuration = load_runtime_configuration(ROOT, profile="local", environment={})
        report = run_bootstrap(
            ROOT,
            configuration,
            prepare=False,
            validate_repository=False,
            correlation_id="corr:test-bootstrap",
        )
        self.assertNotEqual(report.state, BootstrapState.BLOCKED)
        required = [check for check in report.checks if check.required]
        self.assertEqual([check.status for check in required], ["PASS"] * len(required))

    def test_prepare_creates_runtime_paths_in_isolated_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config" / "runtime" / "profiles").mkdir(parents=True)
            for relative in (
                "config/runtime/base.json",
                "config/runtime/profiles/local.json",
            ):
                source = ROOT / relative
                target = root / relative
                target.write_bytes(source.read_bytes())
            configuration = load_runtime_configuration(root, profile="local", environment={})
            report = run_bootstrap(
                root,
                configuration,
                prepare=True,
                validate_repository=False,
                correlation_id="corr:test-prepare",
            )
            runtime_paths = configuration.settings.runtime_paths(root)
            self.assertTrue(all(path.is_dir() for path in runtime_paths.values()))
            self.assertTrue(report.ok)

    def test_foundation_smoke_is_idempotent_and_integrity_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config" / "runtime" / "profiles").mkdir(parents=True)
            for relative in (
                "config/runtime/base.json",
                "config/runtime/profiles/ci.json",
            ):
                source = ROOT / relative
                target = root / relative
                target.write_bytes(source.read_bytes())
            configuration = load_runtime_configuration(root, profile="ci", environment={})
            report = run_foundation_smoke(root, configuration, correlation_id="corr:test-smoke")
            self.assertTrue(report.ok)
            self.assertTrue(report.replayed)
            self.assertTrue(report.artifact_verified)
            self.assertTrue(Path(report.journal_root).is_dir())
