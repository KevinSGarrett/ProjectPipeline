# Autonomy Runtime Windows Service

## Identity

- Service name: `ProjectPipelineAutonomy`
- Foreground diagnostic mode does not require elevation.
- SCM install/start/stop/uninstall may require elevation and is optional for local qualification.

## Paths

All paths are explicit. Never place credential values in command lines, logs, or config files.

- Executable: the project virtualenv `python.exe`
- Script: `scripts/run_autonomy_runtime_service.py`
- State: `<root>/state/autonomy-supervisor.db`
- Log: `<root>/state/autonomy-service.log`
- Working directory: the disposable or project root passed to `--working-directory`
- PID: `<root>/state/autonomy-service.pid`

## Foreground diagnostic

```powershell
& 'C:\Project_X\.venv\Scripts\python.exe' scripts\run_autonomy_runtime_service.py --foreground --root <disposable-root> --max-seconds 5
& 'C:\Project_X\.venv\Scripts\python.exe' scripts\run_autonomy_runtime_service.py --status --root <disposable-root>
& 'C:\Project_X\.venv\Scripts\python.exe' scripts\run_autonomy_runtime_service.py --plan --root <disposable-root>
```

## SCM command generation

`--plan` prints quoted `sc.exe` install/start/status/stop/restart/uninstall commands. Review the plan before applying. Unknown `sc.exe` outcomes must be reconciled by querying service state before retry.

## Restart and rollback

1. Write a stop flag or send SIGINT/SIGTERM to the foreground process.
2. Confirm the PID file is removed and the checkpoint status is `STOPPED`.
3. Start again with the same state path; the checkpoint is the durable resume record.
4. If SCM installation was applied, `sc.exe delete` is the uninstall rollback after stop.

## Least privilege

Run the service as a non-admin local account with write access only to the configured state/log directory. Do not grant the service repository or credential-store write access beyond that directory.
