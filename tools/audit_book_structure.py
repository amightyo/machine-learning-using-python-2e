#!/usr/bin/env python3
"""Audit Quarto book navigation, cross-references, and structural integrity.

Run from repository root:

    python tools/audit_book_structure.py

Checks:
- chapter/resource files declared in _quarto.yml exist;
- .qmd files in the repository are either declared or intentionally excluded;
- duplicate explicit IDs/anchors within files;
- internal .qmd links point to existing files;
- local image/file links point to existing files;
- figure/table/equation references resolve to known labels;
- stale references to Chapters 19, 20, or 21;
- stale language suggesting the book has 20 or 21 chapters;
- duplicate top-level H1 titles across book pages;
- references.qmd remains unnumbered;
- resource pages remain unnumbered.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUARTO = ROOT / "_quarto.yml"

RESOURCE_FILES = {
    "teaching.qmd",
    "about.qmd",
    "citation.qmd",
    "references.qmd",
    "index.qmd",
    "intro.qmd",
}

IGNORED_DIRS = {
    ".git",
    ".quarto",
    "_book",
    "_site",
    ".venv",
    "venv",
    "__pycache__",
    "resources",
    "chapter-development",
}

LABEL_DEF = re.compile(
    r"(?:\{#|#\|\s*label:\s*)(fig-[A-Za-z0-9_.:-]+|tbl-[A-Za-z0-9_.:-]+|eq-[A-Za-z0-9_.:-]+)"
)
XREF = re.compile(r"@(fig-[A-Za-z0-9_.:-]+|tbl-[A-Za-z0-9_.:-]+|eq-[A-Za-z0-9_.:-]+)")
EXPLICIT_ID = re.compile(r"\{#([A-Za-z0-9_.:-]+)")
MD_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
H1 = re.compile(r"^#\s+(.+?)(?:\s+\{.*\})?\s*$", re.MULTILINE)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_declared_qmds(yaml_text: str) -> list[str]:
    # Lightweight extraction avoids adding a YAML dependency.
    return re.findall(r"^\s*-\s+([A-Za-z0-9_./-]+\.qmd)\s*$", yaml_text, re.MULTILINE)


def repository_qmds() -> list[Path]:
    out = []
    for p in ROOT.rglob("*.qmd"):
        rel = p.relative_to(ROOT)
        if any(part in IGNORED_DIRS for part in rel.parts[:-1]):
            continue
        out.append(p)
    return sorted(out)


def strip_code(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def normalize_link_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    target = target.split("#", 1)[0]
    target = target.split("?", 1)[0]
    return target.strip()


def is_external(target: str) -> bool:
    return target.startswith(
        ("http://", "https://", "mailto:", "tel:", "data:", "#")
    )


def main() -> int:
    print("Machine Learning Using Python — Structural Integrity Audit")
    print("=" * 76)

    errors: list[str] = []
    reviews: list[str] = []

    if not QUARTO.exists():
        print("[ERROR] Missing _quarto.yml")
        return 1

    yaml_text = read(QUARTO)
    declared = parse_declared_qmds(yaml_text)
    declared_set = set(declared)

    qmd_paths = repository_qmds()
    qmd_rel = {str(p.relative_to(ROOT)).replace("\\", "/") for p in qmd_paths}

    print(f"Declared book pages:                {len(declared)}")
    print(f"Repository .qmd files scanned:      {len(qmd_paths)}")

    # Declared files exist
    for rel in declared:
        if not (ROOT / rel).exists():
            errors.append(f"Declared file missing: {rel}")

    # Orphans
    orphans = sorted(qmd_rel - declared_set)
    if orphans:
        for rel in orphans:
            reviews.append(f"QMD not declared in _quarto.yml: {rel}")

    # Top-level titles
    title_to_files: dict[str, list[str]] = defaultdict(list)

    # Label definitions + use
    label_defs: dict[str, list[str]] = defaultdict(list)
    xref_uses: dict[str, list[str]] = defaultdict(list)

    for p in qmd_paths:
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        text = read(p)
        prose = strip_code(text)

        h1s = H1.findall(prose)
        if h1s:
            title = re.sub(r"\s+\{.*\}\s*$", "", h1s[0]).strip()
            title_to_files[title].append(rel)
        else:
            reviews.append(f"No H1 title detected: {rel}")

        # Resource numbering guard
        if p.name in {"teaching.qmd", "about.qmd", "citation.qmd", "references.qmd"}:
            first_h1 = h1s[0] if h1s else ""
            if "{.unnumbered}" not in prose.splitlines()[prose.splitlines().index(next(
                (line for line in prose.splitlines() if line.startswith("# ")), ""
            ))] if any(line.startswith("# ") for line in prose.splitlines()) else "":
                reviews.append(f"Resource page may not be unnumbered: {rel}")

            if re.search(r"(?m)^title\s*:", text):
                reviews.append(
                    f"Resource page contains YAML title; may cause duplicate/numbered page: {rel}"
                )

        # Explicit IDs
        ids = EXPLICIT_ID.findall(prose)
        dup_ids = [k for k, c in Counter(ids).items() if c > 1]
        for anchor in dup_ids:
            errors.append(f"Duplicate explicit anchor #{anchor} in {rel}")

        # Labels / xrefs
        for label in LABEL_DEF.findall(text):
            label_defs[label].append(rel)

        for label in XREF.findall(prose):
            xref_uses[label].append(rel)

        # Local markdown links
        for raw_target in MD_LINK.findall(prose):
            target = normalize_link_target(raw_target)
            if not target or is_external(target):
                continue

            # Ignore pure citation-like or generated outputs
            if target.startswith(("_book/", "_site/")):
                continue

            resolved = (p.parent / target).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                reviews.append(f"Link points outside repository in {rel}: {raw_target}")
                continue

            if not resolved.exists():
                errors.append(f"Broken local link in {rel}: {raw_target}")

        # Stale chapter numbering references
        for match in re.finditer(r"\bChapter(?:s)?\s+(19|20|21)\b", prose, re.IGNORECASE):
            reviews.append(
                f"Possible stale chapter reference in {rel}: {match.group(0)}"
            )

        for match in re.finditer(
            r"\b(?:20|21)\s+chapters\b|\bbook\s+has\s+(?:20|21)\s+chapters\b",
            prose,
            re.IGNORECASE,
        ):
            reviews.append(
                f"Possible stale book-length language in {rel}: {match.group(0)}"
            )

    # Duplicate top-level titles
    for title, files in sorted(title_to_files.items()):
        if len(files) > 1:
            reviews.append(
                f"Duplicate H1 title '{title}' in: {', '.join(files)}"
            )

    # Cross-reference validation
    for label, files in sorted(label_defs.items()):
        if len(files) > 1:
            errors.append(
                f"Duplicate cross-reference label @{label} defined in: {', '.join(files)}"
            )

    known = set(label_defs)
    used = set(xref_uses)

    for label in sorted(used - known):
        errors.append(
            f"Unresolved cross-reference @{label} used in: "
            + ", ".join(sorted(set(xref_uses[label])))
        )

    unused_labels = sorted(known - used)

    print()
    print("Cross-Reference Summary")
    print("-" * 76)
    print(f"Defined fig/tbl/eq labels:           {len(known)}")
    print(f"Referenced fig/tbl/eq labels:        {len(used)}")
    print(f"Unresolved cross-references:         {len(used - known)}")
    print(f"Defined but not cited in prose:      {len(unused_labels)}")

    print()
    print("Structural Review")
    print("-" * 76)
    print(f"Errors:                              {len(errors)}")
    print(f"Review items:                        {len(reviews)}")

    if errors:
        print("\nErrors:")
        for item in errors:
            print(f"[ERROR] {item}")

    if reviews:
        print("\nReview items:")
        for item in reviews[:80]:
            print(f"[REVIEW] {item}")
        if len(reviews) > 80:
            print(f"... {len(reviews) - 80} more review items")

    if unused_labels:
        print(
            "\n[INFO] Figure/table/equation labels that are not explicitly cited "
            "in prose are permitted and are not treated as review items."
        )

    print()
    print("Final Verdict")
    print("-" * 76)

    if errors:
        print("STRUCTURAL AUDIT: FAILED")
        return 1

    if reviews:
        print("STRUCTURAL AUDIT: PASSED WITH REVIEW ITEMS")
        return 0

    print("STRUCTURAL AUDIT: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
