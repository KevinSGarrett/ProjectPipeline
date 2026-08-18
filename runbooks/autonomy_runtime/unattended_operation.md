# Unattended qualification runner

This runner records durable checkpoints for recovery, 24-hour, and 72-hour qualification. It does not simulate elapsed time and cannot mark a long-run complete before the attested wall-clock duration has actually passed.

## Required records

Every live run must record:

- process or service ID
- start time
- durable state path
- heartbeat
- lease and fence
- health, stop, and resume commands
- recovery procedure after host or process loss

## Commands

Foreground start:

```powershell
$env:PYTHONPATH = 'src'
& '.\.venv\Scripts\python.exe' scripts\run_autonomy_qualification.py start --database .local\state\qualification.sqlite3 --state-path .local\state\qualification --stage RECOVERY
```

Hidden Windows helper (explicit argument array, working directory, bounded logs, PID readback):

```powershell
$env:PYTHONPATH = 'src'
powershell -NoProfile -File scripts\start_autonomy_qualification_hidden.ps1 `
  -RepositoryRoot (Get-Location).Path `
  -PythonExe '.\.venv\Scripts\python.exe' `
  -Database '.local\pm_cycle_009\qualification\qualify.sqlite3' `
  -StatePath '.local\pm_cycle_009\qualification\state' `
  -LogDirectory '.local\pm_cycle_009\qualification\logs' `
  -Stage RECOVERY `
  -HeartbeatSeconds 30
```

Use `-DryRun` to print the exact hidden-process plan without starting it. Heartbeat, health, resume, stop, and fail use the printed `run_id`. The helper never shortens 24-hour or 72-hour attestation.

## Admission

1. Recovery must be startable and resumable.
2. A 24-hour run may start after recovery planning. It cannot be attested until 24 real hours have elapsed.
3. A 72-hour run cannot start until a 24-hour run is attested with real elapsed time.
4. Never write a fabricated elapsed-seconds value.

## Recovery

If the process exits without release, reconstruct `QualificationStore` from the same database, call `resume`, and continue heartbeats. Do not start a replacement 24-hour or 72-hour run to hide the interruption.
