from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import ConsoleMessage

from project_pipeline.command_center.desktop_qualification import observe_desktop_toolchain


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


COMMAND_CENTER_REQUIRED_SECTIONS = (
    "overview",
    "graph",
    "work",
    "health",
    "budgets",
    "providers",
    "context",
    "recovery",
    "director",
    "incidents",
    "approvals",
    "sync",
    "evidence",
)


def evaluate_loaded_command_center_page(
    page: Any,
    *,
    root: Path,
    output_dir: Path,
    width: int,
    height: int,
    name_prefix: str,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    page.wait_for_function(
        "() => document.body.dataset.liveHydrated === 'true' || document.body.dataset.liveHydrated === 'skipped' || !(window.CC_LIVE_TOKEN || window.__PP_MEMORY_SESSION__)",
        timeout=8000,
    )
    checks["single_main"] = page.locator("main").count() == 1
    checks["single_h1"] = page.locator("h1").count() == 1
    checks["all_surfaces"] = all(
        page.locator(f"#{section}").count() == 1 for section in COMMAND_CENTER_REQUIRED_SECTIONS
    )
    budgets = page.locator("#budgets").inner_text().casefold()
    providers = page.locator("#providers").inner_text().casefold()
    approvals = page.locator("#approvals").inner_text().casefold()
    recovery = page.locator("#recovery").inner_text().casefold()
    context = page.locator("#context").inner_text().casefold()
    evidence = page.locator("#evidence").inner_text().casefold()
    sync = page.locator("#sync").inner_text().casefold()
    work = page.locator("#work").inner_text().casefold()
    graph = page.locator("#graph").inner_text().casefold()
    checks["cost_drilldown"] = "forecast" in budgets and "openai" in budgets
    checks["agent_performance"] = "success" in providers and "latency" in providers
    checks["approval_center"] = "risk" in approvals and "requester" in approvals
    checks["recovery_center"] = "checkpoint" in recovery and "runbook" in recovery
    checks["context_health"] = "freshness" in context and "coverage" in context
    checks["visual_qa_evidence"] = "evid-" in evidence and "verified" in evidence
    checks["jira_github_sync"] = "jira" in sync and "github" in sync
    checks["live_work_fields"] = all(
        token in work for token in ("worker", "workspace", "lease", "next")
    )
    checks["interactive_graph"] = all(
        token in graph for token in ("requirement", "story", "task", "evidence")
    )
    if page.evaluate(
        "() => Boolean(window.CC_LIVE_TOKEN || (window.__PP_MEMORY_SESSION__ && window.__PP_MEMORY_SESSION__.token))"
    ):
        checks["hydrated_in_progress_work"] = "pp-task-000385" in work
    checks["no_horizontal_overflow"] = not bool(
        page.evaluate(
            "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
    )
    checks["button_names"] = bool(
        page.evaluate(
            "() => [...document.querySelectorAll('button')].every(x => (x.innerText || x.getAttribute('aria-label') || '').trim().length > 0)"
        )
    )
    checks["unique_ids"] = bool(
        page.evaluate(
            "() => { const ids=[...document.querySelectorAll('[id]')].map(x=>x.id); return new Set(ids).size===ids.length; }"
        )
    )
    checks["topbar_visible_initially"] = page.locator(".topbar").is_visible()
    initial_screenshot = output_dir / f"{name_prefix}_{width}x{height}_initial.png"
    page.screenshot(path=str(initial_screenshot), full_page=False)
    page.keyboard.press("Tab")
    checks["skip_link_first_focus"] = page.evaluate(
        "() => document.activeElement?.classList.contains('skip-link') === true"
    )
    page.locator("#graph-search").fill("evidence")
    visible_graph_nodes = page.locator(".graph-node:not([hidden])").count()
    checks["graph_filter_interaction"] = visible_graph_nodes == 1
    page.locator("#graph-search").fill("")
    page.locator("[data-control='pause-new']").click()
    checks["preview_control_is_non_mutating"] = (
        "intentionally not executed"
        in page.locator(".rail-card.sticky .control-status").inner_text()
    )
    page.locator("#director-message").fill("What is blocked?")
    page.locator("#director-form button[type='submit']").click()
    checks["director_chat_grounded_preview"] = (
        "no action was executed" in page.locator("#director-log").inner_text().lower()
    )
    checks["director_chat_status_non_mutating"] = (
        "raw chat mutation remains disabled"
        in page.locator("#director-status").inner_text().lower()
    )
    page.locator("[data-incident-action='resolve']").click()
    checks["incident_resolve_blocked_before_verify"] = (
        "resolve remains blocked" in page.locator("#incident-status").inner_text().lower()
    )
    page.locator("[data-incident-action='verify']").click()
    page.locator("[data-incident-action='resolve']").click()
    checks["incident_verified_then_resolved_preview"] = (
        page.locator("#incident-state").inner_text() == "RESOLVED"
    )
    page.locator("[data-inbox-action='notify']").click()
    notification_text = page.locator("#notification-status").inner_text().lower()
    checks["notification_preview_preserves_qualification"] = (
        "native click handling remains unqualified" in notification_text
        and "remote delivery remains off" in notification_text
    )
    if width <= 860:
        checks["mobile_menu_available"] = page.locator(".menu-button").is_visible()
        page.locator(".menu-button").click()
        checks["mobile_menu_expands"] = (
            page.locator(".menu-button").get_attribute("aria-expanded") == "true"
        )
        page.locator(".menu-button").click()
        checks["mobile_menu_collapses"] = (
            page.locator(".menu-button").get_attribute("aria-expanded") == "false"
        )
    page.evaluate("() => window.scrollTo(0, 0)")
    viewport_screenshot = output_dir / f"{name_prefix}_{width}x{height}_viewport.png"
    page.screenshot(path=str(viewport_screenshot), full_page=False)
    full_screenshot = output_dir / f"{name_prefix}_{width}x{height}_full.png"
    page.screenshot(path=str(full_screenshot), full_page=True)

    def relative(path: Path) -> str:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return path.name

    return {
        "viewport": {"width": width, "height": height},
        "checks": checks,
        "initial_screenshot_path": relative(initial_screenshot),
        "initial_screenshot_sha256": _sha256(initial_screenshot),
        "post_interaction_viewport_screenshot_path": relative(viewport_screenshot),
        "post_interaction_viewport_screenshot_sha256": _sha256(viewport_screenshot),
        "full_screenshot_path": relative(full_screenshot),
        "full_screenshot_sha256": _sha256(full_screenshot),
        "passed": all(checks.values()),
    }


def verify_command_center_ui(
    root: Path,
    *,
    chromium_path: str,
    viewports: tuple[tuple[int, int], ...] = ((1440, 900), (1024, 768), (390, 844)),
    write_evidence: bool = False,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("Playwright Python package is unavailable") from exc

    root = root.resolve()
    preview = root / "apps/command_center/preview/index.html"
    html = preview.read_text(encoding="utf-8")
    staged_dir: tempfile.TemporaryDirectory[str] | None = None
    if write_evidence:
        output_dir = root / "evidence/verification/command_center_ui_cycle015"
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        staged_dir = tempfile.TemporaryDirectory(prefix="cc-ui-preview-")
        output_dir = Path(staged_dir.name)
    viewport_results: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=chromium_path,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            for width, height in viewports:
                page = browser.new_page(viewport={"width": width, "height": height})
                console_errors: list[str] = []

                def _on_console(
                    message: ConsoleMessage, _errors: list[str] = console_errors
                ) -> None:
                    if message.type == "error":
                        _errors.append(message.text)

                page.on("console", _on_console)
                page.set_content(html, wait_until="load", timeout=15000)
                result = evaluate_loaded_command_center_page(
                    page,
                    root=root,
                    output_dir=output_dir,
                    width=width,
                    height=height,
                    name_prefix="command_center_cycle015",
                )
                result["console_error_count"] = len(console_errors)
                result["console_errors"] = console_errors
                result["passed"] = bool(result["passed"]) and not console_errors
                viewport_results.append(result)
                page.close()

            contrast = browser.new_page(viewport={"width": 1440, "height": 900})
            contrast.emulate_media(forced_colors="active", reduced_motion="reduce")
            contrast.set_content(html, wait_until="load", timeout=15000)
            forced_colors_overflow = bool(
                contrast.evaluate(
                    "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
                )
            )
            forced_colors_screenshot = (
                output_dir / "command_center_cycle015_forced_colors_1440x900.png"
            )
            contrast.screenshot(path=str(forced_colors_screenshot), full_page=True)
            contrast.close()
        finally:
            browser.close()

    def relative_artifact(path: Path) -> str:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return path.name

    result = {
        "schema_version": "1.0.0",
        "target": preview.relative_to(root).as_posix(),
        "browser": "Chromium via Playwright",
        "viewports": viewport_results,
        "forced_colors": {
            "overflow": forced_colors_overflow,
            "screenshot_path": relative_artifact(forced_colors_screenshot),
            "screenshot_sha256": _sha256(forced_colors_screenshot),
            "passed": not forced_colors_overflow,
        },
        "external_runtime_qualification": {
            **observe_desktop_toolchain(),
            "claim": "NOT_CERTIFIED_BY_OFFLINE_PREVIEW",
        },
    }
    result["passed"] = (
        all(item["passed"] for item in viewport_results) and result["forced_colors"]["passed"]
    )
    if write_evidence:
        target = root / "evidence/command_center_ui_browser_accessibility_cycle015.json"
        target.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
    if staged_dir is not None:
        staged_dir.cleanup()
    return result
