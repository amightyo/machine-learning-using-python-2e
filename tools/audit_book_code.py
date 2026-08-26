#!/usr/bin/env python3
"""Static and warning-enabled audit for executable Quarto book code.

Default:
    python tools/audit_book_code.py

Full render audit:
    python tools/audit_book_code.py --render

The static audit:
- finds executable Python fenced cells in book chapter .qmd files;
- compiles each cell independently for syntax;
- flags known runtime-hygiene regressions;
- reports warning suppression and external-network references.

The render audit:
- runs `quarto render` with Python warnings enabled;
- treats DeprecationWarning and FutureWarning as failures;
- reports other warning lines for review.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHAPTER_GLOBS = [
    "part-01-foundations/*.qmd",
    "part-02-workflow/*.qmd",
    "part-03-supervised/*.qmd",
    "part-04-unsupervised/*.qmd",
    "part-05-modern-ml/*.qmd",
    "part-06-research/*.qmd",
]

PYTHON_FENCE = re.compile(
    r"```(?:\{python\}|python)\s*\n(.*?)\n```",
    re.DOTALL,
)

FAIL_PATTERNS = {
    "parallel-all-cores": re.compile(r"\bn_jobs\s*=\s*-1\b"),
    "weak-loky-setting": re.compile(
        r"os\.environ\.setdefault\(\s*[\"']LOKY_MAX_CPU_COUNT[\"']"
    ),
}

INFO_PATTERNS = {
    "warning-suppression": re.compile(r"#\|\s*warning\s*:\s*false"),
    "external-url": re.compile(r"https?://"),
}


@dataclass
class Finding:
    severity: str
    chapter: str
    detail: str


def chapters() -> list[Path]:
    files: list[Path] = []
    for pattern in CHAPTER_GLOBS:
        files.extend(ROOT.glob(pattern))
    return sorted(files)


def python_cells(text: str) -> list[str]:
    return PYTHON_FENCE.findall(text)


def static_audit() -> tuple[list[Finding], int, int]:
    findings: list[Finding] = []
    total_cells = 0
    syntax_failures = 0

    files = chapters()
    if not files:
        findings.append(
            Finding(
                "ERROR",
                "<repository>",
                "No chapter .qmd files found.",
            )
        )
        return findings, 0, 1

    for chapter in files:
        rel = str(chapter.relative_to(ROOT))
        text = chapter.read_text(encoding="utf-8")
        cells = python_cells(text)
        total_cells += len(cells)

        for index, code in enumerate(cells, start=1):
            # Quarto directives are Python comments and compile normally.
            try:
                compile(code, f"{rel}::cell-{index}", "exec")
            except SyntaxError as exc:
                syntax_failures += 1
                findings.append(
                    Finding(
                        "ERROR",
                        rel,
                        f"Python cell {index} syntax error: {exc}",
                    )
                )

        for name, pattern in FAIL_PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    Finding(
                        "ERROR",
                        rel,
                        f"{name} at line {line}",
                    )
                )

        for name, pattern in INFO_PATTERNS.items():
            count = len(pattern.findall(text))
            if count:
                findings.append(
                    Finding(
                        "INFO",
                        rel,
                        f"{name}: {count} occurrence(s)",
                    )
                )

    return findings, total_cells, syntax_failures


def render_audit() -> tuple[int, list[str], list[str]]:
    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "default"
    env["LOKY_MAX_CPU_COUNT"] = "1"

    print("\nRunning warnings-enabled Quarto render...")
    process = subprocess.run(
        ["quarto", "render"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    combined = "\n".join(
        part for part in [process.stdout, process.stderr] if part
    )

    deprecations = []
    other_warnings = []

    for line in combined.splitlines():
        if "DeprecationWarning" in line or "FutureWarning" in line:
            deprecations.append(line.strip())
        elif "Warning" in line:
            other_warnings.append(line.strip())

    if process.returncode != 0:
        print(combined)
        return process.returncode, deprecations, other_warnings

    return 0, deprecations, other_warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--render",
        action="store_true",
        help="Also run a full warnings-enabled Quarto render.",
    )
    args = parser.parse_args()

    print("Machine Learning Using Python — Book Code Audit")
    print("=" * 64)

    findings, total_cells, syntax_failures = static_audit()

    error_findings = [f for f in findings if f.severity == "ERROR"]
    info_findings = [f for f in findings if f.severity == "INFO"]

    print(f"Chapters found: {len(chapters())}")
    print(f"Executable Python cells found: {total_cells}")
    print(f"Syntax failures: {syntax_failures}")

    if info_findings:
        print("\nInformational findings:")
        for f in info_findings:
            print(f"  [{f.chapter}] {f.detail}")

    if error_findings:
        print("\nStatic audit failures:")
        for f in error_findings:
            print(f"  [{f.chapter}] {f.detail}")

    failed = bool(error_findings)

    if args.render:
        rc, deprecations, other_warnings = render_audit()

        print("\nRender audit:")
        print(f"  Quarto return code: {rc}")
        print(f"  Deprecation/Future warnings: {len(deprecations)}")
        print(f"  Other warning lines: {len(other_warnings)}")

        if deprecations:
            failed = True
            print("\nDeprecation/Future warnings:")
            for line in deprecations:
                print(" ", line)

        if other_warnings:
            print("\nOther warnings requiring human review:")
            for line in other_warnings[:50]:
                print(" ", line)
            if len(other_warnings) > 50:
                print(f"  ... {len(other_warnings) - 50} more")

        if rc != 0:
            failed = True

    print()
    if failed:
        print("BOOK CODE AUDIT: FAILED")
        return 1

    print("BOOK CODE AUDIT: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
