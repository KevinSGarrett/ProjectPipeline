# Local Setup

## Portable shell

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements/runtime.txt
python -m pip install -r requirements/development.txt
python -m pip install --no-deps -e .
python scripts/bootstrap_dev.py --root .
```

## Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements/runtime.txt
python -m pip install -r requirements/development.txt
python -m pip install --no-deps -e .
.\scripts\bootstrap_dev.ps1 -Root .
```

Quality tools require package-index access until the resolver-produced lock is activated. No setup command performs an external Project Pipeline integration write.
