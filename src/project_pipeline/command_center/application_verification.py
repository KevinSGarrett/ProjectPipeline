from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


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
    checks["single_main"] = page.locator("main").count() == 1
    checks["single_h1"] = page.locator("h1").count() == 1
    checks["all_surfaces"] = all(
        page.locator(f"#{section}").count() == 1 for section in COMMAND_CENTER_REQUIRED_SECTIONS
    )
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
    return {
        "viewport": {"width": width, "height": height},
        "checks": checks,
        "initial_screenshot_path": initial_screenshot.relative_to(root).as_posix(),
        "initial_screenshot_sha256": _sha256(initial_screenshot),
        "post_interaction_viewport_screenshot_path": viewport_screenshot.relative_to(
            root
        ).as_posix(),
        "post_interaction_viewport_screenshot_sha256": _sha256(viewport_screenshot),
        "full_screenshot_path": full_screenshot.relative_to(root).as_posix(),
        "full_screenshot_sha256": _sha256(full_screenshot),
        "passed": all(checks.values()),
    }


def verify_command_center_ui(
    root: Path,
    *,
    chromium_path: str,
    viewports: tuple[tuple[int, int], ...] = ((1440, 900), (1024, 768), (390, 844)),
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("Playwright Python package is unavailable") from exc

    root = root.resolve()
    preview = root / "apps/command_center/preview/index.html"
    html = preview.read_text(encoding="utf-8")
    output_dir = root / "evidence/verification/command_center_ui_cycle015"
    output_dir.mkdir(parents=True, exist_ok=True)
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
                page.on(
                    "console",
                    lambda message, console_errors=console_errors: (
                        console_errors.append(message.text) if message.type == "error" else None
                    ),
                )
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

    result = {
        "schema_version": "1.0.0",
        "target": preview.relative_to(root).as_posix(),
        "browser": "Chromium via Playwright",
        "viewports": viewport_results,
        "forced_colors": {
            "overflow": forced_colors_overflow,
            "screenshot_path": forced_colors_screenshot.relative_to(root).as_posix(),
            "screenshot_sha256": _sha256(forced_colors_screenshot),
            "passed": not forced_colors_overflow,
        },
        "external_runtime_qualification": {
            "react_vite_dependency_install": "UNAVAILABLE_IN_EXECUTION_ENVIRONMENT",
            "tauri_rust_windows_build": "UNAVAILABLE_IN_EXECUTION_ENVIRONMENT",
            "claim": "NOT_CERTIFIED_BY_OFFLINE_PREVIEW",
        },
    }
    result["passed"] = (
        all(item["passed"] for item in viewport_results) and result["forced_colors"]["passed"]
    )
    target = root / "evidence/command_center_ui_browser_accessibility_cycle015.json"
    target.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return result
