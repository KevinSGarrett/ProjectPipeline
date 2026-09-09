"""Least-privilege managed worker identity, separate from writable job IO."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Literal

from project_pipeline.autonomy_runtime.windows_service import quote_command

PROTECTED_CODE_ROOT = r"C:\ProgramData\ProjectPipeline\worker"
WRITABLE_JOB_ROOT = r"C:\ProgramData\ProjectPipeline\jobs"
HOST_PROTECTED_CODE_ROOTS = (PROTECTED_CODE_ROOT.lower(),)
SYSTEM_ACCOUNT = r"NT AUTHORITY\SYSTEM"
SYSTEM_IDENTITIES = frozenset({SYSTEM_ACCOUNT.upper(), "SYSTEM", "S-1-5-18"})
XEON_MACHINE_ID = "WIN-EVSH1DN8H5O"
WorkerIdentity = Literal["unprivileged_job_worker", "privileged_bootstrap"]
OWNED_TASK_NAMES = (
    "ProjectPipelineFleetWorkerComfy",
    "ProjectPipelineFleetWorkerXeon",
)
MANAGED_TASK_NAMES = (
    "ProjectPipelineManagedWorkerComfy",
    "ProjectPipelineManagedWorkerXeon",
)
INSPECTABLE_TASK_NAMES = OWNED_TASK_NAMES + MANAGED_TASK_NAMES
NEVER_RUN_RESULTS = frozenset({267011, "267011", "0x41303"})
_PRINCIPAL_FULL_CONTROL = re.compile(
    r"(?P<principal>(?:NT AUTHORITY|BUILTIN|NT SERVICE|[A-Za-z0-9._-]+)"
    r"\\[^\\\r\n:]+):\S*\(F\)",
    re.IGNORECASE,
)
_ADMIN_OR_SYSTEM = frozenset(
    {
        r"nt authority\system",
        "system",
        "s-1-5-18",
        r"builtin\administrators",
        "administrators",
        r"nt service\trustedinstaller",
        "trustedinstaller",
    }
)


def _normalized_windows_path(value: str) -> str:
    return value.replace("/", "\\").lower()


def _is_protected_code_path(script_path: str) -> bool:
    path_norm = _normalized_windows_path(script_path).rstrip("\\")
    for root in HOST_PROTECTED_CODE_ROOTS:
        root_norm = root.rstrip("\\")
        if path_norm == root_norm or path_norm.startswith(root_norm + "\\"):
            return True
    return False


def parse_icacls_fullcontrol_users(text: str) -> tuple[str, ...]:
    """Return non-admin principals that have Full Control in an icacls listing."""

    found: list[str] = []
    for match in _PRINCIPAL_FULL_CONTROL.finditer(text):
        principal = match.group("principal").strip()
        token = principal.lower()
        if not token or token in _ADMIN_OR_SYSTEM:
            continue
        if principal not in found:
            found.append(principal)
    return tuple(found)


def last_result_never_run(last_result: object, last_run_time: str | None = None) -> bool:
    if last_result in NEVER_RUN_RESULTS:
        return True
    try:
        never_run_code = int(str(last_result).strip(), 0) == 267011
    except (TypeError, ValueError):
        never_run_code = False
    if never_run_code:
        return True
    stamp = (last_run_time or "").strip().lower()
    return stamp.startswith("11/30/1999") or stamp in {"n/a", "never"}


def classify_live_managed_worker(
    *,
    runas: str,
    script_path: str,
    icacls_text: str,
    last_result: object,
    last_run_time: str | None = None,
) -> dict[str, Any]:
    """Classify a live task using XML identity plus ACL readback and run evidence."""

    users = parse_icacls_fullcontrol_users(icacls_text)
    parsed = bool(_PRINCIPAL_FULL_CONTROL.search(icacls_text))
    verdict = classify_scheduled_action(
        runas=runas,
        script_path=script_path,
        acl_fullcontrol_users=users,
        acl_evidence=parsed,
    )
    never_run = last_result_never_run(last_result, last_run_time)
    accepted = False if never_run else bool(verdict["accepted_production_worker"])
    reason = "managed_worker_never_run" if never_run else verdict["reason"]
    return {
        **verdict,
        "accepted_production_worker": accepted,
        "reason": reason,
        "acl_fullcontrol_users": users,
        "last_result": last_result,
        "last_run_time": last_run_time,
        "never_run": never_run,
    }


def classify_scheduled_action(
    *,
    runas: str,
    script_path: str,
    acl_fullcontrol_users: tuple[str, ...],
    acl_evidence: bool = False,
) -> dict[str, str | bool]:
    """SYSTEM or pp_jobs-generated code is never an accepted production job worker."""

    path_norm = _normalized_windows_path(script_path)
    writable = "pp_jobs" in path_norm
    system = runas.strip().upper() in SYSTEM_IDENTITIES
    user_write = bool(acl_fullcontrol_users)
    protected = _is_protected_code_path(script_path)
    accepted = (not system) and (not writable) and protected and (not user_write) and acl_evidence
    if system:
        reason = "system_not_job_worker"
    elif writable:
        reason = "user_writable_pp_jobs"
    elif not acl_evidence:
        reason = "acl_readback_required"
    elif user_write:
        reason = "acl_allows_user_write"
    elif not protected:
        reason = "code_not_in_protected_root"
    else:
        reason = "least_privilege_ok"
    return {
        "accepted_production_worker": accepted,
        "identity": "privileged_bootstrap" if system else "unprivileged_job_worker",
        "reason": reason,
        "protected_code_root": PROTECTED_CODE_ROOT,
        "writable_job_root": WRITABLE_JOB_ROOT,
    }


def owned_task_retirement_plan(
    task_name: str,
    *,
    python_executable: str | None = None,
) -> dict[str, Any]:
    """Disable only the two owned SYSTEM index tasks; register a least-privilege replacement."""

    if task_name not in OWNED_TASK_NAMES:
        return {"ok": False, "reason": "not_owned_task", "task_name": task_name}
    if not python_executable or Path(python_executable).suffix.lower() != ".exe":
        return {
            "ok": False,
            "reason": "python_executable_unresolved",
            "task_name": task_name,
        }
    replacement = task_name.replace("FleetWorker", "ManagedWorker")
    worker_script = rf"{PROTECTED_CODE_ROOT}\cycle20_remote_worker.py"
    return {
        "ok": True,
        "task_name": task_name,
        "export_argv": ("schtasks", "/Query", "/TN", task_name, "/XML"),
        "disable_argv": ("schtasks", "/Change", "/TN", task_name, "/DISABLE"),
        "replacement_name": replacement,
        "replacement_create_argv": (
            "schtasks",
            "/Create",
            "/TN",
            replacement,
            "/SC",
            "ONLOGON",
            "/TR",
            quote_command([python_executable, worker_script, "--managed"]),
            "/F",
        ),
        "rollback_argv": ("schtasks", "/Change", "/TN", task_name, "/ENABLE"),
        "unrelated_services_untouched": True,
        "do_not_reboot": True,
    }


def _xml_child_text(root: ElementTree.Element, ns: str, tag: str) -> str:
    element = root.find(f".//{ns}{tag}")
    return element.text if element is not None and element.text else ""


def inspect_scheduled_task_xml(xml_text: str) -> dict[str, Any]:
    """Hash and classify an exported scheduled-task XML without mutating the host."""

    digest = hashlib.sha256(xml_text.encode("utf-8")).hexdigest()
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return {
            "sha256": digest,
            "accepted_production_worker": False,
            "reason": "task_xml_invalid",
        }
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"
    command = _xml_child_text(root, ns, "Command")
    arguments = _xml_child_text(root, ns, "Arguments")
    runas = _xml_child_text(root, ns, "UserId")
    script_path = f"{command} {arguments}".strip()
    verdict = classify_scheduled_action(
        runas=runas or "SYSTEM",
        script_path=script_path,
        acl_fullcontrol_users=("Users",) if "pp_jobs" in script_path.lower() else (),
        acl_evidence=False,
    )
    return {
        "sha256": digest,
        "command": command,
        "arguments": arguments,
        "runas": runas,
        **verdict,
    }


def os_age_denies_xeon(os_support_status: str | None, machine_id: str) -> bool:
    """Operator grant: OS support-age never denies WIN-EVSH1DN8H5O."""

    del os_support_status
    del machine_id
    return False


def os_age_policy(machine_id: str, os_support_status: str | None) -> dict[str, Any]:
    """OS-age stays truthful and informational; it cannot restrict this Xeon."""

    xeon_grant = machine_id == XEON_MACHINE_ID
    return {
        "machine_id": machine_id,
        "os_support_status": os_support_status,
        "informational": True,
        "deny": False,
        "demote": False,
        "memory_ceiling_mb": None,
        "single_job_cap": False,
        "require_duplicate_verification": False,
        "strip_credentials": False,
        "operator_grant": xeon_grant,
    }


def owned_task_query_argv(task_name: str) -> tuple[str, ...]:
    if task_name not in INSPECTABLE_TASK_NAMES:
        raise ValueError("unowned_scheduled_task")
    return ("schtasks", "/Query", "/TN", task_name, "/XML")
