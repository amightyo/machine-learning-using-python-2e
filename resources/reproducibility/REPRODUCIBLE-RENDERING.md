# Reproducible Rendering Guide

## Goal

A release should be reproducible from a clean checkout rather than only from the author's existing machine.

## Clean-machine test

From a fresh clone:

```powershell
git clone https://github.com/amightyo/machine-learning-using-python-2e.git
cd machine-learning-using-python-2e

py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r environment/requirements-tested.txt
```

Confirm that Quarto is installed:

```powershell
quarto --version
```

Verify the Python environment:

```powershell
python tools/verify_environment.py
```

Run the code audit:

```powershell
python tools/audit_book_code.py
```

Run a warnings-enabled render:

```powershell
python tools/audit_book_code.py --render
```

Then capture the environment:

```powershell
python tools/snapshot_environment.py
```

## Release interpretation

A successful render establishes computational reproducibility only for the tested environment and available data.

It does not establish:
- scientific validity;
- external generalization;
- replication on new data;
- robustness to all analytical choices.

## Archive rule

For a DOI-bearing release, retain:
- Git tag;
- commit SHA;
- environment snapshot;
- dependency specification;
- rendered book;
- source manuscript;
- citation metadata;
- license information.
