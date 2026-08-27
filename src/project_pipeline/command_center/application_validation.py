from __future__ import annotations

import json
from pathlib import Path

_REQUIRED_FILES = (
    "apps/command_center/package.json",
    "apps/command_center/package-lock.json",
    "apps/command_center/index.html",
    "apps/command_center/src/App.jsx",
    "apps/command_center/src/app.css",
    "apps/command_center/src/appModel.mjs",
    "apps/command_center/src/apiClient.mjs",
    "apps/command_center/src/desktopBridge.mjs",
    "apps/command_center/preview/index.html",
    "apps/desktop_shell/src-tauri/Cargo.toml",
    "apps/desktop_shell/src-tauri/Cargo.lock",
    "apps/desktop_shell/src-tauri/.cargo/config.toml",
    "apps/desktop_shell/src-tauri/src/main.rs",
    "apps/desktop_shell/src-tauri/tauri.conf.json",
    "apps/desktop_shell/src-tauri/capabilities/main.json",
    "apps/desktop_shell/src-tauri/icons/icon.ico",
    "apps/command_center/scripts/run-tauri.mjs",
    "config/desktop_nondeterminism_schema.json",
    "rust-toolchain.toml",
    ".github/workflows/desktop-windows.yml",
    "docs/command_center/application_and_desktop_shell.md",
    "runbooks/command_center_windows_qualification.md",
)


