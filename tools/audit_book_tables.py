#!/usr/bin/env python3
"""Audit Markdown pipe tables for accessibility and portability in a Quarto book.

Machine Learning Using Python, Second Edition

Run from repository root:

    python tools/audit_book_tables.py

This refined version:
- detects actual Markdown pipe tables;
- ignores code fences;
- allows an intentionally blank top-left header cell for matrix-style tables
  when the remaining headers are populated and the body contains meaningful
  first-column row labels;
- treats missing formal captions/labels as informational rather than review
  items for compact pedagogical tables;
- continues to flag genuinely malformed headers, duplicate headers, wide
  tables, and long-cell portability concerns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUARTO = ROOT / "_quarto.yml"

DECLARED_QMD = re.compile(r"^\s*-\s+([A-Za-z0-9_./-]+\.qmd)\s*$", re.MULTILINE)
SEPARATOR_CELL = re.compile(r"^\s*:?-{3,}:?\s*$")


@dataclass
class TableFinding:
    file: str
    start_line: int
    rows: int
    columns: int
    has_caption_or_label: bool
    empty_headers: int
    allowed_blank_corner: bool
    duplicate_headers: list[str]
    max_cell_length: int
    long_cells: int


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def declared_pages() -> list[Path]:
    if not QUARTO.exists():
        return []
    rels = DECLARED_QMD.findall(read(QUARTO))
    return [ROOT / rel for rel in rels if (ROOT / rel).exists()]


def mask_code_fences(lines: list[str]) -> list[bool]:
    inside = False
    masked = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```"):
            masked.append(True)
            inside = not inside
            continue
        masked.append(inside)
    return masked


def split_pipe_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]

    parts = re.split(r"(?<!\\)\|", stripped)
    return [p.replace(r"\|", "|").strip() for p in parts]


def is_separator_row(line: str) -> bool:
    cells = split_pipe_row(line)
    return len(cells) >= 2 and all(SEPARATOR_CELL.fullmatch(c or "") for c in cells)


def looks_like_pipe_row(line: str) -> bool:
    return "|" in line and len(split_pipe_row(line)) >= 2


def nearby_caption_or_label(lines: list[str], start_idx: int, end_idx: int) -> bool:
    nearby = []
    for i in range(max(0, start_idx - 4), min(len(lines), end_idx + 5)):
        if start_idx <= i <= end_idx:
            continue
        nearby.append(lines[i])

    block = "\n".join(nearby)

    patterns = [
        r"\{#tbl-[A-Za-z0-9_.:-]+\}",
        r"^:\s+\S",
        r"^Table\s+\d+",
        r"^Table:",
        r"^Caption:",
    ]

    return any(re.search(p, block, re.MULTILINE | re.IGNORECASE) for p in patterns)


def is_allowed_blank_corner(header: list[str], body_rows: list[list[str]]) -> bool:
    """Allow one blank top-left cell in a matrix-style table.

    Conditions:
    - first header cell is blank;
    - all remaining header cells are populated;
    - at least one body row exists;
    - every body row has a non-empty first cell.

    This captures confusion matrices and similar row-vs-column tables.
    """
    if not header or header[0].strip():
        return False

    if len(header) < 2:
        return False

    if any(not h.strip() for h in header[1:]):
        return False

    if not body_rows:
        return False

    for row in body_rows:
        if not row or not row[0].strip():
            return False

    return True


def find_tables(path: Path) -> list[TableFinding]:
    lines = read(path).splitlines()
    masked = mask_code_fences(lines)

    findings = []
    i = 0

    while i < len(lines) - 1:
        if masked[i]:
            i += 1
            continue

        if (
            looks_like_pipe_row(lines[i])
            and not masked[i + 1]
            and is_separator_row(lines[i + 1])
        ):
            start = i
            header = split_pipe_row(lines[i])
            columns = len(header)

            j = i + 2
            body_rows = []

            while j < len(lines):
                if masked[j] or not looks_like_pipe_row(lines[j]) or not lines[j].strip():
                    break
                body_rows.append(split_pipe_row(lines[j]))
                j += 1

            all_rows = [header] + body_rows
            all_cells = [cell for row in all_rows for cell in row]

            norm_headers = [h.strip().lower() for h in header if h.strip()]
            duplicates = sorted({
                h for h in norm_headers if norm_headers.count(h) > 1
            })

            allowed_blank_corner = is_allowed_blank_corner(header, body_rows)

            raw_empty_headers = sum(1 for h in header if not h.strip())
            effective_empty_headers = (
                raw_empty_headers - 1
                if allowed_blank_corner and raw_empty_headers > 0
                else raw_empty_headers
            )

            max_cell_length = max((len(c) for c in all_cells), default=0)
            long_cells = sum(1 for c in all_cells if len(c) >= 80)

            rel = str(path.relative_to(ROOT)).replace("\\", "/")

            findings.append(
                TableFinding(
                    file=rel,
                    start_line=start + 1,
                    rows=1 + len(body_rows),
                    columns=columns,
                    has_caption_or_label=nearby_caption_or_label(
                        lines, start, max(start, j - 1)
                    ),
                    empty_headers=effective_empty_headers,
                    allowed_blank_corner=allowed_blank_corner,
                    duplicate_headers=duplicates,
                    max_cell_length=max_cell_length,
                    long_cells=long_cells,
                )
            )

            i = j
            continue

        i += 1

    return findings


def main() -> int:
    print("Machine Learning Using Python — Table Accessibility & Portability Audit")
    print("=" * 84)

    pages = declared_pages()

    if not pages:
        print("[ERROR] No declared QMD pages found.")
        return 1

    tables = []
    for page in pages:
        tables.extend(find_tables(page))

    print(f"Declared QMD pages scanned:          {len(pages)}")
    print(f"Actual Markdown pipe tables found:   {len(tables)}")
    print()

    if not tables:
        print("No Markdown pipe tables detected.")
        print("\nTABLE AUDIT: PASSED")
        return 0

    wide = [t for t in tables if t.columns >= 7]
    very_wide = [t for t in tables if t.columns >= 9]
    long_cell_tables = [t for t in tables if t.long_cells > 0]
    no_caption = [t for t in tables if not t.has_caption_or_label]
    empty_header_tables = [t for t in tables if t.empty_headers > 0]
    duplicate_header_tables = [t for t in tables if t.duplicate_headers]
    allowed_corner_tables = [t for t in tables if t.allowed_blank_corner]

    print("Table Inventory")
    print("-" * 84)

    for idx, t in enumerate(tables, start=1):
        flags = []

        if t.columns >= 9:
            flags.append("VERY-WIDE")
        elif t.columns >= 7:
            flags.append("WIDE")

        if t.long_cells:
            flags.append(f"LONG-CELLS={t.long_cells}")

        if t.empty_headers:
            flags.append(f"EMPTY-HEADERS={t.empty_headers}")

        if t.duplicate_headers:
            flags.append("DUPLICATE-HEADERS")

        if t.allowed_blank_corner:
            flags.append("MATRIX-CORNER-OK")

        if not t.has_caption_or_label:
            flags.append("INFORMAL-TABLE")

        flag_text = ", ".join(flags) if flags else "OK"

        print(
            f"[{idx:02}] {t.file}:{t.start_line}  "
            f"rows={t.rows:<3} cols={t.columns:<2} "
            f"max-cell={t.max_cell_length:<3}  {flag_text}"
        )

    print()
    print("Book-Level Summary")
    print("-" * 84)
    print(f"Tables with >= 7 columns:            {len(wide)}")
    print(f"Tables with >= 9 columns:            {len(very_wide)}")
    print(f"Tables containing long cells:        {len(long_cell_tables)}")
    print(f"Tables with empty headers:           {len(empty_header_tables)}")
    print(f"Tables with duplicate headers:       {len(duplicate_header_tables)}")
    print(f"Accepted blank matrix corner cells:  {len(allowed_corner_tables)}")
    print(f"Informal tables without caption:     {len(no_caption)}")

    errors = []
    reviews = []
    infos = []

    for t in empty_header_tables:
        errors.append(
            f"{t.file}:{t.start_line} has {t.empty_headers} unapproved empty header cell(s)."
        )

    for t in duplicate_header_tables:
        errors.append(
            f"{t.file}:{t.start_line} has duplicate header(s): "
            + ", ".join(t.duplicate_headers)
        )

    for t in very_wide:
        reviews.append(
            f"{t.file}:{t.start_line} has {t.columns} columns; inspect PDF/mobile readability."
        )

    for t in wide:
        if t not in very_wide:
            reviews.append(
                f"{t.file}:{t.start_line} has {t.columns} columns; inspect for horizontal compression."
            )

    for t in long_cell_tables:
        reviews.append(
            f"{t.file}:{t.start_line} contains {t.long_cells} cell(s) with 80+ characters; "
            "inspect wrapping/readability."
        )

    for t in allowed_corner_tables:
        infos.append(
            f"{t.file}:{t.start_line} uses an intentional blank top-left matrix header cell."
        )

    for t in no_caption:
        infos.append(
            f"{t.file}:{t.start_line} is treated as an informal pedagogical table "
            "without a formal caption/label."
        )

    print()
    print("Accessibility & Portability Review")
    print("-" * 84)
    print(f"Errors:                              {len(errors)}")
    print(f"Review items:                        {len(reviews)}")
    print(f"Informational items:                 {len(infos)}")

    if errors:
        print("\nErrors:")
        for item in errors:
            print(f"[ERROR] {item}")

    if reviews:
        print("\nReview items:")
        for item in reviews:
            print(f"[REVIEW] {item}")

    if infos:
        print("\nInformational items:")
        for item in infos:
            print(f"[INFO] {item}")

    print()
    print("Interpretation")
    print("-" * 84)
    print(
        "Compact pedagogical tables may remain informal without formal numbering. "
        "A blank top-left header cell is accepted for matrix-style tables when "
        "column headers and row labels are otherwise explicit. Errors are reserved "
        "for genuinely malformed headers or duplicate headers; review items focus "
        "on width and wrapping risks."
    )

    print()
    print("Final Verdict")
    print("-" * 84)

    if errors:
        print("TABLE AUDIT: FAILED")
        return 1

    if reviews:
        print("TABLE AUDIT: PASSED WITH REVIEW ITEMS")
        return 0

    print("TABLE AUDIT: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
