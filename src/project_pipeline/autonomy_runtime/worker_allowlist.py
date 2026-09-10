"""Allowlisted worker/job scripts and host Python identities.

Imported by the remote worker protocol and SSH dispatch. Does not import the
controller service/supervisor stack.
"""

from __future__ import annotations

from project_pipeline.autonomy_runtime.confinement import (
    COMFY_MACHINE_ID,
    XEON_MACHINE_ID,
    ConfinementError,
    reject_unsafe_string,
)

APPROVED_WORKER_HOSTS = frozenset({XEON_MACHINE_ID, COMFY_MACHINE_ID})
PYTHON_NAMES = frozenset({"python", "python.exe", "python3", "python3.exe"})
PROTECTED_WORKER_SCRIPT = r"C:\ProgramData\ProjectPipeline\worker\cycle20_remote_worker.py"
REMOTE_WORKER_SCRIPTS = {
    XEON_MACHINE_ID: PROTECTED_WORKER_SCRIPT,
    COMFY_MACHINE_ID: PROTECTED_WORKER_SCRIPT,
}
REMOTE_JOB_SCRIPTS = {
    XEON_MACHINE_ID: r"C:\Users\kines\ProjectPipeline\jobs\cycle21_validation_job.py",
    COMFY_MACHINE_ID: r"C:\Users\Windows 11\ProjectPipeline\jobs\cycle21_validation_job.py",
}
REMOTE_JOB_SCRIPT_ALIASES = (
    r"C:\Users\kines\ProjectPipeline\jobs\cycle20_useful_job.py",
    r"C:\Users\Windows 11\ProjectPipeline\jobs\cycle20_useful_job.py",
    r"C:\Users\kines\ProjectPipeline\jobs\cycle21_validation_job.py",
    r"C:\Users\Windows 11\ProjectPipeline\jobs\cycle21_validation_job.py",
)
REMOTE_HOLD_SCRIPTS = {
    XEON_MACHINE_ID: r"C:\Users\kines\ProjectPipeline\jobs\cycle20_hold_job.py",
    COMFY_MACHINE_ID: r"C:\Users\Windows 11\ProjectPipeline\jobs\cycle20_hold_job.py",
}
REMOTE_HOLD_SCRIPT_ALIASES = (
    r"C:\Users\kines\ProjectPipeline\jobs\cycle20_hold_job.py",
    r"C:\Users\Windows 11\ProjectPipeline\jobs\cycle20_hold_job.py",
    r"C:\Users\kines\ProjectPipeline\jobs\cycle21_hold_job.py",
    r"C:\Users\Windows 11\ProjectPipeline\jobs\cycle21_hold_job.py",
)
HOST_PYTHON_EXECUTABLES = {
    COMFY_MACHINE_ID: (r"C:\Users\Windows 11\AppData\Local\Programs\Python\Python311\python.exe"),
    XEON_MACHINE_ID: r"C:\Users\kines\AppData\Local\Programs\Python\Python311\python.exe",
}


def worker_launch_argv(machine_id: str) -> tuple[str, ...]:
    """Return the fixed remote worker executable and ProgramData script."""

    script = REMOTE_WORKER_SCRIPTS.get(machine_id)
    if not script:
        raise ValueError("worker_script_unresolved")
    python_exe = HOST_PYTHON_EXECUTABLES.get(machine_id)
    if python_exe:
        return (python_exe, script)
    return ("python", script)


def _argv_name(value: str) -> str:
    return value.replace("\\", "/").rsplit("/", 1)[-1].lower()


def remote_command_allowed(argv: tuple[str, ...]) -> bool:
    if not argv:
        return False
    name = _argv_name(argv[0])
    if name == "hostname":
        return len(argv) == 1
    if name not in PYTHON_NAMES:
        return False
    if len(argv) == 2 and argv[1] in {"-V", "--version"}:
        return True
    if (
        len(argv) >= 3
        and argv[1] == "-m"
        and argv[2] == "project_pipeline.autonomy_runtime.worker_entrypoint"
    ):
        return True
    if len(argv) >= 2 and not str(argv[1]).startswith("-"):
        posix = argv[1].replace("\\", "/")
        if "pp_jobs" in posix.split("/"):
            return False
        approved = (
            {item.replace("\\", "/").casefold() for item in REMOTE_WORKER_SCRIPTS.values()}
            | {item.replace("\\", "/").casefold() for item in REMOTE_HOLD_SCRIPTS.values()}
            | {item.replace("\\", "/").casefold() for item in REMOTE_HOLD_SCRIPT_ALIASES}
            | {item.replace("\\", "/").casefold() for item in REMOTE_JOB_SCRIPTS.values()}
            | {item.replace("\\", "/").casefold() for item in REMOTE_JOB_SCRIPT_ALIASES}
        )
        if posix.casefold() not in approved:
            return False
        if ".." in posix:
            return False
        for item in argv[2:]:
            if item == "--managed":
                continue
            try:
                reject_unsafe_string(item, field="argv")
            except ConfinementError:
                return False
        return True
    return False
