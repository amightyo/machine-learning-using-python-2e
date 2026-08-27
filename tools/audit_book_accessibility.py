#!/usr/bin/env python3
"""Audit figures, tables, equations, and accessibility in a Quarto book."""

from __future__ import annotations
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUARTO = ROOT / "_quarto.yml"

DECLARED_QMD = re.compile(r"^\s*-\s+([A-Za-z0-9_./-]+\.qmd)\s*$", re.MULTILINE)
MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)(?:\{([^}]*)\})?")
FIG_LABEL = re.compile(r"#\|\s*label:\s*(fig-[A-Za-z0-9_.:-]+)")
FIG_CAP = re.compile(r"#\|\s*fig-cap:\s*(.+)")
FIG_ALT = re.compile(r"#\|\s*fig-alt:\s*(.+)")
EXPLICIT_LABEL = re.compile(
    r"(?:\{#|#\|\s*label:\s*)(fig-[A-Za-z0-9_.:-]+|tbl-[A-Za-z0-9_.:-]+|eq-[A-Za-z0-9_.:-]+)"
)
PIPE_TABLE_SEPARATOR = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", re.MULTILINE
)
TBL_LABEL = re.compile(r"#\|\s*label:\s*(tbl-[A-Za-z0-9_.:-]+)")
TBL_CAP = re.compile(r"#\|\s*tbl-cap:\s*(.+)")
DISPLAY_MATH = re.compile(r"\$\$(.*?)\$\$", re.DOTALL)
EQ_LABEL = re.compile(r"\{#(eq-[A-Za-z0-9_.:-]+)\}")
COLOR_ONLY = re.compile(
    r"\b(red line|blue line|green line|orange line|purple line|"
    r"red curve|blue curve|green curve|orange curve|purple curve|"
    r"red points|blue points|green points|orange points|purple points|"
    r"in red|in blue|in green|in orange|in purple|"
    r"shown in red|shown in blue|shown in green|shown in orange|shown in purple)\b",
    re.IGNORECASE,
)
WEAK_ALT = re.compile(
    r"^\s*(figure|plot|chart|graph|image|diagram|photo|picture|"
    r"scatterplot|scatter plot|bar chart|line chart|heatmap)\s*\.?\s*$",
    re.IGNORECASE,
)

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".svg"}
PDF_RISKY_IMAGE_EXTENSIONS = {".svg"}
EXTERNAL_PREFIXES = ("http://", "https://", "data:")


@dataclass
class Finding:
    severity: str
    location: str
    detail: str


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def declared_pages() -> list[Path]:
    if not QUARTO.exists():
        return []
    rels = DECLARED_QMD.findall(read(QUARTO))
    return [ROOT / rel for rel in rels if (ROOT / rel).exists()]


