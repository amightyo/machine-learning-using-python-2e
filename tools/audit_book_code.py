#!/usr/bin/env python3
"""Whole-book code, citation, and bibliography audit.

Machine Learning Using Python, Second Edition

Usage
-----
Static audit:
    python tools/audit_book_code.py

Static audit + warning-enabled Quarto render:
    python tools/audit_book_code.py --render

Optional stricter bibliography behavior:
    python tools/audit_book_code.py --fail-on-uncited

What this script checks
-----------------------
Code:
- discovers all 18 chapter .qmd files;
- finds executable Python fenced cells;
- compiles every Python cell for syntax;
- flags `n_jobs=-1`;
- flags weak `os.environ.setdefault("LOKY_MAX_CPU_COUNT", ...)`;
- reports `#| warning: false`;
- reports external URLs in executable Python cells;
- optionally runs a warning-enabled `quarto render`.

Citations and bibliography:
- loads `references.bib`;
- extracts all Pandoc-style citation keys from chapters;
- reports unresolved citation keys;
- reports malformed-looking citation syntax;
- reports duplicate BibTeX keys;
- reports possible duplicate titles;
- reports duplicate DOIs;
- reports uncited/orphaned bibliography entries;
- reports citation counts by chapter;
- reports chapters with no scholarly citations;
- reports bibliography entry totals.

Exit behavior
-------------
The audit FAILS for:
- Python syntax errors;
- unresolved citation keys;
- duplicate BibTeX keys;
- duplicate DOIs;
- known runtime-hygiene regressions;
- Quarto render failure;
- DeprecationWarning or FutureWarning during `--render`.

By default, uncited bibliography entries are REVIEW items rather than failures.
Use `--fail-on-uncited` if you want them to fail the audit.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIB_PATH = ROOT / "references.bib"

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
}

URL_PATTERN = re.compile(r"https?://[^\s\"')\]]+")

# Pandoc citations such as:
# [@smith2020]
# [@smith2020; @jones2021]
# Smith [-@smith2020]
# textual citations outside brackets are not intentionally supported here
# because the book currently uses bracketed Pandoc citations.
PANDOC_CITATION_BLOCK = re.compile(r"\[([^\]]*@[\w:.\-]+[^\]]*)\]")
CITATION_KEY = re.compile(r"(?<![\w])@([A-Za-z0-9_:\-\.]+)")

BIB_ENTRY_START = re.compile(
    r"@([A-Za-z]+)\s*\{\s*([^,\s]+)\s*,",
    re.MULTILINE,
)

FIELD_NAME = re.compile(
    r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*",
    re.MULTILINE,
)


@dataclass
class Finding:
    severity: str
    location: str
    detail: str


@dataclass
class BibEntry:
    entry_type: str
    key: str
    raw: str
    fields: dict[str, str]


def line_number(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def chapter_files() -> list[Path]:
    files: list[Path] = []
    for pattern in CHAPTER_GLOBS:
        files.extend(ROOT.glob(pattern))
    return sorted(files)


def python_cells(text: str) -> list[str]:
    return PYTHON_FENCE.findall(text)


def strip_code_fences(text: str) -> str:
    """Remove fenced code so @ operators/usernames do not look like citations."""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def extract_pandoc_citations(text: str) -> list[str]:
    """Return citation keys from bracketed Pandoc citation blocks."""
    prose = strip_code_fences(text)
    keys: list[str] = []
    for block in PANDOC_CITATION_BLOCK.findall(prose):
        keys.extend(CITATION_KEY.findall(block))
    return keys


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_title(value: str) -> str:
    value = value.replace("{", "").replace("}", "")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return normalize_space(value)


def normalize_doi(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("https://doi.org/", "")
    value = value.replace("http://doi.org/", "")
    value = value.replace("doi:", "")
    return value.strip()


def split_bibtex_entries(text: str) -> list[tuple[str, str, str]]:
    """Split a BibTeX file into entries using brace depth.

    Returns tuples of (entry_type, key, raw_entry).
    """
    entries: list[tuple[str, str, str]] = []
    pos = 0

    while True:
        match = BIB_ENTRY_START.search(text, pos)
        if not match:
            break

        entry_type = match.group(1)
        key = match.group(2)
        start = match.start()

        brace_start = text.find("{", match.start())
        if brace_start == -1:
            break

        depth = 0
        end = None
        in_quote = False
        escaped = False

        for i in range(brace_start, len(text)):
            ch = text[i]

            if escaped:
                escaped = False
                continue

            if ch == "\\":
                escaped = True
                continue

            if ch == '"':
                in_quote = not in_quote
                continue

            if in_quote:
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        if end is None:
            raw = text[start:]
            entries.append((entry_type, key, raw))
            break

        raw = text[start:end]
        entries.append((entry_type, key, raw))
        pos = end

    return entries


def parse_entry_fields(raw: str) -> dict[str, str]:
    """Parse BibTeX fields robustly, including compact one-line entries.

    Supports braced, quoted, and bare values. Nested braces are preserved.
    """
    fields: dict[str, str] = {}

    # Skip the entry header up to the first comma after the key.
    first_comma = raw.find(",")
    if first_comma == -1:
        return fields

    body = raw[first_comma + 1 :]
    pos = 0

    while pos < len(body):
        match = FIELD_NAME.search(body, pos)
        if not match:
            break

        field = match.group(1).lower()
        i = match.end()

        # Skip whitespace after '='.
        while i < len(body) and body[i].isspace():
            i += 1

        if i >= len(body):
            break

        if body[i] == "{":
            depth = 0
            start = i + 1
            i += 1

            while i < len(body):
                ch = body[i]

                if ch == "{":
                    depth += 1
                elif ch == "}":
                    if depth == 0:
                        value = body[start:i]
                        fields[field] = normalize_space(value)
                        i += 1
                        break
                    depth -= 1

                i += 1
            else:
                # Unterminated braced value.
                fields[field] = normalize_space(body[start:])
                break

        elif body[i] == '"':
            start = i + 1
            i += 1
            escaped = False

            while i < len(body):
                ch = body[i]

                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    fields[field] = normalize_space(body[start:i])
                    i += 1
                    break

                i += 1
            else:
                fields[field] = normalize_space(body[start:])
                break

        else:
            start = i
            while i < len(body) and body[i] not in ",\n}":
                i += 1
            fields[field] = normalize_space(body[start:i])

        pos = i

    return fields


def parse_bibtex(text: str) -> list[BibEntry]:
    entries: list[BibEntry] = []

    for entry_type, key, raw in split_bibtex_entries(text):
        entries.append(
            BibEntry(
                entry_type=entry_type,
                key=key,
                raw=raw,
                fields=parse_entry_fields(raw),
            )
        )

    return entries


def static_code_audit() -> tuple[list[Finding], int, int]:
    findings: list[Finding] = []
    total_cells = 0
    syntax_failures = 0

    files = chapter_files()
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

            urls = URL_PATTERN.findall(code)
            if urls:
                findings.append(
                    Finding(
                        "INFO",
                        rel,
                        f"Python cell {index} external URL(s): "
                        + ", ".join(sorted(set(urls))),
                    )
                )

        for name, pattern in FAIL_PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append(
                    Finding(
                        "ERROR",
                        rel,
                        f"{name} at line {line_number(text, match.start())}",
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


def citation_audit(
    *,
    fail_on_uncited: bool = False,
) -> tuple[
    list[Finding],
    dict[str, list[str]],
    list[BibEntry],
    set[str],
]:
    findings: list[Finding] = []
    citations_by_chapter: dict[str, list[str]] = {}

    if not BIB_PATH.exists():
        findings.append(
            Finding(
                "ERROR",
                "references.bib",
                "Bibliography file not found.",
            )
        )
        return findings, citations_by_chapter, [], set()

    bib_text = BIB_PATH.read_text(encoding="utf-8")
    entries = parse_bibtex(bib_text)

    if not entries:
        findings.append(
            Finding(
                "ERROR",
                "references.bib",
                "No BibTeX entries could be parsed.",
            )
        )
        return findings, citations_by_chapter, [], set()

    keys = [entry.key for entry in entries]
    key_counts = Counter(keys)
    duplicate_keys = sorted(k for k, count in key_counts.items() if count > 1)

    for key in duplicate_keys:
        findings.append(
            Finding(
                "ERROR",
                "references.bib",
                f"Duplicate BibTeX key: {key}",
            )
        )

    bibliography_keys = set(keys)
    all_cited_keys: list[str] = []

    for chapter in chapter_files():
        rel = str(chapter.relative_to(ROOT))
        text = chapter.read_text(encoding="utf-8")
        cited = extract_pandoc_citations(text)
        citations_by_chapter[rel] = cited
        all_cited_keys.extend(cited)

        if not cited:
            findings.append(
                Finding(
                    "REVIEW",
                    rel,
                    "No bracketed Pandoc scholarly citations detected.",
                )
            )

        unresolved = sorted(set(cited) - bibliography_keys)
        for key in unresolved:
            findings.append(
                Finding(
                    "ERROR",
                    rel,
                    f"Unresolved citation key: {key}",
                )
            )

        # Detect suspicious citation-like bracket blocks with a raw @
        # but no valid parsed key.
        prose = strip_code_fences(text)
        for match in re.finditer(r"\[[^\]]*@[^\]]*\]", prose):
            block = match.group(0)
            if not CITATION_KEY.search(block):
                findings.append(
                    Finding(
                        "REVIEW",
                        rel,
                        "Malformed-looking citation block at line "
                        f"{line_number(prose, match.start())}: {block}",
                    )
                )

    cited_set = set(all_cited_keys)
    uncited = sorted(bibliography_keys - cited_set)

    for key in uncited:
        findings.append(
            Finding(
                "ERROR" if fail_on_uncited else "REVIEW",
                "references.bib",
                f"Uncited bibliography entry: {key}",
            )
        )

    # Duplicate titles
    titles: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        title = entry.fields.get("title", "")
        if title:
            norm = normalize_title(title)
            if norm:
                titles[norm].append(entry.key)

    for norm_title, title_keys in sorted(titles.items()):
        if len(title_keys) > 1:
            findings.append(
                Finding(
                    "REVIEW",
                    "references.bib",
                    "Possible duplicate title: "
                    + ", ".join(title_keys)
                    + f" | normalized='{norm_title[:100]}'",
                )
            )

    # Duplicate DOIs
    dois: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        doi = entry.fields.get("doi", "")
        if doi:
            dois[normalize_doi(doi)].append(entry.key)

    for doi, doi_keys in sorted(dois.items()):
        if doi and len(doi_keys) > 1:
            findings.append(
                Finding(
                    "ERROR",
                    "references.bib",
                    f"Duplicate DOI {doi}: " + ", ".join(doi_keys),
                )
            )

    # Metadata review
    for entry in entries:
        if not entry.fields.get("title"):
            findings.append(
                Finding(
                    "REVIEW",
                    "references.bib",
                    f"{entry.key}: missing title field",
                )
            )

        if not entry.fields.get("author") and entry.entry_type.lower() not in {
            "misc",
            "online",
        }:
            findings.append(
                Finding(
                    "REVIEW",
                    "references.bib",
                    f"{entry.key}: missing author field",
                )
            )

        if not entry.fields.get("year"):
            findings.append(
                Finding(
                    "REVIEW",
                    "references.bib",
                    f"{entry.key}: missing year field",
                )
            )

    return findings, citations_by_chapter, entries, cited_set


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

    deprecations: list[str] = []
    other_warnings: list[str] = []

    for line in combined.splitlines():
        if "DeprecationWarning" in line or "FutureWarning" in line:
            deprecations.append(line.strip())
        elif "Warning" in line:
            other_warnings.append(line.strip())

    if process.returncode != 0:
        print(combined)

    return process.returncode, deprecations, other_warnings


def print_section(title: str) -> None:
    print()
    print(title)
    print("-" * 72)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--render",
        action="store_true",
        help="Also run a full warnings-enabled Quarto render.",
    )
    parser.add_argument(
        "--fail-on-uncited",
        action="store_true",
        help="Treat uncited bibliography entries as audit failures.",
    )
    parser.add_argument(
        "--show-all-uncited",
        action="store_true",
        help="Print every uncited bibliography entry instead of a sample.",
    )
    args = parser.parse_args()

    print("Machine Learning Using Python — Whole-Book Audit")
    print("=" * 72)

    chapters = chapter_files()

    code_findings, total_cells, syntax_failures = static_code_audit()
    (
        citation_findings,
        citations_by_chapter,
        bib_entries,
        cited_set,
    ) = citation_audit(
        fail_on_uncited=args.fail_on_uncited,
    )

    all_findings = code_findings + citation_findings

    errors = [f for f in all_findings if f.severity == "ERROR"]
    reviews = [f for f in all_findings if f.severity == "REVIEW"]
    infos = [f for f in all_findings if f.severity == "INFO"]

    print(f"Chapters found:                     {len(chapters)}")
    print(f"Executable Python cells found:      {total_cells}")
    print(f"Python syntax failures:             {syntax_failures}")
    print(f"Bibliography entries:               {len(bib_entries)}")
    print(f"Unique citation keys used:          {len(cited_set)}")

    print_section("Code Audit")
    if infos:
        for finding in infos:
            print(f"[INFO] {finding.location}: {finding.detail}")
    else:
        print("No informational code findings.")

    code_errors = [f for f in code_findings if f.severity == "ERROR"]
    if code_errors:
        print()
        for finding in code_errors:
            print(f"[ERROR] {finding.location}: {finding.detail}")
    else:
        print("Code integrity: PASS")

    print_section("Citation Coverage by Chapter")

    total_citations = 0
    for rel in sorted(citations_by_chapter):
        citations = citations_by_chapter[rel]
        unique = len(set(citations))
        total = len(citations)
        total_citations += total

        print(
            f"{rel:<62} "
            f"citations={total:>3}  unique={unique:>3}"
        )

    print()
    print(f"Total citation occurrences:         {total_citations}")

    unresolved = [
        f for f in citation_findings
        if f.severity == "ERROR" and "Unresolved citation key" in f.detail
    ]
    duplicate_key_findings = [
        f for f in citation_findings
        if f.severity == "ERROR" and "Duplicate BibTeX key" in f.detail
    ]
    duplicate_doi_findings = [
        f for f in citation_findings
        if f.severity == "ERROR" and "Duplicate DOI" in f.detail
    ]

    print_section("Citation Integrity")
    print(f"Unresolved citation keys:           {len(unresolved)}")
    print(f"Duplicate BibTeX keys:              {len(duplicate_key_findings)}")
    print(f"Duplicate DOIs:                     {len(duplicate_doi_findings)}")

    for finding in unresolved + duplicate_key_findings + duplicate_doi_findings:
        print(f"[ERROR] {finding.location}: {finding.detail}")

    uncited = [
        f for f in citation_findings
        if "Uncited bibliography entry:" in f.detail
    ]
    duplicate_titles = [
        f for f in citation_findings
        if "Possible duplicate title:" in f.detail
    ]
    no_citations = [
        f for f in citation_findings
        if "No bracketed Pandoc scholarly citations detected." in f.detail
    ]
    metadata_review = [
        f for f in citation_findings
        if (
            "missing title field" in f.detail
            or "missing author field" in f.detail
            or "missing year field" in f.detail
            or "Malformed-looking citation block" in f.detail
        )
    ]

    print_section("Bibliography Review")
    print(f"Uncited bibliography entries:       {len(uncited)}")
    print(f"Possible duplicate titles:          {len(duplicate_titles)}")
    print(f"Chapters with zero citations:       {len(no_citations)}")
    print(f"Metadata/syntax review items:       {len(metadata_review)}")

    if duplicate_titles:
        print("\nPossible duplicate titles:")
        for finding in duplicate_titles:
            print(f"[REVIEW] {finding.detail}")

    if no_citations:
        print("\nChapters with no scholarly citations:")
        for finding in no_citations:
            print(f"[REVIEW] {finding.location}")

    if metadata_review:
        print("\nMetadata/citation review:")
        for finding in metadata_review:
            print(f"[REVIEW] {finding.location}: {finding.detail}")

    if uncited:
        print("\nUncited entries:")
        display = uncited if args.show_all_uncited else uncited[:25]
        for finding in display:
            print(f"[REVIEW] {finding.detail}")

        if not args.show_all_uncited and len(uncited) > len(display):
            print(
                f"... {len(uncited) - len(display)} more. "
                "Use --show-all-uncited to display all."
            )

    failed = bool(errors)

    if args.render:
        rc, deprecations, other_warnings = render_audit()

        print_section("Warning-Enabled Render Audit")
        print(f"Quarto return code:                 {rc}")
        print(f"Deprecation/Future warnings:        {len(deprecations)}")
        print(f"Other warning lines:                {len(other_warnings)}")

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
                print(f"... {len(other_warnings) - 50} more")

        if rc != 0:
            failed = True

    print_section("Final Verdict")

    if failed:
        print("WHOLE-BOOK AUDIT: FAILED")
        return 1

    if reviews:
        print("WHOLE-BOOK AUDIT: PASSED WITH REVIEW ITEMS")
        print(
            "Review items are intentionally non-fatal unless "
            "--fail-on-uncited is used."
        )
        return 0

    print("WHOLE-BOOK AUDIT: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