def validate_command_center_application(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    for relative in _REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(f"missing Command Center application artifact: {relative}")

    package_path = root / "apps/command_center/package.json"
    if package_path.is_file():
        package = json.loads(package_path.read_text(encoding="utf-8"))
        dependencies = package.get("dependencies", {})
        dev_dependencies = package.get("devDependencies", {})
        if "react" not in dependencies or "react-dom" not in dependencies:
            errors.append("Command Center application must declare React and react-dom")
        if "vite" not in dev_dependencies:
            errors.append("Command Center application must declare Vite")
        if "@tauri-apps/cli" not in dev_dependencies:
            errors.append("Command Center application must declare the Tauri v2 CLI boundary")
        scripts = package.get("scripts") or {}
        for name in ("tauri:dev", "tauri:build"):
            command = str(scripts.get(name, ""))
            if "run-tauri.mjs" not in command:
                errors.append(
                    f"Command Center {name} must invoke scripts/run-tauri.mjs from the desktop_shell cwd"
                )
        if "@tauri-apps/plugin-notification" not in dependencies:
            errors.append(
                "Command Center desktop boundary must declare the official notification plugin"
            )

    client_paths = (
        root / "apps/command_center/src/apiClient.mjs",
        root / "apps/command_center/src/desktopBridge.mjs",
        root / "apps/command_center/src/App.jsx",
    )
    for path in client_paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "localStorage" in text or "sessionStorage" in text or "indexedDB" in text:
            errors.append(
                f"credential-capable Command Center source must not persist auth state: {path.relative_to(root)}"
            )

    live_server = root / "src/project_pipeline/command_center/live_server.py"
    if live_server.is_file() and "CC_LIVE_TOKEN=" in live_server.read_text(encoding="utf-8"):
        errors.append("live Command Center preview must not inject bearer tokens into HTML")

    policy_path = root / "config/command_center_policy.json"
    if policy_path.is_file():
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        desktop_auth = policy.get("desktop_auth") or {}
        if desktop_auth.get("decision_id") != "ADR-0028":
            errors.append("Command Center desktop_auth must bind ADR-0028")
        if desktop_auth.get("default_bind") != "127.0.0.1":
            errors.append("Command Center desktop_auth must default to loopback")
        if desktop_auth.get("persist_secrets") is not False:
            errors.append("Command Center desktop_auth must forbid persisted secrets")
        if desktop_auth.get("allow_nonloopback") is not False:
            errors.append("Command Center desktop_auth must reject non-loopback binds by default")

    runner_path = root / "apps/command_center/scripts/run-tauri.mjs"
    if runner_path.is_file():
        runner = runner_path.read_text(encoding="utf-8")
        if "desktop_shell" not in runner or "cwd: desktopRoot" not in runner:
            errors.append(
                "Tauri runner must execute the CLI with cwd set to apps/desktop_shell so src-tauri/tauri.conf.json is discoverable"
            )
        if "TAURI_FRONTEND_PATH: frontendRoot" not in runner:
            errors.append("Tauri runner must set TAURI_FRONTEND_PATH to apps/command_center")
        if "TAURI_APP_PATH" not in runner:
            errors.append("Tauri runner must set TAURI_APP_PATH to apps/desktop_shell/src-tauri")

    tauri_path = root / "apps/desktop_shell/src-tauri/tauri.conf.json"
    if tauri_path.is_file():
        tauri = json.loads(tauri_path.read_text(encoding="utf-8"))
        build = tauri.get("build") or {}
        frontend = (root / "apps/command_center").resolve()
        if build.get("beforeDevCommand") != "npm run dev":
            errors.append("Tauri beforeDevCommand must run npm run dev in TAURI_FRONTEND_PATH")
        if build.get("beforeBuildCommand") != "npm run build":
            errors.append("Tauri beforeBuildCommand must run npm run build in TAURI_FRONTEND_PATH")
        frontend_dist = build.get("frontendDist")
        if not isinstance(frontend_dist, str) or (tauri_path.parent / frontend_dist).resolve() != (
            frontend / "dist"
        ):
            errors.append(
                "Tauri frontendDist must resolve from src-tauri to apps/command_center/dist"
            )
        security = tauri.get("app", {}).get("security", {})
        csp = str(security.get("csp", ""))
        loopback_fixed = "127.0.0.1:8765" in csp
        loopback_dynamic = "http://127.0.0.1:*" in csp and "ws://127.0.0.1:*" in csp
        if not (loopback_fixed or loopback_dynamic):
            errors.append(
                "Tauri CSP must restrict Command Center API transport to the loopback control endpoint"
            )
        wildcard_sanitized = (
            csp.replace("http://127.0.0.1:*", "").replace("ws://127.0.0.1:*", "")
        )
        if "https:" in wildcard_sanitized or "*" in wildcard_sanitized:
            errors.append("Tauri CSP must not grant arbitrary remote network origins")

    capability_path = root / "apps/desktop_shell/src-tauri/capabilities/main.json"
    if capability_path.is_file():
        capability = json.loads(capability_path.read_text(encoding="utf-8"))
        permissions = set(capability.get("permissions", []))
        if "notification:default" not in permissions:
            errors.append(
                "Tauri desktop shell must explicitly allow the bounded notification capability"
            )
        if any(
            str(value).startswith(("shell:", "fs:", "opener:", "http:")) for value in permissions
        ):
            errors.append("Tauri desktop shell grants an unnecessary high-risk capability")

    app_path = root / "apps/command_center/src/App.jsx"
    model_path = root / "apps/command_center/src/appModel.mjs"
    if app_path.is_file():
        app_text = app_path.read_text(encoding="utf-8")
        model_text = model_path.read_text(encoding="utf-8") if model_path.is_file() else ""
        surface_text = app_text + "\n" + model_text
        for surface in (
            "Project Graph",
            "Live Work",
            "Budget",
            "Provider",
            "Context",
            "Recovery",
            "Director Chat",
            "Incident Manager",
            "Approval",
            "Jira / GitHub",
            "Evidence",
        ):
            if surface not in surface_text:
                errors.append(
                    f"Command Center application is missing required surface text: {surface}"
                )
        if "makeControlCommand" not in app_text or ".control(" not in app_text:
            errors.append("Command Center mutation controls must use the typed control client path")
        if "makeDirectorRequest" not in app_text or ".directorChat(" not in app_text:
            errors.append("Director Chat must use the bounded API client path")
        if "verifyIncident" not in (root / "apps/command_center/src/apiClient.mjs").read_text(
            encoding="utf-8"
        ):
            errors.append("Incident Manager must expose repair verification through the API client")
        if "actionLinkQualification" not in (
            root / "apps/command_center/src/desktopBridge.mjs"
        ).read_text(encoding="utf-8"):
            errors.append(
                "desktop notification bridge must expose native action-link qualification"
            )

    preview_path = root / "apps/command_center/preview/index.html"
    if preview_path.is_file():
        preview = preview_path.read_text(encoding="utf-8")
        if "http://" in preview or "https://" in preview:
            errors.append(
                "offline Command Center verification preview must not depend on external network resources"
            )
        if preview.count("<main") != 1 or preview.count("<h1") != 1:
            errors.append(
                "offline Command Center verification preview must have one main landmark and one h1"
            )

    evidence_path = root / "evidence/command_center_ui_browser_accessibility.json"
    if evidence_path.is_file():
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if evidence.get("passed") is not True:
            errors.append(
                "recorded Command Center browser/accessibility verification is not passing"
            )

    return errors
