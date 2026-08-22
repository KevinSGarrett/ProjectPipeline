from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_pipeline.domain.verification import (
    AccessibilityEvidence,
    ArtifactKind,
    BrowserEvidence,
    MutationProbeResult,
    PerformanceResult,
    PostMergeReport,
    VerificationArtifact,
    VerificationCategory,
    VerificationCheckResult,
    VerificationCheckSpec,
    VerificationResultState,
    VerificationRun,
    verification_identifier,
)
from project_pipeline.manifest import write_manifest
from project_pipeline.verification.adversarial import run_adversarial_checks
from project_pipeline.verification.browser import (
    find_chromium,
    render_verification_report,
)
from project_pipeline.verification.faults import run_fault_scenarios
from project_pipeline.verification.golden import run_all as run_golden_journeys
from project_pipeline.verification.policy import VerificationPolicy
from project_pipeline.verification.property_checks import run_properties
from project_pipeline.verification.tools import activation_snapshot


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(
    root: Path, check_id: str, path: Path, kind: ArtifactKind, media_type: str
) -> VerificationArtifact:
    return VerificationArtifact(
        artifact_id=verification_identifier(
            "VART", check_id, path.relative_to(root).as_posix(), _sha_file(path)
        ),
        kind=kind,
        relative_path=path.relative_to(root).as_posix(),
        sha256=_sha_file(path),
        size_bytes=path.stat().st_size,
        media_type=media_type,
        produced_by_check_id=check_id,
    )


def _spec(
    name: str,
    category: VerificationCategory,
    description: str,
    *,
    command: tuple[str, ...] = (),
    required: bool = True,
    upstream_ids: tuple[str, ...] = (),
    requirement_ids: tuple[str, ...] = (),
    timeout_seconds: int = 300,
) -> VerificationCheckSpec:
    return VerificationCheckSpec(
        check_id=verification_identifier("VCHK", name, category.value, str(required), description),
        name=name,
        category=category,
        required=required,
        command=command,
        timeout_seconds=timeout_seconds,
        upstream_ids=upstream_ids,
        requirement_ids=requirement_ids,
        description=description,
    )


