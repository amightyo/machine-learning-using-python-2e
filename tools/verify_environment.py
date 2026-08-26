#!/usr/bin/env python3
"""Verify the publication environment against environment/requirements-tested.txt."""

from __future__ import annotations

import importlib.metadata as metadata
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ = ROOT / "environment" / "requirements-tested.txt"


def command_version(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
        return (result.stdout or result.stderr).strip()
    except Exception:
        return "NOT FOUND"


def parse_requirements(path: Path) -> dict[str, str]:
    expected = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            continue
        name, ver = line.split("==", 1)
        expected[name.strip()] = ver.strip()
    return expected


def main() -> int:
    print("Machine Learning Using Python — Environment Verification")
    print("=" * 64)
    print("Python:", sys.version.split()[0])
    print("Platform:", platform.platform())
    print("Quarto:", command_version(["quarto", "--version"]))
    print("Git:", command_version(["git", "--version"]))
    print()

    if not REQ.exists():
        print(f"ERROR: missing {REQ.relative_to(ROOT)}")
        return 2

    expected = parse_requirements(REQ)
    failures = []

    print(f"{'Package':<22} {'Expected':<14} {'Installed':<14} Status")
    print("-" * 64)

    for package, expected_version in expected.items():
        try:
            installed = metadata.version(package)
        except metadata.PackageNotFoundError:
            installed = "NOT INSTALLED"

        ok = installed == expected_version
        print(
            f"{package:<22} {expected_version:<14} {installed:<14} "
            f"{'OK' if ok else 'MISMATCH'}"
        )
        if not ok:
            failures.append((package, expected_version, installed))

    print()
    if shutil.which("quarto") is None:
        failures.append(("quarto", "installed", "NOT FOUND"))
    if shutil.which("git") is None:
        failures.append(("git", "installed", "NOT FOUND"))

    if failures:
        print("Environment verification FAILED.")
        for name, expected_version, installed in failures:
            print(f" - {name}: expected {expected_version}; found {installed}")
        return 1

    print("Environment verification PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
