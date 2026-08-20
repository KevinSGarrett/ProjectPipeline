from __future__ import annotations

import hashlib
import html
import importlib.util
import os
import shutil
import time
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any

from project_pipeline.domain.verification import (
    AccessibilityEvidence,
    BrowserEvidence,
    verification_identifier,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_verification_report(root: Path, *, summary: dict[str, Any]) -> Path:
    target = root / "evidence" / "verification" / "pass16_verification_report.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    metrics = "\n".join(
        f"<tr><th scope='row'>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in sorted(summary.items())
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Project Pipeline Pass 16 Verification Report</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
body {{ margin: 0; line-height: 1.5; }}
header, main, footer {{ width: min(1100px, calc(100% - 2rem)); margin-inline: auto; }}
header {{ padding-block: 2rem 1rem; }}
main {{ padding-block: 1rem 3rem; }}
section {{ border: 1px solid currentColor; border-radius: .5rem; padding: 1rem; margin-block: 1rem; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: left; padding: .5rem; border-bottom: 1px solid currentColor; vertical-align: top; }}
code {{ overflow-wrap: anywhere; }}
.status {{ font-weight: 700; }}
@media (max-width: 520px) {{
  table, tbody, tr, th, td {{ display: block; width: 100%; box-sizing: border-box; }}
  th {{ padding-bottom: .1rem; }}
  td {{ padding-top: .1rem; }}
}}
</style>
</head>
<body>
<header>
  <p>Project Pipeline · deterministic verification evidence</p>
  <h1>Pass 16 Verification Report</h1>
</header>
<main id="main-content">
<section aria-labelledby="truth-heading">
  <h2 id="truth-heading">Verification truth</h2>
  <p class="status">This report is evidence-producing only. The Completion Gate remains the sole authority for project completion.</p>
</section>
<section aria-labelledby="metrics-heading">
  <h2 id="metrics-heading">Repository snapshot</h2>
  <table><caption>Current governed verification metrics</caption><tbody>{metrics}</tbody></table>
</section>
<section aria-labelledby="scope-heading">
  <h2 id="scope-heading">Pass 16 evidence scope</h2>
  <ul>
    <li>Contract, API, integration and end-to-end verification</li>
    <li>Golden journeys and post-merge verification</li>
    <li>Browser, visual, accessibility and performance evidence</li>
    <li>Adversarial, property, mutation and fault probes</li>
  </ul>
</section>
</main>
<footer><p>Generated from repository state; no external network resources are required.</p></footer>
</body>
</html>
"""
    target.write_text(document, encoding="utf-8", newline="\n")
    return target


def _platform_chromium_candidates() -> tuple[str, ...]:
    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    local_app = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        str(Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        str(Path(program_files_x86) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        str(Path(program_files) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
        str(Path(program_files_x86) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
    ]
    if local_app:
        candidates.extend(
            (
                str(Path(local_app) / "Google" / "Chrome" / "Application" / "chrome.exe"),
                str(Path(local_app) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
            )
        )
    return tuple(candidates)


def find_chromium(candidates: tuple[str, ...] = ()) -> str | None:
    for candidate in (*candidates, *_platform_chromium_candidates()):
        if candidate and Path(candidate).is_file():
            return candidate
    for name in (
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "chrome",
        "msedge",
    ):
        path = shutil.which(name)
        if path:
            return path
    return None


def playwright_runtime_status() -> dict[str, Any]:
    """Report Playwright availability without inventing a live browser measurement."""

    package_present = importlib.util.find_spec("playwright") is not None
    chromium_path = find_chromium()
    if package_present and chromium_path:
        status = "MEASURED"
        reason = "playwright_package_and_chromium_present"
    elif package_present:
        status = "UNAVAILABLE_IN_EXECUTION_ENVIRONMENT"
        reason = "chromium_executable_missing"
    else:
        status = "UNAVAILABLE_IN_EXECUTION_ENVIRONMENT"
        reason = "playwright_package_missing"
    return {
        "runtime": "playwright",
        "package_present": package_present,
        "chromium_present": chromium_path is not None,
        "chromium_path": chromium_path,
        "status": status,
        "reason": reason,
    }


def _accessibility_violations(page: Any) -> tuple[list[str], int]:
    result = page.evaluate(
        """() => {
          const violations = [];
          let rules = 0;
          const check = (condition, message) => { rules += 1; if (!condition) violations.push(message); };
          check(document.documentElement.lang && document.documentElement.lang.trim().length > 0, "document-language");
          check(document.querySelectorAll('main').length === 1, "single-main-landmark");
          check(document.querySelectorAll('h1').length === 1, "single-h1");
          check([...document.querySelectorAll('img')].every(x => x.hasAttribute('alt')), "image-alt");
          check([...document.querySelectorAll('button')].every(x => (x.innerText || x.getAttribute('aria-label') || '').trim().length > 0), "button-name");
          check([...document.querySelectorAll('a')].every(x => (x.innerText || x.getAttribute('aria-label') || '').trim().length > 0), "link-name");
          check([...document.querySelectorAll('input,select,textarea')].every(x => {
            if (x.getAttribute('aria-label') || x.getAttribute('aria-labelledby')) return true;
            return x.id && document.querySelector(`label[for="${CSS.escape(x.id)}"]`);
          }), "form-labels");
          const ids = [...document.querySelectorAll('[id]')].map(x => x.id);
          check(new Set(ids).size === ids.length, "unique-ids");
          const levels = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(x => Number(x.tagName.substring(1)));
          let headingOk = true;
          for (let i = 1; i < levels.length; i++) if (levels[i] > levels[i-1] + 1) headingOk = false;
          check(headingOk, "heading-order");
          return {violations, rules};
        }"""
    )
    return list(result["violations"]), int(result["rules"])


class _QuietRepositoryHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return None


def verify_report(
    root: Path,
    report_path: Path,
    *,
    chromium_path: str,
    viewports: tuple[tuple[int, int], ...],
) -> tuple[tuple[BrowserEvidence, ...], AccessibilityEvidence]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment-dependent branch
        raise RuntimeError("Playwright Python package is unavailable") from exc

    root = root.resolve()
    report_path = report_path.resolve()
    if root not in report_path.parents:
        raise ValueError("browser target must remain repository-local")
    report_html = report_path.read_text(encoding="utf-8")
    screenshots = root / "evidence" / "verification" / "browser"
    screenshots.mkdir(parents=True, exist_ok=True)
    browser_results: list[BrowserEvidence] = []
    all_violations: set[str] = set()
    rule_count = 0

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
                started = time.perf_counter()
                # The execution sandbox blocks browser URL navigation, including file:// and localhost.
                # set_content still exercises the real Chromium DOM/layout/rendering engine using the
                # repository-local evidence document without external navigation or network access.
                page.set_content(report_html, wait_until="load", timeout=15000)
                load_ms = int((time.perf_counter() - started) * 1000)
                overflow = bool(
                    page.evaluate(
                        "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
                    )
                )
                violations, rules = _accessibility_violations(page)
                all_violations.update(violations)
                rule_count = max(rule_count, rules)
                screenshot = screenshots / f"verification_report_{width}x{height}.png"
                page.screenshot(path=str(screenshot), full_page=True)
                user_agent = page.evaluate("() => navigator.userAgent")
                version = "unknown"
                marker = "HeadlessChrome/"
                if marker in user_agent:
                    version = user_agent.split(marker, 1)[1].split(" ", 1)[0]
                passed = not overflow and not console_errors and not violations
                browser_results.append(
                    BrowserEvidence(
                        browser_evidence_id=verification_identifier(
                            "BROWSE", report_path.name, str(width), str(height), _sha256(screenshot)
                        ),
                        target=report_path.relative_to(root).as_posix(),
                        browser_name="Chromium",
                        browser_version=version,
                        viewport_width=width,
                        viewport_height=height,
                        screenshot_path=screenshot.relative_to(root).as_posix(),
                        screenshot_sha256=_sha256(screenshot),
                        horizontal_overflow=overflow,
                        console_error_count=len(console_errors),
                        load_duration_ms=load_ms,
                        passed=passed,
                    )
                )
                page.close()
        finally:
            browser.close()

    accessibility = AccessibilityEvidence(
        accessibility_id=verification_identifier(
            "A11Y", report_path.name, "semantic-baseline", *sorted(all_violations or {"PASS"})
        ),
        target=report_path.relative_to(root).as_posix(),
        method="Playwright DOM semantic baseline; axe-core adapter remains optional when the reviewed bundle is installed",
        rule_count=rule_count,
        violation_count=len(all_violations),
        violations=tuple(sorted(all_violations)),
        passed=not all_violations,
    )
    return tuple(browser_results), accessibility
