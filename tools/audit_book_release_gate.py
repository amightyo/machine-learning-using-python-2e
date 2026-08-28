#!/usr/bin/env python3
"""
Machine Learning Using Python
Pass 4E-C v4 — Master Release Quality Gate

Runs the established audit suite and normalizes legacy audit exit-code behavior.

Semantic gate policy
--------------------
ACCEPT:
  * explicit output line containing "AUDIT:" and "PASSED"
  * including "PASSED WITH REVIEW ITEMS"

HOLD:
  * explicit output line containing "AUDIT:" and "FAILED"
  * auditor cannot be executed
  * no recognizable semantic verdict AND subprocess exit code is nonzero

An explicit semantic audit verdict takes precedence over inconsistent legacy
subprocess exit codes. This script does not modify repository files.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
LOG_DIR = ROOT / "release-audit-logs"

AUDITS = [
    ("Code & Reproducibility", "audit_book_code.py"),
    ("Structure", "audit_book_structure.py"),
    ("Continuity", "audit_book_continuity.py"),
    ("Accessibility", "audit_book_accessibility.py"),
    ("Tables", "audit_book_tables.py"),
    ("Editorial", "audit_book_editorial.py"),
    ("Release Metadata", "audit_book_release.py"),
    ("Release Infrastructure", "audit_book_release_infrastructure.py"),
]


@dataclass
class AuditResult:
    name: str
    script: str
    returncode: int
    output: str
    verdict: str | None
    accepted: bool
    display_status: str
    reason: str


def extract_verdict(output: str) -> str | None:
    """
    Extract the final recognizable semantic audit verdict.

    Intentionally avoids a strict regular expression because the established
    auditors use different audit-name prefixes. Any line containing "AUDIT:"
    is eligible; classification is based on the verdict phrase.
    """
    candidates: list[str] = []

    for raw_line in output.splitlines():
        line = raw_line.strip()
        upper = line.upper()

        if "AUDIT:" not in upper:
            continue

        if "PASSED WITH REVIEW ITEMS" in upper:
            candidates.append(line)
        elif "PASSED" in upper:
            candidates.append(line)
        elif "FAILED" in upper:
            candidates.append(line)

    return candidates[-1] if candidates else None


def classify(returncode: int, output: str) -> tuple[str | None, bool, str, str]:
    """
    Normalize established auditors.

    Explicit semantic verdict takes precedence over inconsistent legacy exit
    codes. Exit code is authoritative only when no semantic verdict is found.
    """
    verdict = extract_verdict(output)

    if verdict:
        upper = verdict.upper()

        if "FAILED" in upper:
            return verdict, False, "HOLD", "explicit audit verdict is FAILED"

        if "PASSED WITH REVIEW ITEMS" in upper:
            return (
                verdict,
                True,
                "REVIEW",
                "audit passed with documented non-blocking review items",
            )

        if "PASSED" in upper:
            return verdict, True, "PASS", "audit passed"

    if returncode == 0:
        return (
            None,
            True,
            "PASS",
            "no explicit semantic verdict detected, but subprocess exit code is 0",
        )

    return (
        None,
        False,
        "HOLD",
        f"no recognizable semantic verdict and subprocess exit code is {returncode}",
    )


def run_audit(name: str, script_name: str) -> AuditResult:
    script = TOOLS / script_name

    if not script.exists():
        return AuditResult(
            name=name,
            script=script_name,
            returncode=127,
            output=f"ERROR: expected audit script is missing: {script}\n",
            verdict=None,
            accepted=False,
            display_status="HOLD",
            reason="expected audit script is missing",
        )

    # Force UTF-8 for child auditors. On Windows, redirected stdout can
    # otherwise fall back to cp1252; continuity output includes Unicode arrows
    # (→), which can raise UnicodeEncodeError before the semantic verdict prints.
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"

    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        env=child_env,
    )

    verdict, accepted, display_status, reason = classify(
        proc.returncode, proc.stdout
    )

    return AuditResult(
        name=name,
        script=script_name,
        returncode=proc.returncode,
        output=proc.stdout,
        verdict=verdict,
        accepted=accepted,
        display_status=display_status,
        reason=reason,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the complete Machine Learning Using Python "
            "pre-release quality audit suite."
        )
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print complete output from every underlying audit.",
    )
    args = parser.parse_args()

    print("Machine Learning Using Python — Master Release Quality Gate [4E-C v4]")
    print("=" * 100)
    print(f"Repository root: {ROOT}")
    print(f"Python:          {sys.executable}")
    print(f"Audits:          {len(AUDITS)}")
    print("Mode:            PRE-RELEASE")
    print(
        "Gate policy:     PASSED and PASSED WITH REVIEW ITEMS are accepted; "
        "FAILED is blocking."
    )
    print()

    results: list[AuditResult] = []

    for i, (name, script) in enumerate(AUDITS, start=1):
        print(f"[{i}/{len(AUDITS)}] {name} ... ", end="", flush=True)
        result = run_audit(name, script)
        results.append(result)
        print(result.display_status)

        if args.verbose:
            print("-" * 100)
            print(result.output.rstrip())
            print("-" * 100)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"release-quality-gate-{stamp}.txt"

    with log_path.open("w", encoding="utf-8") as fh:
        fh.write(
            "Machine Learning Using Python — "
            "Master Release Quality Gate [4E-C v4]\n"
        )
        fh.write("=" * 100 + "\n")
        fh.write(f"Repository root: {ROOT}\n")
        fh.write(f"Python: {sys.executable}\n")
        fh.write(f"Timestamp: {datetime.now().isoformat(timespec='seconds')}\n")
        fh.write("Mode: PRE-RELEASE\n")
        fh.write("Child encoding: UTF-8 forced for captured audit subprocesses.\n")
        fh.write(
            "Gate policy: explicit semantic audit verdict takes precedence "
            "over legacy exit-code differences.\n\n"
        )

        for result in results:
            fh.write("=" * 100 + "\n")
            fh.write(f"{result.name} — {result.script}\n")
            fh.write(f"Subprocess exit code: {result.returncode}\n")
            fh.write(
                f"Semantic verdict: {result.verdict or 'not detected'}\n"
            )
            fh.write(f"Gate status: {result.display_status}\n")
            fh.write(
                f"Accepted by gate: {'yes' if result.accepted else 'no'}\n"
            )
            fh.write(f"Reason: {result.reason}\n")
            fh.write("=" * 100 + "\n")
            fh.write(result.output.rstrip() + "\n\n")

    accepted = [r for r in results if r.accepted]
    blocking = [r for r in results if not r.accepted]
    clean_passes = [r for r in results if r.display_status == "PASS"]
    review_passes = [r for r in results if r.display_status == "REVIEW"]

    print()
    print("Consolidated Results")
    print("-" * 100)
    print(f"Accepted audits:        {len(accepted)}/{len(results)}")
    print(f"  Clean passes:         {len(clean_passes)}")
    print(f"  Passes with review:   {len(review_passes)}")
    print(f"Blocking audits:        {len(blocking)}/{len(results)}")
    print()

    for result in results:
        semantic = result.verdict or result.reason
        print(
            f"[{result.display_status:6}] "
            f"{result.name:<24} {semantic}"
        )

        if result.verdict and result.returncode != 0 and result.accepted:
            print(
                f"         note: legacy subprocess exit code "
                f"{result.returncode} was normalized by the explicit "
                "PASSED verdict."
            )

    print()
    print(f"Detailed log: {log_path.relative_to(ROOT).as_posix()}")
    print()
    print("Master Decision")
    print("-" * 100)

    if blocking:
        print(
            "HOLD — one or more established audits are blocking "
            "release progression."
        )
        print(
            "Resolve the blocking audit(s) before the final production "
            "render or v2.0.0 release freeze."
        )
        return 1

    print(
        "GO — all established audits are accepted by the "
        "pre-release quality gate."
    )

    if review_passes:
        print(
            f"{len(review_passes)} audit(s) passed with documented "
            "non-blocking review items; these remain visible for "
            "human inspection."
        )

    print(
        "Next stage: final clean production render and artifact "
        "inspection before v2.0.0 release freeze."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