def strip_code(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def normalize_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if " " in target and not target.startswith(("http://", "https://")):
        target = target.split(" ", 1)[0]
    target = target.split("#", 1)[0].split("?", 1)[0]
    return target.strip()


def line_number(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def inspect_markdown_images(path, text, findings, inventory):
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    for match in MD_IMAGE.finditer(text):
        alt = match.group(1).strip()
        raw_target = match.group(2).strip()
        attrs = (match.group(3) or "").strip()
        target = normalize_target(raw_target)
        inventory["markdown_images"] += 1

        if not alt:
            findings.append(Finding("REVIEW", rel, f"Image has empty alt text at line {line_number(text, match.start())}: {raw_target}"))
        elif WEAK_ALT.fullmatch(alt):
            findings.append(Finding("REVIEW", rel, f"Weak/generic alt text at line {line_number(text, match.start())}: '{alt}'"))
        else:
            inventory["markdown_images_with_alt"] += 1

        attr_alt = re.search(r'fig-alt\s*=\s*"([^"]*)"', attrs)
        if attr_alt:
            inventory["markdown_images_with_fig_alt"] += 1
            if not attr_alt.group(1).strip():
                findings.append(Finding("REVIEW", rel, f"Empty fig-alt attribute at line {line_number(text, match.start())}."))

        if not target or target.startswith(EXTERNAL_PREFIXES):
            continue

        image_path = (path.parent / target).resolve()
        try:
            image_path.relative_to(ROOT.resolve())
        except ValueError:
            findings.append(Finding("REVIEW", rel, f"Image path points outside repository: {raw_target}"))
            continue

        if not image_path.exists():
            findings.append(Finding("ERROR", rel, f"Missing local image at line {line_number(text, match.start())}: {raw_target}"))
            continue

        suffix = image_path.suffix.lower()
        if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
            findings.append(Finding("ERROR", rel, f"Unsupported image type '{suffix}': {raw_target}"))
        if suffix in PDF_RISKY_IMAGE_EXTENSIONS:
            findings.append(Finding("REVIEW", rel, f"SVG asset may require conversion support for PDF output: {raw_target}"))


def inspect_executable_figures(path, text, findings, inventory):
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    for m in re.finditer(r"```(?:\{python\}|python)\s*\n(.*?)\n```", text, re.DOTALL):
        cell = m.group(1)
        for label in FIG_LABEL.findall(cell):
            inventory["executable_figures"] += 1
            if FIG_CAP.search(cell):
                inventory["executable_figures_with_caption"] += 1
            else:
                findings.append(Finding("REVIEW", rel, f"Executable figure {label} has no fig-cap near line {line_number(text, m.start())}."))
            alt_match = FIG_ALT.search(cell)
            if alt_match:
                inventory["executable_figures_with_alt"] += 1
                alt = alt_match.group(1).strip().strip('"').strip("'")
                if not alt:
                    findings.append(Finding("REVIEW", rel, f"Executable figure {label} has empty fig-alt."))
                elif WEAK_ALT.fullmatch(alt):
                    findings.append(Finding("REVIEW", rel, f"Executable figure {label} has weak/generic fig-alt: {alt}"))
            else:
                findings.append(Finding("REVIEW", rel, f"Executable figure {label} has no fig-alt."))


def inspect_tables(path, text, findings, inventory):
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    prose = strip_code(text)
    inventory["pipe_tables"] += len(PIPE_TABLE_SEPARATOR.findall(prose))

    for i, line in enumerate(prose.splitlines(), start=1):
        if PIPE_TABLE_SEPARATOR.fullmatch(line):
            cols = len([c for c in line.strip().strip("|").split("|")])
            if cols >= 7:
                findings.append(Finding("REVIEW", rel, f"Potentially wide pipe table at line {i}: {cols} columns."))

    for m in re.finditer(r"```(?:\{python\}|python)\s*\n(.*?)\n```", text, re.DOTALL):
        cell = m.group(1)
        for label in TBL_LABEL.findall(cell):
            inventory["labeled_tables"] += 1
            if TBL_CAP.search(cell):
                inventory["labeled_tables_with_caption"] += 1
            else:
                findings.append(Finding("REVIEW", rel, f"Table {label} has no tbl-cap near line {line_number(text, m.start())}."))


def inspect_equations(path, text, findings, inventory):
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    prose = strip_code(text)
    inventory["display_equations"] += len(DISPLAY_MATH.findall(prose))
    inventory["labeled_equations"] += len(EQ_LABEL.findall(prose))
    for m in DISPLAY_MATH.finditer(prose):
        body = re.sub(r"\s+", " ", m.group(1)).strip()
        if len(body) > 240:
            findings.append(Finding("REVIEW", rel, f"Long display equation near line {line_number(prose, m.start())} may need PDF/mobile review."))


def inspect_color_language(path, text, findings):
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    prose = strip_code(text)
    for m in COLOR_ONLY.finditer(prose):
        findings.append(Finding("REVIEW", rel, f"Possible color-dependent interpretation at line {line_number(prose, m.start())}: '{m.group(0)}'"))


def main() -> int:
    print("Machine Learning Using Python — Figures, Tables & Accessibility Audit")
    print("=" * 82)

    pages = declared_pages()
    if not pages:
        print("[ERROR] No declared QMD pages found.")
        return 1

    findings = []
    inventory = {
        "markdown_images": 0,
        "markdown_images_with_alt": 0,
        "markdown_images_with_fig_alt": 0,
        "executable_figures": 0,
        "executable_figures_with_caption": 0,
        "executable_figures_with_alt": 0,
        "pipe_tables": 0,
        "labeled_tables": 0,
        "labeled_tables_with_caption": 0,
        "display_equations": 0,
        "labeled_equations": 0,
    }
    all_labels = defaultdict(list)

    for path in pages:
        text = read(path)
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        inspect_markdown_images(path, text, findings, inventory)
        inspect_executable_figures(path, text, findings, inventory)
        inspect_tables(path, text, findings, inventory)
        inspect_equations(path, text, findings, inventory)
        inspect_color_language(path, text, findings)
        for label in EXPLICIT_LABEL.findall(text):
            all_labels[label].append(rel)

    for label, files in sorted(all_labels.items()):
        if len(files) > 1:
            findings.append(Finding("ERROR", "<book>", f"Duplicate label {label} defined in: {', '.join(files)}"))

    errors = [f for f in findings if f.severity == "ERROR"]
    reviews = [f for f in findings if f.severity == "REVIEW"]

    print(f"Declared QMD pages scanned:          {len(pages)}")
    print()
    print("Figures")
    print("-" * 82)
    print(f"Markdown images:                     {inventory['markdown_images']}")
    print(f"Markdown images with alt text:       {inventory['markdown_images_with_alt']}")
    print(f"Markdown images with fig-alt attr:   {inventory['markdown_images_with_fig_alt']}")
    print(f"Executable figures:                  {inventory['executable_figures']}")
    print(f"Executable figures with captions:    {inventory['executable_figures_with_caption']}")
    print(f"Executable figures with fig-alt:     {inventory['executable_figures_with_alt']}")

    print()
    print("Tables")
    print("-" * 82)
    print(f"Pipe tables detected:                {inventory['pipe_tables']}")
    print(f"Labeled executable tables:           {inventory['labeled_tables']}")
    print(f"Labeled tables with captions:        {inventory['labeled_tables_with_caption']}")

    print()
    print("Equations")
    print("-" * 82)
    print(f"Display equations detected:          {inventory['display_equations']}")
    print(f"Labeled equations:                   {inventory['labeled_equations']}")

    print()
    print("Accessibility & Portability Review")
    print("-" * 82)
    print(f"Errors:                              {len(errors)}")
    print(f"Review items:                        {len(reviews)}")

    if errors:
        print("\nErrors:")
        for f in errors:
            print(f"[ERROR] {f.location}: {f.detail}")

    if reviews:
        print("\nReview items:")
        for f in reviews[:120]:
            print(f"[REVIEW] {f.location}: {f.detail}")
        if len(reviews) > 120:
            print(f"... {len(reviews)-120} more review items")

    print()
    print("Interpretation")
    print("-" * 82)
    print(
        "Missing or weak alt text, color-only wording, SVG portability, wide tables, "
        "and long equations are review items rather than automatic failures because "
        "some require human judgment. Missing assets, unsupported image types, and "
        "duplicate labels are treated as errors."
    )

    print()
    print("Final Verdict")
    print("-" * 82)

    if errors:
        print("ACCESSIBILITY AUDIT: FAILED")
        return 1
    if reviews:
        print("ACCESSIBILITY AUDIT: PASSED WITH REVIEW ITEMS")
        return 0

    print("ACCESSIBILITY AUDIT: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
