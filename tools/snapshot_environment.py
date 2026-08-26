#!/usr/bin/env python3
"""Capture the exact software and repository state used for a render/release."""

from __future__ import annotations

import importlib.metadata as metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "environment" / "snapshots"

PACKAGES = [
    "numpy",
    "pandas",
    "scipy",
    "matplotlib",
    "scikit-learn",
    "statsmodels",
    "joblib",
    "jupyterlab",
    "ipykernel",
]


def run(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return (result.stdout or result.stderr).strip()
    except Exception:
        return "UNKNOWN"


def package_versions() -> dict[str, str]:
    result = {}
    for package in PACKAGES:
        try:
            result[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            result[package] = "NOT INSTALLED"
    return result


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    commit = run(["git", "rev-parse", "HEAD"])

    payload = {
        "captured_at_utc": timestamp,
        "git_commit": commit,
        "git_status": run(["git", "status", "--porcelain"]),
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "quarto": run(["quarto", "--version"]),
        "git": run(["git", "--version"]),
        "packages": package_versions(),
    }

    json_path = OUT / f"environment-{timestamp}.json"
    txt_path = OUT / f"environment-{timestamp}.txt"

    json_path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    lines = [
        "Machine Learning Using Python — Environment Snapshot",
        "=" * 64,
        f"Captured UTC: {payload['captured_at_utc']}",
        f"Git commit: {payload['git_commit']}",
        f"Working tree changes: {payload['git_status'] or 'CLEAN'}",
        f"Python: {payload['python']}",
        f"Python executable: {payload['python_executable']}",
        f"Platform: {payload['platform']}",
        f"Quarto: {payload['quarto']}",
        f"Git: {payload['git']}",
        "",
        "Packages:",
    ]
    for name, ver in payload["packages"].items():
        lines.append(f"  {name}=={ver}")

    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json_path.relative_to(ROOT))
    print(txt_path.relative_to(ROOT))

    if payload["git_status"]:
        print("WARNING: working tree was not clean when snapshot was created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
