#!/usr/bin/env python3
"""
Machine Learning Using Python
Pass 4E-A — Publication & Release Metadata Audit (CFF-aware revision)

Diagnostic only: this script never modifies repository files.

Release-state meanings
----------------------
ERROR  = release-blocking problem
REVIEW = human decision/check required before release
INFO   = expected or useful pre-release observation

Important publication-state rules
---------------------------------
- A DOI that has not yet been minted is NOT a pre-release error.
- A fixed publication date that has not yet been set is NOT a pre-release error.
- version "2.0.0-dev" is acceptable before the final release freeze.
- Quarto title + subtitle are treated as bibliographically equivalent to a
  combined CFF title of "Title: Subtitle".
- CFF 1.2.0 root-level "subtitle" is invalid.
- CFF 1.2.0 root-level "type: book" is invalid; root type, when supplied,
  is restricted to CFF-supported root resource types.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TITLE = "Machine Learning Using Python"
EXPECTED_SUBTITLE = "Foundations, Algorithms, Applications, and Reproducible Research"
EXPECTED_FULL_TITLE = f"{EXPECTED_TITLE}: {EXPECTED_SUBTITLE}"
EXPECTED_AUTHOR = "Itauma Itauma"
EXPECTED_EDITION = "Second Edition"
EXPECTED_DEV_VERSION = "2.0.0-dev"
EXPECTED_RELEASE_VERSION = "2.0.0"

FILES = {
    "quarto": ROOT / "_quarto.yml",
    "citation_cff": ROOT / "CITATION.cff",
    "citation_page": ROOT / "citation.qmd",
    "about": ROOT / "about.qmd",
    "readme": ROOT / "README.md",
    "license": ROOT / "LICENSE",
    "zenodo_json": ROOT / ".zenodo.json",
    "zenodo_yaml": ROOT / ".zenodo.yml",
    "zenodo_yml": ROOT / ".zenodo.yaml",
}

PLACEHOLDER_PATTERNS = [
    r"\bTODO\b",
    r"\bTBD\b",
    r"\bFIXME\b",
    r"\bINSERT\s+DOI\b",
    r"\bDOI\s+HERE\b",
    r"\bYOUR\s+DOI\b",
    r"\bPLACEHOLDER\b",
    r"10\.XXXX/",
    r"10\.0000/",
]

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)
URL_RE = re.compile(r"https?://[^\s<>)\]\"']+", re.I)


@dataclass
class Finding:
    level: str
    location: str
    message: str

    def render(self) -> str:
        return f"[{self.level}] {self.location}: {self.message}"


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def load_yaml(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "file does not exist"
    if yaml is None:
        return None, "PyYAML is not installed"
    try:
        data = yaml.safe_load(read_text(path))
    except Exception as exc:
        return None, str(exc)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None, "top-level YAML value is not a mapping"
    return data, None


def norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(norm(v) for v in value)
    if isinstance(value, dict):
        return " ".join(f"{k} {norm(v)}" for k, v in value.items())
    return re.sub(r"\s+", " ", str(value)).strip()


def norm_compare(value: Any) -> str:
    text = norm(value).lower()
    text = text.replace("&", "and")
    text = re.sub(r"[^\w]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get_nested(data: dict[str, Any] | None, *keys: str) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def first_present(data: dict[str, Any] | None, paths: list[tuple[str, ...]]) -> Any:
    for path in paths:
        value = get_nested(data, *path)
        if value not in (None, "", [], {}):
            return value
    return None


def author_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(author_strings(item))
        return out
    if isinstance(value, dict):
        name = value.get("name")
        if name:
            return [str(name)]
        given = value.get("given-names") or value.get("given") or value.get("first")
        family = value.get("family-names") or value.get("family") or value.get("last")
        combined = " ".join(x for x in [norm(given), norm(family)] if x)
        return [combined] if combined else []
    return [str(value)]


def find_dois(text: str) -> list[str]:
    return sorted(
        {doi.rstrip(".,;:") for doi in DOI_RE.findall(text)},
        key=str.lower
    )


def find_urls(text: str) -> list[str]:
    return sorted(set(u.rstrip(".,;:") for u in URL_RE.findall(text)))


def contains_expected(text: str, expected: str) -> bool:
    return norm_compare(expected) in norm_compare(text)


def cff_title_is_equivalent(cff_title: Any) -> bool:
    """Accept canonical full title, or title-only if no subtitle is expected in CFF."""
    n = norm_compare(cff_title)
    return n in {
        norm_compare(EXPECTED_FULL_TITLE),
        norm_compare(EXPECTED_TITLE),
    }


def check_required_files(findings: list[Finding]) -> None:
    required = ["quarto", "citation_page", "about", "readme"]
    for key in required:
        path = FILES[key]
        if not path.exists():
            findings.append(Finding("ERROR", rel(path), "required release file is missing."))

    if not FILES["license"].exists():
        alternatives = list(ROOT.glob("LICENSE.*")) + list(ROOT.glob("COPYING*"))
        if alternatives:
            findings.append(Finding(
                "INFO", rel(alternatives[0]),
                "license file found under an alternate filename."
            ))
        else:
            findings.append(Finding(
                "REVIEW", "LICENSE",
                "no repository license file detected; confirm the intended book/code license before release."
            ))

    if not FILES["citation_cff"].exists():
        findings.append(Finding(
            "REVIEW", "CITATION.cff",
            "CITATION.cff is not present; recommended for the scholarly release."
        ))


def check_yaml_parse(path: Path, label: str, findings: list[Finding]) -> dict[str, Any] | None:
    data, error = load_yaml(path)
    if error:
        if path.exists():
            level = "ERROR" if error != "PyYAML is not installed" else "REVIEW"
            findings.append(Finding(level, rel(path), f"{label} could not be parsed: {error}."))
        return None
    return data


def check_quarto(quarto: dict[str, Any] | None, findings: list[Finding]) -> None:
    if quarto is None:
        return

    book = quarto.get("book", {}) if isinstance(quarto.get("book"), dict) else {}

    title = first_present(quarto, [("book", "title"), ("title",)])
    subtitle = first_present(quarto, [("book", "subtitle"), ("subtitle",)])
    author = first_present(quarto, [("book", "author"), ("author",)])
    edition = first_present(quarto, [("book", "edition"), ("edition",)])
    date = first_present(quarto, [("book", "date"), ("date",)])

    if not title:
        findings.append(Finding("ERROR", "_quarto.yml", "book title is missing."))
    elif norm_compare(title) != norm_compare(EXPECTED_TITLE):
        findings.append(Finding(
            "REVIEW", "_quarto.yml",
            f"title is '{norm(title)}'; expected '{EXPECTED_TITLE}'."
        ))

    if not subtitle:
        findings.append(Finding("REVIEW", "_quarto.yml", "book subtitle is not declared."))
    elif norm_compare(subtitle) != norm_compare(EXPECTED_SUBTITLE):
        findings.append(Finding(
            "REVIEW", "_quarto.yml",
            f"subtitle differs from expected '{EXPECTED_SUBTITLE}'."
        ))

    authors = author_strings(author)
    if not authors:
        findings.append(Finding("ERROR", "_quarto.yml", "author metadata is missing."))
    elif not any(norm_compare(EXPECTED_AUTHOR) == norm_compare(a) for a in authors):
        findings.append(Finding(
            "REVIEW", "_quarto.yml",
            f"author metadata {authors!r} does not exactly match expected author '{EXPECTED_AUTHOR}'."
        ))

    if not edition:
        findings.append(Finding("REVIEW", "_quarto.yml", "edition metadata is missing."))
    elif norm_compare(edition) != norm_compare(EXPECTED_EDITION):
        findings.append(Finding(
            "REVIEW", "_quarto.yml",
            f"edition is '{norm(edition)}'; expected '{EXPECTED_EDITION}'."
        ))

    if not date:
        findings.append(Finding(
            "INFO", "_quarto.yml",
            "no fixed publication date is declared; acceptable before the release date is finalized."
        ))
    elif re.search(r"\btoday\b|\bnow\b", norm(date), re.I):
        findings.append(Finding(
            "REVIEW", "_quarto.yml",
            f"dynamic date value '{norm(date)}' detected; use a fixed archival release date."
        ))

    if not book.get("chapters"):
        findings.append(Finding("ERROR", "_quarto.yml", "book chapter navigation is missing."))


def check_cff(cff: dict[str, Any] | None, findings: list[Finding]) -> None:
    if cff is None:
        return

    required = ["cff-version", "message", "title", "authors"]
    for field in required:
        if cff.get(field) in (None, "", [], {}):
            findings.append(Finding(
                "ERROR", "CITATION.cff",
                f"required CFF field '{field}' is missing."
            ))

    cff_version = norm(cff.get("cff-version"))
    if cff_version and cff_version != "1.2.0":
        findings.append(Finding(
            "REVIEW", "CITATION.cff",
            f"cff-version is '{cff_version}'; this auditor is tuned for CFF 1.2.0."
        ))

    # CFF 1.2.0 root-level constraints relevant to this book.
    if "subtitle" in cff:
        findings.append(Finding(
            "ERROR", "CITATION.cff",
            "root-level 'subtitle' is not valid in CFF 1.2.0. "
            "Use the full bibliographic title in 'title'."
        ))

    if "type" in cff:
        cff_type = norm(cff.get("type")).lower()
        if cff_type not in {"software", "dataset"}:
            findings.append(Finding(
                "ERROR", "CITATION.cff",
                f"root-level type '{norm(cff.get('type'))}' is not valid for CFF 1.2.0. "
                "For this book, omit the root-level type field."
            ))
        else:
            findings.append(Finding(
                "REVIEW", "CITATION.cff",
                f"root-level type is '{cff_type}'. Verify that this is intentional for a book-centered release."
            ))

    title = cff.get("title")
    if title and not cff_title_is_equivalent(title):
        findings.append(Finding(
            "REVIEW", "CITATION.cff",
            f"title is '{norm(title)}'; expected bibliographic title is '{EXPECTED_FULL_TITLE}'."
        ))

    authors = author_strings(cff.get("authors"))
    if not authors:
        findings.append(Finding("ERROR", "CITATION.cff", "authors metadata is missing."))
    elif not any(norm_compare(EXPECTED_AUTHOR) == norm_compare(a) for a in authors):
        findings.append(Finding(
            "REVIEW", "CITATION.cff",
            f"authors metadata {authors!r} does not exactly match expected author '{EXPECTED_AUTHOR}'."
        ))

    version = norm(cff.get("version"))
    if not version:
        findings.append(Finding(
            "REVIEW", "CITATION.cff",
            "version is not set; use 2.0.0-dev during development and 2.0.0 at final release."
        ))
    elif version == EXPECTED_DEV_VERSION:
        findings.append(Finding(
            "INFO", "CITATION.cff",
            "version is 2.0.0-dev; correct for the pre-release development state."
        ))
    elif version == EXPECTED_RELEASE_VERSION:
        findings.append(Finding(
            "INFO", "CITATION.cff",
            "version is 2.0.0; verify that the repository is at the final release freeze."
        ))
    else:
        findings.append(Finding(
            "REVIEW", "CITATION.cff",
            f"version is '{version}'; expected pre-release '{EXPECTED_DEV_VERSION}' "
            f"or release '{EXPECTED_RELEASE_VERSION}'."
        ))

    if not cff.get("date-released"):
        findings.append(Finding(
            "INFO", "CITATION.cff",
            "date-released is not set; acceptable until the archival release date is finalized."
        ))

    if not cff.get("doi"):
        findings.append(Finding(
            "INFO", "CITATION.cff",
            "DOI is not set; expected before Zenodo mints the Second Edition DOI."
        ))

    if not cff.get("repository-code"):
        findings.append(Finding(
            "REVIEW", "CITATION.cff",
            "repository-code is not set."
        ))

    if not cff.get("license"):
        findings.append(Finding(
            "REVIEW", "CITATION.cff",
            "license is not set."
        ))


def check_text_identity(path: Path, label: str, findings: list[Finding]) -> None:
    if not path.exists():
        return
    text = read_text(path)

    if not contains_expected(text, EXPECTED_TITLE):
        findings.append(Finding(
            "REVIEW", rel(path),
            f"{label} does not visibly contain the canonical title '{EXPECTED_TITLE}'."
        ))

    if not contains_expected(text, EXPECTED_AUTHOR):
        findings.append(Finding(
            "REVIEW", rel(path),
            f"{label} does not visibly contain the canonical author name '{EXPECTED_AUTHOR}'."
        ))


def check_placeholders(findings: list[Finding]) -> None:
    release_files = [
        FILES["quarto"], FILES["citation_cff"], FILES["citation_page"],
        FILES["about"], FILES["readme"],
        FILES["zenodo_json"], FILES["zenodo_yaml"], FILES["zenodo_yml"],
    ]

    for path in release_files:
        if not path.exists():
            continue
        text = read_text(path)
        hits = [p for p in PLACEHOLDER_PATTERNS if re.search(p, text, re.I)]
        if hits:
            findings.append(Finding(
                "REVIEW", rel(path),
                f"possible release placeholder text detected ({len(hits)} pattern(s)); inspect before tagging."
            ))


def check_cross_file_identity(
    quarto: dict[str, Any] | None,
    cff: dict[str, Any] | None,
    findings: list[Finding]
) -> None:
    if quarto is None or cff is None:
        return

    q_title = first_present(quarto, [("book", "title"), ("title",)])
    q_subtitle = first_present(quarto, [("book", "subtitle"), ("subtitle",)])
    c_title = cff.get("title")

    if q_title and q_subtitle and c_title:
        combined = f"{norm(q_title)}: {norm(q_subtitle)}"
        if norm_compare(combined) != norm_compare(c_title):
            findings.append(Finding(
                "REVIEW", "<metadata>",
                "Quarto title + subtitle do not match the CFF bibliographic title: "
                f"_quarto.yml='{combined}'; CITATION.cff='{norm(c_title)}'."
            ))

    q_authors = author_strings(first_present(quarto, [("book", "author"), ("author",)]))
    c_authors = author_strings(cff.get("authors"))
    if q_authors and c_authors:
        q_set = tuple(sorted(norm_compare(a) for a in q_authors))
        c_set = tuple(sorted(norm_compare(a) for a in c_authors))
        if q_set != c_set:
            findings.append(Finding(
                "REVIEW", "<metadata>",
                f"author disagreement: _quarto.yml={q_authors!r}; CITATION.cff={c_authors!r}."
            ))

    q_license = first_present(quarto, [("book", "license"), ("license",)])
    c_license = cff.get("license")
    if q_license and c_license and norm_compare(q_license) != norm_compare(c_license):
        findings.append(Finding(
            "REVIEW", "<metadata>",
            f"license disagreement: _quarto.yml='{norm(q_license)}'; CITATION.cff='{norm(c_license)}'."
        ))

    q_doi = first_present(quarto, [("book", "doi"), ("doi",)])
    c_doi = cff.get("doi")
    if q_doi and c_doi and norm_compare(q_doi) != norm_compare(c_doi):
        findings.append(Finding(
            "REVIEW", "<metadata>",
            f"DOI disagreement: _quarto.yml='{norm(q_doi)}'; CITATION.cff='{norm(c_doi)}'."
        ))


def check_doi_state(findings: list[Finding]) -> None:
    paths = [
        FILES["quarto"], FILES["citation_cff"], FILES["citation_page"],
        FILES["readme"], FILES["zenodo_json"], FILES["zenodo_yaml"], FILES["zenodo_yml"],
    ]

    found: dict[str, list[str]] = {}
    for path in paths:
        if path.exists():
            dois = find_dois(read_text(path))
            if dois:
                found[rel(path)] = dois

    all_dois = sorted({d.lower() for values in found.values() for d in values})

    if not all_dois:
        findings.append(Finding(
            "INFO", "<release>",
            "no minted DOI detected in release metadata; expected before the Zenodo/GitHub release."
        ))
    elif len(all_dois) > 1:
        detail = "; ".join(f"{path}: {', '.join(values)}" for path, values in found.items())
        findings.append(Finding(
            "REVIEW", "<metadata>",
            f"multiple DOI values detected across release files: {detail}."
        ))
    else:
        findings.append(Finding(
            "INFO", "<release>",
            f"DOI detected: {all_dois[0]}. Verify it is the intended Second Edition DOI."
        ))


def check_repository_urls(cff: dict[str, Any] | None, findings: list[Finding]) -> None:
    candidates = [FILES["quarto"], FILES["citation_cff"], FILES["citation_page"], FILES["readme"]]
    urls: dict[str, list[str]] = {}

    for path in candidates:
        if path.exists():
            values = find_urls(read_text(path))
            if values:
                urls[rel(path)] = values

    github_urls = [
        u for values in urls.values() for u in values
        if "github.com/" in u.lower()
    ]
    if not github_urls:
        findings.append(Finding(
            "REVIEW", "<repository>",
            "no GitHub repository URL detected in the principal release metadata files."
        ))

    cff_repo = norm(cff.get("repository-code")) if cff else ""
    if cff_repo and "github.com/" not in cff_repo.lower():
        findings.append(Finding(
            "REVIEW", "CITATION.cff",
            f"repository-code does not appear to be a GitHub repository URL: '{cff_repo}'."
        ))

    # This is only heuristic. A site may be configured in YAML without appearing in prose.
    site_urls = [
        u for values in urls.values() for u in values
        if "github.io/" in u.lower() or "quarto.pub/" in u.lower()
    ]
    if not site_urls:
        findings.append(Finding(
            "INFO", "<repository>",
            "no obvious published book-site URL detected by heuristic; verify manually during 4E-B."
        ))


def check_zenodo_metadata(findings: list[Finding]) -> None:
    existing = [
        p for p in [FILES["zenodo_json"], FILES["zenodo_yaml"], FILES["zenodo_yml"]]
        if p.exists()
    ]

    if not existing:
        findings.append(Finding(
            "INFO", "<release>",
            "no dedicated Zenodo metadata file detected. This is not required for a GitHub-integrated Zenodo release."
        ))
    elif len(existing) > 1:
        findings.append(Finding(
            "REVIEW", "<release>",
            "multiple Zenodo metadata files detected: " + ", ".join(rel(p) for p in existing) + "."
        ))


def print_rule(char: str = "-", width: int = 92) -> None:
    print(char * width)


def main() -> int:
    findings: list[Finding] = []

    check_required_files(findings)

    quarto = check_yaml_parse(FILES["quarto"], "_quarto.yml", findings) if FILES["quarto"].exists() else None
    cff = check_yaml_parse(FILES["citation_cff"], "CITATION.cff", findings) if FILES["citation_cff"].exists() else None

    check_quarto(quarto, findings)
    check_cff(cff, findings)

    for path, label in [
        (FILES["citation_page"], "citation page"),
        (FILES["about"], "about page"),
        (FILES["readme"], "README"),
    ]:
        check_text_identity(path, label, findings)

    check_placeholders(findings)
    check_cross_file_identity(quarto, cff, findings)
    check_doi_state(findings)
    check_repository_urls(cff, findings)
    check_zenodo_metadata(findings)

    errors = [f for f in findings if f.level == "ERROR"]
    reviews = [f for f in findings if f.level == "REVIEW"]
    infos = [f for f in findings if f.level == "INFO"]

    print("Machine Learning Using Python — Publication & Release Metadata Audit [4E-A v2]")
    print_rule("=", 92)
    print(f"Repository root:                     {ROOT}")
    print(f"Expected title:                      {EXPECTED_TITLE}")
    print(f"Expected subtitle:                   {EXPECTED_SUBTITLE}")
    print(f"Expected CFF title:                  {EXPECTED_FULL_TITLE}")
    print(f"Expected author:                     {EXPECTED_AUTHOR}")
    print(f"Expected edition:                    {EXPECTED_EDITION}")
    print()

    print("Release File Inventory")
    print_rule()
    for key, path in FILES.items():
        print(f"{key:<22} {'FOUND' if path.exists() else 'MISSING':<8} {rel(path)}")
    print()

    print("Release Review")
    print_rule()
    print(f"Errors:                              {len(errors)}")
    print(f"Review items:                        {len(reviews)}")
    print(f"Informational items:                 {len(infos)}")
    print()

    if errors:
        print("Errors:")
        for f in errors:
            print(f.render())
        print()

    if reviews:
        print("Review items:")
        for f in reviews:
            print(f.render())
        print()

    if infos:
        print("Informational items:")
        for f in infos:
            print(f.render())
        print()

    print("Interpretation")
    print_rule()
    print(
        "ERROR means the repository is not ready to tag for release. REVIEW means a human "
        "decision or metadata reconciliation is needed before release. INFO records an expected "
        "or useful pre-release state. A missing DOI, an unset final release date, and version "
        "'2.0.0-dev' are intentionally non-blocking during development."
    )
    print()

    print("Final Verdict")
    print_rule()
    if errors:
        print("RELEASE METADATA AUDIT: FAILED")
        return 1
    if reviews:
        print("RELEASE METADATA AUDIT: PASSED WITH REVIEW ITEMS")
        return 0
    print("RELEASE METADATA AUDIT: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
