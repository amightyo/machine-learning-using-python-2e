# Tested Python Environment

This directory records the computational environment used to audit the Second Edition.

## Recommended release workflow

Create a fresh virtual environment from the repository root.

### Windows PowerShell

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r environment/requirements-tested.txt
python -m ipykernel install --user --name ml-python-2e --display-name "ML Python 2e"
```

Verify the environment:

```powershell
python tools/verify_environment.py
```

Run the static audit:

```powershell
python tools/audit_book_code.py
```

Run the warning-enabled full render audit:

```powershell
python tools/audit_book_code.py --render
```

Capture the exact environment used for an archival release:

```powershell
python tools/snapshot_environment.py
```

The snapshot is written under `environment/snapshots/`.

## Why both a tested requirements file and a snapshot?

`requirements-tested.txt` describes the package versions used by the project.

The snapshot also records:
- Python version;
- operating system;
- Quarto version;
- Git version;
- Git commit;
- installed package versions.

For a DOI-bearing release, preserve the snapshot corresponding to the tagged release.
