from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from project_pipeline.command_center.application_verification import (
    evaluate_loaded_command_center_page,
)
from project_pipeline.command_center.live_server import LiveCommandCenterServer
from project_pipeline.verification.browser import find_chromium


def _http_status(url: str, *, token: str | None = None) -> tuple[int, Any]:
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload: Any = None
            if "json" in (response.headers.get("content-type") or ""):
                payload = json.loads(response.read().decode("utf-8"))
            return int(response.status), payload
    except urllib.error.HTTPError as error:
        payload = None
        try:
            payload = json.loads(error.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None
        return int(error.code), payload


def verify_live_command_center(
    root: Path,
    *,
    token: str = "cc-local-loopback",
    chromium_path: str | None = None,
    viewports: tuple[tuple[int, int], ...] = ((1440, 900), (1024, 768), (390, 844)),
) -> dict[str, Any]:
    root = root.resolve()
    chrome = chromium_path or find_chromium()
    if chrome is None:
        raise RuntimeError("system Chrome or Edge executable is required")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright Python package is unavailable") from exc

    server = LiveCommandCenterServer(root, token=token)
    base_url = server.start()
    output = root / "evidence/verification/command_center_live"
    output.mkdir(parents=True, exist_ok=True)
    checks: dict[str, bool] = {}
    unauthorized_status, _ = _http_status(f"{base_url}/api/v1/command-center/application")
    checks["rejects_missing_bearer"] = unauthorized_status == 401
    status, body = _http_status(f"{base_url}/api/v1/command-center/application", token=token)
    checks["application_ok"] = status == 200 and isinstance(body, dict)
    live_work = body.get("live_work", []) if isinstance(body, dict) else []
    checks["live_work_includes_pp385"] = any(
        item.get("work_id") == "PP-TASK-000385" for item in live_work
    )
    synchronization = body.get("synchronization", []) if isinstance(body, dict) else []
    jira = next((item for item in synchronization if item.get("system") == "Jira"), {})
    checks["jira_readback_not_stale"] = jira.get("stale") is False
    checks["jira_note_names_pp391"] = "PP-391" in str(jira.get("note", ""))
    checks["ui_not_authoritative"] = (
        isinstance(body, dict) and body.get("ui_state_authoritative") is False
    )

    viewport_results: list[dict[str, Any]] = []
    console_errors: list[str] = []
    forced_colors_overflow = True
    forced_colors_screenshot = output / "live_command_center_forced_colors_1440x900.png"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                executable_path=chrome,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            try:
                for width, height in viewports:
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page_errors: list[str] = []
                    page.on(
                        "console",
                        lambda message, page_errors=page_errors: (
                            page_errors.append(message.text) if message.type == "error" else None
                        ),
                    )
                    page.goto(f"{base_url}/", wait_until="load", timeout=20000)
                    result = evaluate_loaded_command_center_page(
                        page,
                        root=root,
                        output_dir=output,
                        width=width,
                        height=height,
                        name_prefix="live_command_center",
                    )
                    result["console_errors"] = page_errors
                    result["console_error_count"] = len(page_errors)
                    result["passed"] = bool(result["passed"]) and not page_errors
                    viewport_results.append(result)
                    console_errors.extend(page_errors)
                    page.close()

                contrast = browser.new_page(viewport={"width": 1440, "height": 900})
                contrast.emulate_media(forced_colors="active", reduced_motion="reduce")
                contrast.goto(f"{base_url}/", wait_until="load", timeout=20000)
                forced_colors_overflow = bool(
                    contrast.evaluate(
                        "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
                    )
                )
                forced_colors_screenshot = output / "live_command_center_forced_colors_1440x900.png"
                contrast.screenshot(path=str(forced_colors_screenshot), full_page=True)
                contrast.close()

                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(f"{base_url}/", wait_until="load", timeout=20000)
                checks["live_document"] = page.locator("main").count() == 1
                checks["live_title"] = page.locator("h1").count() == 1
                ws_result = page.evaluate(
                    """async (url) => {
                      const first = new WebSocket(url);
                      const opened = await new Promise((resolve) => {
                        const timer = setTimeout(() => resolve(false), 3000);
                        first.onopen = () => { clearTimeout(timer); resolve(true); };
                        first.onerror = () => { clearTimeout(timer); resolve(false); };
                      });
                      first.close();
                      const second = new WebSocket(url);
                      const reopened = await new Promise((resolve) => {
                        const timer = setTimeout(() => resolve(false), 3000);
                        second.onopen = () => { clearTimeout(timer); resolve(true); };
                        second.onerror = () => { clearTimeout(timer); resolve(false); };
                      });
                      second.close();
                      return {opened, reopened};
                    }""",
                    base_url.replace("http://", "ws://")
                    + "/api/v1/command-center/ws?token="
                    + token,
                )
                checks["websocket_connect"] = bool(ws_result.get("opened"))
                checks["websocket_reconnect"] = bool(ws_result.get("reopened"))
                page.close()
            finally:
                browser.close()
    finally:
        server.stop()

    result = {
        "schema_version": "1.0.0",
        "target": base_url,
        "browser": "system Chrome via Playwright",
        "checks": checks,
        "viewports": viewport_results,
        "forced_colors": {
            "overflow": forced_colors_overflow,
            "screenshot_path": forced_colors_screenshot.relative_to(root).as_posix(),
            "passed": not forced_colors_overflow,
        },
        "console_errors": console_errors,
        "screenshot_path": "evidence/verification/command_center_live/live_command_center_1440x900_full.png",
        "external_runtime_qualification": {
            "claim": "LIVE_LOOPBACK_COMMAND_CENTER",
            "server": "uvicorn loopback",
            "browser": "system Chrome",
        },
        "passed": (
            all(checks.values())
            and all(item["passed"] for item in viewport_results)
            and not forced_colors_overflow
            and not console_errors
        ),
    }
    (root / "evidence/command_center_live_browser.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result
