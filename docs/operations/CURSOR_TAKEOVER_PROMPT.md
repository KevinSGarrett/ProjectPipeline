# Cursor takeover prompt

The canonical prompt is generated from `project_pipeline.cursor_takeover.takeover_prompt` so the permanent product outcome cannot silently drift between documentation and execution.

Run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\cursor_takeover.py prompt --root .
```

Paste the complete output into a fresh Cursor Agent session at `C:\Project_X`. Cursor must return the read-only audit and proposed first cohesive slice before it writes.