def default_check_specs() -> tuple[VerificationCheckSpec, ...]:
    py = sys.executable
    return (
        _spec(
            "Generated contract and schema suite",
            VerificationCategory.CONTRACT,
            "Validate generated domain contracts and schema compatibility.",
            command=(
                py,
                "-m",
                "pytest",
                "-q",
                "tests/test_contracts.py",
                "tests/test_assurance_compiler.py",
            ),
            requirement_ids=("REQ-ASSURE-0003", "REQ-ASSURE-0014", "REQ-ASSURE-0015"),
        ),
        _spec(
            "External API adapter contract suite",
            VerificationCategory.API,
            "Exercise Jira, GitHub, and provider protocol contracts through deterministic fake transports.",
            command=(
                py,
                "-m",
                "pytest",
                "-q",
                "tests/test_agent_router_adapters.py",
                "tests/test_jira_cloud_adapter.py",
                "tests/test_github_rest_adapter.py",
            ),
            requirement_ids=("REQ-ASSURE-0021", "REQ-ASSURE-0022"),
        ),
        _spec(
            "Cross-subsystem integration suite",
            VerificationCategory.INTEGRATION,
            "Exercise control, scheduler, context, orchestration, and budget integration boundaries.",
            command=(
                py,
                "-m",
                "pytest",
                "-q",
                "tests/test_control_kernel.py",
                "tests/test_scheduler_engine.py",
                "tests/test_context_service.py",
                "tests/test_orchestration_runtime.py",
                "tests/test_budget_integration.py",
            ),
            requirement_ids=("REQ-ASSURE-0022",),
        ),
        _spec(
            "Pass 16 end-to-end journey suite",
            VerificationCategory.END_TO_END,
            "Exercise Project Pipeline golden journeys across multiple deterministic subsystems.",
            command=(py, "-m", "pytest", "-q", "tests/test_verification_golden.py"),
            requirement_ids=("REQ-ASSURE-0024", "REQ-ASSURE-0025"),
        ),
        _spec(
            "Golden journey execution",
            VerificationCategory.GOLDEN_JOURNEY,
            "Run canonical Pass 16 golden journeys and capture structured evidence.",
            requirement_ids=("REQ-ASSURE-0024", "REQ-ASSURE-0025"),
        ),
        _spec(
            "Adversarial invariant probes",
            VerificationCategory.ADVERSARIAL,
            "Attempt silent skips, forged completion, and unsafe verifier-path inputs.",
            requirement_ids=("REQ-ASSURE-0023", "REQ-ASSURE-0029"),
        ),
        _spec(
            "Deterministic property probes",
            VerificationCategory.PROPERTY,
            "Generate deterministic property cases for completion and scheduler invariants.",
            upstream_ids=("UPSTREAM-051",),
            requirement_ids=("REQ-ASSURE-0021", "REQ-ASSURE-0022"),
        ),
        _spec(
            "Repository mutation probes",
            VerificationCategory.MUTATION,
            "Mutate repository contracts in isolated copies and require validators to detect the changes.",
            upstream_ids=("UPSTREAM-015", "UPSTREAM-101"),
            requirement_ids=("REQ-ASSURE-0021", "REQ-ASSURE-0022"),
            timeout_seconds=900,
        ),
        _spec(
            "Fault injection scenarios",
            VerificationCategory.FAULT,
            "Inject deterministic worker, acknowledgement, and uncertain-spend failures.",
            upstream_ids=("UPSTREAM-093",),
            requirement_ids=("REQ-RES-0019", "REQ-ASSURE-0023"),
        ),
        _spec(
            "Browser verification report",
            VerificationCategory.BROWSER,
            "Render the repository verification report in headless Chromium at desktop and mobile viewports.",
            upstream_ids=("UPSTREAM-063",),
            requirement_ids=("REQ-ASSURE-0021",),
        ),
        _spec(
            "Visual evidence capture",
            VerificationCategory.VISUAL,
            "Capture stable desktop/mobile screenshots and reject horizontal overflow or browser console errors.",
            upstream_ids=("UPSTREAM-063", "UPSTREAM-064", "UPSTREAM-111"),
            requirement_ids=("REQ-ASSURE-0021",),
        ),
        _spec(
            "Accessibility semantic baseline",
            VerificationCategory.ACCESSIBILITY,
            "Check language, landmarks, heading order, accessible names, labels, and ID uniqueness.",
            upstream_ids=("UPSTREAM-027", "UPSTREAM-063"),
            requirement_ids=("REQ-ASSURE-0021",),
        ),
        _spec(
            "Representative local performance budget",
            VerificationCategory.PERFORMANCE,
            "Measure repository validation and CLI startup against explicit local p95 budgets.",
            upstream_ids=("UPSTREAM-044",),
            requirement_ids=("REQ-ASSURE-0021",),
        ),
        _spec(
            "Post-merge repository verification",
            VerificationCategory.POST_MERGE,
            "Reconcile manifest, repository contract, traceability, evidence integrity, and required suite state.",
            requirement_ids=("REQ-ASSURE-0026", "REQ-ASSURE-0028", "REQ-ASSURE-0029"),
        ),
    )


