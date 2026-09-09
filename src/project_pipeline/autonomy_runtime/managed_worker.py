"""Least-privilege managed worker identity, separate from writable job IO."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ElementTree
from typing import Any, Literal

PROTECTED_CODE_ROOT = r"C:\ProgramData\ProjectPipeline\worker"
WRITABLE_JOB_ROOT = r"C:\ProgramData\ProjectPipeline\jobs"
SYSTEM_ACCOUNT = r"NT AUTHORITY\SYSTEM"
SYSTEM_IDENTITIES = frozenset({SYSTEM_ACCOUNT.upper(), "SYSTEM", "S-1-5-18"})
XEON_MACHINE_ID = "WIN-EVSH1DN8H5O"
WorkerIdentity = Literal["unprivileged_job_worker", "privileged_bootstrap"]
OWNED_TASK_NAMES = (
    "ProjectPipelineFleetWorkerComfy",
    "ProjectPipelineFleetWorkerXeon",
)


def classify_scheduled_action(
    *,
    runas: str,
    script_path: str,
    acl_fullcontrol_users: tuple[str, ...],
) -> dict[str, str | bool]:
    """SYSTEM executing user-writable generated code is not a production worker."""

    writable = "pp_jobs" in script_path.replace("/", "\\").lower()
    system = runas.upper() in SYSTEM_IDENTITIES
    user_write = bool(acl_fullcontrol_users)
    accepted = not (system and (writable or user_write))
    return {
        "accepted_production_worker": accepted,
        "identity": "privileged_bootstrap" if system else "unprivileged_job_worker",
        "reason": "system_user_writable_code" if not accepted else "least_privilege_ok",
        "protected_code_root": PROTECTED_CODE_ROOT,
        "writable_job_root": WRITABLE_JOB_ROOT,
    }


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
    command = ""
    arguments = ""
    runas = ""
    command_el = root.find(f".//{ns}Command")
    args_el = root.find(f".//{ns}Arguments")
    user_el = root.find(f".//{ns}UserId")
    if command_el is not None and command_el.text:
        command = command_el.text
    if args_el is not None and args_el.text:
        arguments = args_el.text
    if user_el is not None and user_el.text:
        runas = user_el.text
    script_path = f"{command} {arguments}".strip()
    verdict = classify_scheduled_action(
        runas=runas or "SYSTEM",
        script_path=script_path,
        acl_fullcontrol_users=("Users",) if "pp_jobs" in script_path.lower() else (),
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
    return False if machine_id == XEON_MACHINE_ID else False


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
    if task_name not in OWNED_TASK_NAMES:
        raise ValueError("unowned_scheduled_task")
    return ("schtasks", "/Query", "/TN", task_name, "/XML")