class VerificationHarness:
    def __init__(self, root: Path, policy: VerificationPolicy) -> None:
        self.root = root.resolve()
        self.policy = policy
        self.output_dir = self.root / "evidence" / "verification"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _run_command(self, spec: VerificationCheckSpec) -> VerificationCheckResult:
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.root / "src")
        completed = subprocess.run(
            spec.command,
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
            check=False,
            shell=False,
        )
        duration = int((time.perf_counter() - started) * 1000)
        out = self.output_dir / "runs" / f"{spec.check_id}.stdout.txt"
        err = self.output_dir / "runs" / f"{spec.check_id}.stderr.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        artifacts: list[VerificationArtifact] = []
        if completed.stdout:
            out.write_text(completed.stdout, encoding="utf-8", newline="\n")
            artifacts.append(
                _artifact(self.root, spec.check_id, out, ArtifactKind.LOG, "text/plain")
            )
        elif out.exists():
            out.unlink()
        if completed.stderr:
            err.write_text(completed.stderr, encoding="utf-8", newline="\n")
            artifacts.append(
                _artifact(self.root, spec.check_id, err, ArtifactKind.LOG, "text/plain")
            )
        elif err.exists():
            err.unlink()
        state = (
            VerificationResultState.PASS
            if completed.returncode == 0
            else VerificationResultState.FAIL
        )
        return VerificationCheckResult(
            check_id=spec.check_id,
            state=state,
            required=spec.required,
            category=spec.category,
            duration_ms=duration,
            reason=f"command exit code {completed.returncode}",
            stdout_sha256=_sha_bytes(completed.stdout.encode("utf-8")),
            stderr_sha256=_sha_bytes(completed.stderr.encode("utf-8")),
            artifacts=tuple(artifacts),
            started_at_utc=started_at,
            completed_at_utc=datetime.now(UTC),
        )

    def _json_worker(self, worker: str, args: tuple[str, ...], *, timeout: int) -> Any:
        # Use files rather than PIPEs: optional runtime helpers may inherit stdout/stderr.
        # A descendant that keeps a pipe open must never hold the verification parent hostage.
        with tempfile.TemporaryDirectory(prefix="project-pipeline-worker-") as temp:
            out_path = Path(temp) / "stdout.txt"
            err_path = Path(temp) / "stderr.txt"
            with out_path.open("wb") as out, err_path.open("wb") as err:
                completed = subprocess.run(
                    (sys.executable, "-c", worker, *args),
                    cwd=self.root,
                    env={**os.environ, "PYTHONPATH": str(self.root / "src")},
                    stdout=out,
                    stderr=err,
                    timeout=timeout,
                    check=False,
                    shell=False,
                )
            stdout = out_path.read_text(encoding="utf-8", errors="replace")
            stderr = err_path.read_text(encoding="utf-8", errors="replace")
        if completed.returncode != 0:
            raise RuntimeError(
                f"isolated verification worker failed: exit={completed.returncode}; "
                f"stdout={stdout}; stderr={stderr}"
            )
        return json.loads(stdout)

    def _isolated_mutation_probes(self) -> tuple[MutationProbeResult, ...]:
        worker = """
import json, sys
from pathlib import Path
from project_pipeline.verification.mutation import run_mutation_probes
values = run_mutation_probes(Path(sys.argv[1]).resolve())
print(json.dumps([item.model_dump(mode='json') for item in values], default=str))
sys.stdout.flush()
__import__('os')._exit(0)
"""
        payload = self._json_worker(worker, (str(self.root),), timeout=90)
        return tuple(MutationProbeResult.model_validate(item) for item in payload)

    def _isolated_performance(self) -> tuple[PerformanceResult, ...]:
        worker = """
import json, sys
from pathlib import Path
from project_pipeline.verification.performance import repository_validation_performance, cli_help_performance
root = Path(sys.argv[1]).resolve()
values = (
    repository_validation_performance(root, samples=int(sys.argv[2])),
    cli_help_performance(root, samples=int(sys.argv[3]), p95_budget_ms=int(sys.argv[4])),
)
print(json.dumps([item.model_dump(mode='json') for item in values], default=str))
sys.stdout.flush()
__import__('os')._exit(0)
"""
        payload = self._json_worker(
            worker,
            (
                str(self.root),
                str(max(3, self.policy.performance_samples // 2)),
                str(self.policy.performance_samples),
                str(self.policy.cli_help_p95_budget_ms),
            ),
            timeout=90,
        )
        return tuple(PerformanceResult.model_validate(item) for item in payload)

    def _isolated_post_merge(self, *, required_test_suite_ok: bool) -> PostMergeReport:
        worker = """
import json, sys
from pathlib import Path
from project_pipeline.verification.post_merge import evaluate_post_merge
value = evaluate_post_merge(Path(sys.argv[1]).resolve(), required_test_suite_ok=sys.argv[2] == '1')
print(json.dumps(value.model_dump(mode='json'), default=str))
sys.stdout.flush()
__import__('os')._exit(0)
"""
        payload = self._json_worker(
            worker,
            (str(self.root), "1" if required_test_suite_ok else "0"),
            timeout=45,
        )
        return PostMergeReport.model_validate(payload)

    def _browser_preflight(self) -> tuple[str | None, dict[str, Any] | None, int, str | None]:
        manifest = json.loads((self.root / "PROJECT_MANIFEST.json").read_text(encoding="utf-8"))
        coverage = json.loads(
            (self.root / "plans/_traceability/coverage_report.json").read_text(encoding="utf-8")
        )
        jira_index = json.loads(
            (self.root / "jira/indexes/issues_by_id.json").read_text(encoding="utf-8")
        )
        report_path = render_verification_report(
            self.root,
            summary={
                "repository_files": manifest.get("file_count"),
                "repository_aggregate_sha256": manifest.get("aggregate_sha256"),
                "requirements": coverage.get("requirement_count"),
                "unexplained_traceability_gaps": coverage.get(
                    "unexplained_gap_count", coverage.get("gap_count")
                ),
                "jira_issues": len(jira_index),
                "completion_authority": "Execution Assurance Completion Gate",
            },
        )
        chromium = find_chromium(self.policy.system_chromium_candidates)
        if chromium is None:
            return None, None, 0, None
        worker = """
import json
import sys
import tempfile
from pathlib import Path
from project_pipeline.verification.browser import verify_report
root = Path(sys.argv[1]).resolve()
report = Path(sys.argv[2]).resolve()
chromium = sys.argv[3]
viewports = tuple(tuple(int(v) for v in pair) for pair in json.loads(sys.argv[4]))
browser, accessibility = verify_report(root, report, chromium_path=chromium, viewports=viewports)
print(json.dumps({
    'browser': [item.model_dump(mode='json') for item in browser],
    'accessibility': accessibility.model_dump(mode='json'),
}, default=str))
sys.stdout.flush()
__import__('os')._exit(0)
"""
        started = time.perf_counter()
        try:
            payload = self._json_worker(
                worker,
                (
                    str(self.root),
                    str(report_path),
                    chromium,
                    json.dumps(self.policy.screenshot_viewports),
                ),
                timeout=60,
            )
            duration = int((time.perf_counter() - started) * 1000)
            return chromium, payload, duration, None
        except Exception as exc:
            return (
                chromium,
                None,
                int((time.perf_counter() - started) * 1000),
                f"{type(exc).__name__}: {exc}",
            )

    def run(self) -> tuple[VerificationRun, dict[str, object]]:
        specs = default_check_specs()
        results: list[VerificationCheckResult] = []
        details: dict[str, object] = {}
        executed_upstreams: set[str] = set()
        evidence_by_upstream: dict[str, tuple[str, ...]] = {}
        run_started = datetime.now(UTC)
        by_category = {spec.category: spec for spec in specs if not spec.command}
        chromium, browser_payload, browser_duration, browser_error = self._browser_preflight()
        command_specs = [spec for spec in specs if spec.command]
        for spec in command_specs:
            results.append(self._run_command(spec))

        def direct(
            category: VerificationCategory,
            callback: Callable[[], Any],
            serializer: Callable[[Any], Any],
            *,
            evidence_name: str,
            success: Callable[[Any], bool] | None = None,
        ) -> Any:
            spec = by_category[category]
            started_at = datetime.now(UTC)
            started = time.perf_counter()
            state = VerificationResultState.PASS
            reason = "verification passed"
            try:
                value = callback()
                payload = serializer(value)
                if success is not None and not success(value):
                    state = VerificationResultState.FAIL
                    reason = "verification result did not satisfy required success predicate"
            except Exception as exc:
                value = None
                payload = {"error": type(exc).__name__, "message": str(exc)}
                state = VerificationResultState.FAIL
                reason = f"{type(exc).__name__}: {exc}"
            duration = int((time.perf_counter() - started) * 1000)
            target = self.output_dir / evidence_name
            target.write_text(
                json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
            )
            results.append(
                VerificationCheckResult(
                    check_id=spec.check_id,
                    state=state,
                    required=spec.required,
                    category=category,
                    duration_ms=duration,
                    reason=reason,
                    artifacts=(
                        _artifact(
                            self.root, spec.check_id, target, ArtifactKind.JSON, "application/json"
                        ),
                    ),
                    started_at_utc=started_at,
                    completed_at_utc=datetime.now(UTC),
                )
            )
            return value

        journeys = direct(
            VerificationCategory.GOLDEN_JOURNEY,
            lambda: run_golden_journeys(self.root),
            lambda value: [item.model_dump(mode="json") for item in value],
            evidence_name="golden_journeys.json",
            success=lambda value: all(item.state is VerificationResultState.PASS for item in value),
        )
        details["golden_journeys"] = journeys
        adversarial = direct(
            VerificationCategory.ADVERSARIAL,
            lambda: run_adversarial_checks(self.root),
            lambda value: {"observations": list(value)},
            evidence_name="adversarial_checks.json",
        )
        details["adversarial"] = adversarial
        properties = direct(
            VerificationCategory.PROPERTY,
            lambda: run_properties(
                self.root, seed=self.policy.property_seed, cases=self.policy.property_case_count
            ),
            lambda value: [item.model_dump(mode="json") for item in value],
            evidence_name="property_probes.json",
            success=lambda value: all(item.passed for item in value),
        )
        details["properties"] = properties
        mutations = direct(
            VerificationCategory.MUTATION,
            self._isolated_mutation_probes,
            lambda value: [item.model_dump(mode="json") for item in value],
            evidence_name="mutation_probes.json",
            success=lambda value: all(item.detected for item in value),
        )
        details["mutations"] = mutations
        faults = direct(
            VerificationCategory.FAULT,
            lambda: run_fault_scenarios(self.root),
            lambda value: [item.model_dump(mode="json") for item in value],
            evidence_name="fault_scenarios.json",
            success=lambda value: all(item.passed for item in value),
        )
        details["faults"] = faults

        browser_spec = by_category[VerificationCategory.BROWSER]
        visual_spec = by_category[VerificationCategory.VISUAL]
        a11y_spec = by_category[VerificationCategory.ACCESSIBILITY]
        if chromium is None:
            for spec in (browser_spec, visual_spec, a11y_spec):
                results.append(
                    VerificationCheckResult(
                        check_id=spec.check_id,
                        state=VerificationResultState.BLOCKED,
                        required=spec.required,
                        category=spec.category,
                        duration_ms=0,
                        reason="Playwright-capable Chromium executable is unavailable",
                    )
                )
        elif browser_error is not None or browser_payload is None:
            for spec in (browser_spec, visual_spec, a11y_spec):
                results.append(
                    VerificationCheckResult(
                        check_id=spec.check_id,
                        state=VerificationResultState.FAIL,
                        required=spec.required,
                        category=spec.category,
                        duration_ms=browser_duration,
                        reason=browser_error or "browser preflight produced no payload",
                        started_at_utc=run_started,
                        completed_at_utc=datetime.now(UTC),
                    )
                )
        else:
            browser_values = tuple(
                BrowserEvidence.model_validate(item) for item in browser_payload["browser"]
            )
            accessibility = AccessibilityEvidence.model_validate(browser_payload["accessibility"])
            browser_pass = all(item.passed for item in browser_values)
            browser_json = self.output_dir / "browser_evidence.json"
            browser_json.write_text(
                json.dumps(
                    [item.model_dump(mode="json") for item in browser_values],
                    indent=2,
                    sort_keys=True,
                    default=str,
                )
                + "\n",
                encoding="utf-8",
            )
            a11y_json = self.output_dir / "accessibility_evidence.json"
            a11y_json.write_text(
                json.dumps(
                    accessibility.model_dump(mode="json"), indent=2, sort_keys=True, default=str
                )
                + "\n",
                encoding="utf-8",
            )
            screenshot_artifacts = tuple(
                _artifact(
                    self.root,
                    browser_spec.check_id,
                    self.root / item.screenshot_path,
                    ArtifactKind.SCREENSHOT,
                    "image/png",
                )
                for item in browser_values
            )
            results.append(
                VerificationCheckResult(
                    check_id=browser_spec.check_id,
                    state=VerificationResultState.PASS
                    if browser_pass
                    else VerificationResultState.FAIL,
                    required=browser_spec.required,
                    category=VerificationCategory.BROWSER,
                    duration_ms=browser_duration,
                    reason="headless Chromium browser checks passed"
                    if browser_pass
                    else "browser evidence contains failures",
                    artifacts=(
                        _artifact(
                            self.root,
                            browser_spec.check_id,
                            browser_json,
                            ArtifactKind.JSON,
                            "application/json",
                        ),
                        *screenshot_artifacts,
                    ),
                    started_at_utc=run_started,
                    completed_at_utc=datetime.now(UTC),
                )
            )
            results.append(
                VerificationCheckResult(
                    check_id=visual_spec.check_id,
                    state=VerificationResultState.PASS
                    if browser_pass
                    else VerificationResultState.FAIL,
                    required=visual_spec.required,
                    category=VerificationCategory.VISUAL,
                    duration_ms=browser_duration,
                    reason="desktop/mobile screenshots captured without overflow or console errors"
                    if browser_pass
                    else "visual/browser evidence contains failures",
                    artifacts=screenshot_artifacts,
                    started_at_utc=run_started,
                    completed_at_utc=datetime.now(UTC),
                )
            )
            results.append(
                VerificationCheckResult(
                    check_id=a11y_spec.check_id,
                    state=VerificationResultState.PASS
                    if accessibility.passed
                    else VerificationResultState.FAIL,
                    required=a11y_spec.required,
                    category=VerificationCategory.ACCESSIBILITY,
                    duration_ms=browser_duration,
                    reason=f"semantic accessibility baseline violations={accessibility.violation_count}",
                    artifacts=(
                        _artifact(
                            self.root,
                            a11y_spec.check_id,
                            a11y_json,
                            ArtifactKind.JSON,
                            "application/json",
                        ),
                    ),
                    started_at_utc=run_started,
                    completed_at_utc=datetime.now(UTC),
                )
            )
            executed_upstreams.add("UPSTREAM-063")
            evidence_by_upstream["UPSTREAM-063"] = (
                browser_json.relative_to(self.root).as_posix(),
                *tuple(item.screenshot_path for item in browser_values),
            )
            details["browser"] = browser_values
            details["accessibility"] = accessibility

        # Browser evidence changes the governed tree. Refresh before performance so
        # repository-validator samples measure a clean, self-consistent state.
        write_manifest(self.root)
        performance = direct(
            VerificationCategory.PERFORMANCE,
            self._isolated_performance,
            lambda value: [item.model_dump(mode="json") for item in value],
            evidence_name="performance_results.json",
            success=lambda value: all(item.passed for item in value),
        )
        details["performance"] = performance

        # Every generated verification artifact must be included before post-merge manifest validation.
        write_manifest(self.root)
        pre_post_results_ok = all(
            item.state is VerificationResultState.PASS for item in results if item.required
        )
        post_merge = direct(
            VerificationCategory.POST_MERGE,
            lambda: self._isolated_post_merge(required_test_suite_ok=pre_post_results_ok),
            lambda value: value.model_dump(mode="json"),
            evidence_name="post_merge_report.json",
            success=lambda value: value.final_passed,
        )
        details["post_merge"] = post_merge

        # The post-merge JSON itself changes the governed tree, so refresh the manifest again.
        write_manifest(self.root)
        source_fingerprint = json.loads(
            (self.root / "PROJECT_MANIFEST.json").read_text(encoding="utf-8")
        )["aggregate_sha256"]
        failures = sum(
            item.required and item.state is VerificationResultState.FAIL for item in results
        )
        blocked = sum(
            item.required and item.state is VerificationResultState.BLOCKED for item in results
        )
        skipped = sum(
            (not item.required) and item.state is VerificationResultState.SKIPPED
            for item in results
        )
        final_state = (
            VerificationResultState.FAIL
            if failures
            else VerificationResultState.BLOCKED
            if blocked
            else VerificationResultState.PASS
        )
        run_completed = datetime.now(UTC)
        run_id = verification_identifier(
            "VRUN",
            self.policy.project_id,
            self.policy.profile,
            source_fingerprint,
            *[f"{item.check_id}:{item.state.value}" for item in results],
        )
        run = VerificationRun(
            run_id=run_id,
            project_id=self.policy.project_id,
            profile=self.policy.profile,
            source_fingerprint=source_fingerprint,
            results=tuple(results),
            final_state=final_state,
            required_fail_count=failures,
            required_blocked_count=blocked,
            optional_skipped_count=skipped,
            started_at_utc=run_started,
            completed_at_utc=run_completed,
        )
        activation_values = activation_snapshot(
            self.root,
            executed_upstream_ids=tuple(sorted(executed_upstreams)),
            evidence_by_upstream=evidence_by_upstream,
        )
        details["activations"] = activation_values
        return run, details
