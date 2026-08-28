#!/usr/bin/env python3
"""
Machine Learning Using Python
Pass 4E-B — Release Infrastructure Audit

Diagnostic only: this script never modifies repository files.

Purpose
-------
Evaluate whether the repository is structurally ready to support a reproducible
Second Edition release workflow:

development -> final freeze -> v2.0.0 -> GitHub Release -> Zenodo DOI -> DOI propagation

Release-state meanings
----------------------
ERROR  = release-blocking infrastructure problem
REVIEW = human decision/check required before release
INFO   = expected or useful observation
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_REPO = "https://github.com/amightyo/machine-learning-using-python-2e"
EXPECTED_VERSION_DEV = "2.0.0-dev"
EXPECTED_VERSION_RELEASE = "2.0.0"

FILES = {
    "quarto": ROOT / "_quarto.yml",
    "gitignore": ROOT / ".gitignore",
    "license": ROOT / "LICENSE",
    "citation_cff": ROOT / "CITATION.cff",
    "readme": ROOT / "README.md",
    "references": ROOT / "references.bib",
    "citation_page": ROOT / "citation.qmd",
    "about": ROOT / "about.qmd",
    "tools_dir": ROOT / "tools",
    "github_dir": ROOT / ".github",
    "workflows_dir": ROOT / ".github" / "workflows",
    "book_dir": ROOT / "_book",
}

EXPECTED_AUDIT_TOOLS = [
    "audit_book_code.py",
    "audit_book_structure.py",
    "audit_book_continuity.py",
    "audit_book_accessibility.py",
    "audit_book_tables.py",
    "audit_book_editorial.py",
    "audit_book_release.py",
]

ENVIRONMENT_CANDIDATES = [
    "requirements.txt",
    "requirements-lock.txt",
    "environment.yml",
    "environment.yaml",
    "pyproject.toml",
    "uv.lock",
    "Pipfile",
    "Pipfile.lock",
    "renv.lock",
]

HELPER_TOOL_CANDIDATES = [
    "verify_environment.py",
    "snapshot_environment.py",
    "audit_book.ps1",
]

GENERATED_PATTERNS = [
    "_book/",
    ".quarto/",
    "__pycache__/",
    "*.pyc",
    ".ipynb_checkpoints/",
]

LOCAL_ONLY_PATTERNS = [
    ".venv/",
    "venv/",
    "env/",
    ".env",
    ".DS_Store",
    "Thumbs.db",
]


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


def norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


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


def run_git(*args: str) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", "git executable not found"


def git_tracked(path: Path) -> bool:
    code, out, _ = run_git("ls-files", "--error-unmatch", rel(path))
    return code == 0 and bool(out)


def get_git_remote() -> str | None:
    code, out, _ = run_git("remote", "get-url", "origin")
    return out.strip() if code == 0 and out.strip() else None


def check_git_repository(findings: list[Finding]) -> None:
    code, out, err = run_git("rev-parse", "--show-toplevel")
    if code != 0:
        findings.append(Finding("ERROR", "<git>", f"repository root could not be resolved: {err or out}."))
        return

    resolved = Path(out).resolve()
    if resolved != ROOT.resolve():
        findings.append(Finding(
            "REVIEW", "<git>",
            f"auditor root is '{ROOT}', but git root resolves to '{resolved}'."
        ))

    remote = get_git_remote()
    if not remote:
        findings.append(Finding("ERROR", "<git>", "origin remote is not configured."))
    else:
        normalized = remote.rstrip("/")
        normalized = re.sub(r"\.git$", "", normalized, flags=re.I)
        normalized = normalized.replace("git@github.com:", "https://github.com/")
        if normalized.lower() != EXPECTED_REPO.lower():
            findings.append(Finding(
                "REVIEW", "<git>",
                f"origin remote is '{remote}'; expected repository is '{EXPECTED_REPO}'."
            ))
        else:
            findings.append(Finding(
                "INFO", "<git>",
                f"origin remote matches expected repository: {EXPECTED_REPO}."
            ))

    code, branch, _ = run_git("branch", "--show-current")
    if code == 0 and branch:
        findings.append(Finding("INFO", "<git>", f"current branch is '{branch}'."))

    code, status, err = run_git("status", "--short")
    if code != 0:
        findings.append(Finding("ERROR", "<git>", f"git status failed: {err}."))
    elif status:
        lines = [line for line in status.splitlines() if line.strip()]
        findings.append(Finding(
            "INFO", "<git>",
            f"working tree has {len(lines)} uncommitted/untracked item(s); acceptable during 4E-B, "
            "but final release must be committed and clean."
        ))
    else:
        findings.append(Finding("INFO", "<git>", "working tree is clean."))

    code, tags, _ = run_git("tag", "--list", "v2.0.0")
    if code == 0 and tags.strip():
        findings.append(Finding(
            "REVIEW", "<git>",
            "tag 'v2.0.0' already exists. Verify before creating the final Second Edition release."
        ))
    else:
        findings.append(Finding(
            "INFO", "<git>",
            "tag 'v2.0.0' does not yet exist; expected during pre-release development."
        ))


def check_core_files(findings: list[Finding]) -> None:
    required = [
        "quarto",
        "gitignore",
        "license",
        "citation_cff",
        "readme",
        "references",
        "citation_page",
        "about",
        "tools_dir",
    ]

    for key in required:
        path = FILES[key]
        if not path.exists():
            findings.append(Finding("ERROR", rel(path), "required release-infrastructure item is missing."))

    if FILES["github_dir"].exists():
        findings.append(Finding("INFO", ".github", "GitHub configuration directory is present."))
    else:
        findings.append(Finding(
            "INFO", ".github",
            "GitHub configuration directory is absent; acceptable if publishing is managed manually or through repository settings."
        ))


def check_audit_toolchain(findings: list[Finding]) -> None:
    tools_dir = FILES["tools_dir"]
    if not tools_dir.exists():
        return

    missing = []
    for name in EXPECTED_AUDIT_TOOLS:
        path = tools_dir / name
        if not path.exists():
            missing.append(name)

    if missing:
        findings.append(Finding(
            "ERROR", "tools/",
            "expected audit tools are missing: " + ", ".join(missing) + "."
        ))
    else:
        findings.append(Finding(
            "INFO", "tools/",
            f"all {len(EXPECTED_AUDIT_TOOLS)} expected audit tools are present."
        ))

    present_helpers = [
        name for name in HELPER_TOOL_CANDIDATES
        if (tools_dir / name).exists()
    ]
    if present_helpers:
        findings.append(Finding(
            "INFO", "tools/",
            "additional reproducibility helpers detected: " + ", ".join(present_helpers) + "."
        ))


def check_environment_capture(findings: list[Finding]) -> None:
    present = [name for name in ENVIRONMENT_CANDIDATES if (ROOT / name).exists()]
    if present:
        findings.append(Finding(
            "INFO", "<environment>",
            "environment/dependency file(s) detected: " + ", ".join(present) + "."
        ))
    else:
        findings.append(Finding(
            "REVIEW", "<environment>",
            "no standard dependency/environment manifest detected at repository root. "
            "Verify that the Python environment is reproducibly documented elsewhere."
        ))


def parse_cff(findings: list[Finding]) -> dict[str, Any] | None:
    data, err = load_yaml(FILES["citation_cff"])
    if err:
        if FILES["citation_cff"].exists():
            findings.append(Finding("ERROR", "CITATION.cff", f"could not parse YAML: {err}."))
        return None
    return data


def parse_quarto(findings: list[Finding]) -> dict[str, Any] | None:
    data, err = load_yaml(FILES["quarto"])
    if err:
        if FILES["quarto"].exists():
            findings.append(Finding("ERROR", "_quarto.yml", f"could not parse YAML: {err}."))
        return None
    return data


def check_repo_metadata(
    quarto: dict[str, Any] | None,
    cff: dict[str, Any] | None,
    findings: list[Finding],
) -> None:
    if cff:
        repo_code = norm(cff.get("repository-code"))
        url = norm(cff.get("url"))
        if repo_code:
            if repo_code.rstrip("/").lower() != EXPECTED_REPO.lower():
                findings.append(Finding(
                    "REVIEW", "CITATION.cff",
                    f"repository-code is '{repo_code}', expected '{EXPECTED_REPO}'."
                ))
        else:
            findings.append(Finding("REVIEW", "CITATION.cff", "repository-code is missing."))

        if url and url.rstrip("/").lower() != EXPECTED_REPO.lower():
            findings.append(Finding(
                "INFO", "CITATION.cff",
                f"url is '{url}'. Verify whether this should remain the repository URL or become the published book-site URL."
            ))

        version = norm(cff.get("version"))
        if version == EXPECTED_VERSION_DEV:
            findings.append(Finding(
                "INFO", "CITATION.cff",
                f"version '{EXPECTED_VERSION_DEV}' is correct for the current pre-release state."
            ))
        elif version == EXPECTED_VERSION_RELEASE:
            findings.append(Finding(
                "REVIEW", "CITATION.cff",
                "version is already 2.0.0. Verify that final release freeze has actually occurred."
            ))

    if quarto:
        book = quarto.get("book") if isinstance(quarto.get("book"), dict) else {}
        repo_url = book.get("repo-url") or quarto.get("repo-url")
        site_url = book.get("site-url") or quarto.get("site-url")

        if repo_url:
            repo_url_n = norm(repo_url).rstrip("/")
            if repo_url_n.lower() != EXPECTED_REPO.lower():
                findings.append(Finding(
                    "REVIEW", "_quarto.yml",
                    f"repo-url is '{repo_url_n}', expected '{EXPECTED_REPO}'."
                ))
            else:
                findings.append(Finding(
                    "INFO", "_quarto.yml",
                    "repo-url matches the expected GitHub repository."
                ))
        else:
            findings.append(Finding(
                "INFO", "_quarto.yml",
                "no repo-url detected; optional, but useful for repository navigation."
            ))

        if site_url:
            findings.append(Finding(
                "INFO", "_quarto.yml",
                f"published site URL configured as '{norm(site_url)}'."
            ))
        else:
            findings.append(Finding(
                "REVIEW", "_quarto.yml",
                "no site-url detected. Confirm the canonical public book URL during 4E-B."
            ))


def check_gitignore(findings: list[Finding]) -> None:
    """
    Check whether generated/local artifacts are ignored, allowing equivalent
    Gitignore expressions rather than requiring exact literal strings.
    """
    path = FILES["gitignore"]
    if not path.exists():
        return

    text = read_text(path)
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    normalized = set(lines)

    def has_any(*patterns: str) -> bool:
        return any(p in normalized for p in patterns)

    # Quarto output/cache directories: accept anchored or unanchored forms.
    quarto_cache_ok = has_any(".quarto/", "/.quarto/")
    book_output_ok = has_any("_book/", "/_book/")

    # Python bytecode: accept exact pyc or broader standard glob patterns.
    bytecode_ok = (
        has_any("*.pyc", "*.py[cod]", "**/*.pyc", "**/*.py[cod]")
        or any(re.fullmatch(r"\*+/?\.?py\[cod\]", p, re.I) for p in normalized)
    )

    checks = [
        ("Quarto cache", quarto_cache_ok, "'.quarto/' or '/.quarto/'"),
        ("Quarto book output", book_output_ok, "'_book/' or '/_book/'"),
        ("Python bytecode", bytecode_ok, "'*.pyc' or broader equivalent such as '*.py[cod]'"),
    ]

    missing = [label for label, ok, _ in checks if not ok]
    if missing:
        detail = "; ".join(
            expected for label, ok, expected in checks if not ok
        )
        findings.append(Finding(
            "REVIEW", ".gitignore",
            "generated artifact ignore coverage is incomplete for "
            + ", ".join(missing)
            + f". Acceptable patterns include {detail}."
        ))
    else:
        findings.append(Finding(
            "INFO", ".gitignore",
            "generated Quarto output/cache and Python bytecode are covered by equivalent ignore patterns."
        ))

    ignored_local = [
        pattern for pattern in LOCAL_ONLY_PATTERNS
        if pattern in normalized
    ]
    if ignored_local:
        findings.append(Finding(
            "INFO", ".gitignore",
            f"{len(ignored_local)} common local-only pattern(s) explicitly ignored."
        ))

def check_generated_tracking(findings: list[Finding]) -> None:
    tracked_generated = []

    code, files, _ = run_git("ls-files")
    if code != 0:
        return

    tracked = files.splitlines()

    for f in tracked:
        p = f.replace("\\", "/")
        if (
            p.startswith("_book/")
            or p.startswith(".quarto/")
            or "/__pycache__/" in f"/{p}/"
            or p.endswith(".pyc")
            or ".ipynb_checkpoints/" in p
        ):
            tracked_generated.append(p)

    if tracked_generated:
        sample = ", ".join(tracked_generated[:8])
        suffix = "" if len(tracked_generated) <= 8 else f" (+{len(tracked_generated)-8} more)"
        findings.append(Finding(
            "REVIEW", "<git>",
            f"{len(tracked_generated)} generated/cache file(s) are tracked: {sample}{suffix}."
        ))
    else:
        findings.append(Finding(
            "INFO", "<git>",
            "no obvious Quarto/Python cache artifacts are tracked."
        ))


def check_workflows(findings: list[Finding]) -> None:
    """
    Inspect GitHub Actions without assuming Actions are required.
    Absence of workflows is one architectural REVIEW item, not duplicated with
    absence of the .github directory.
    """
    workflows_dir = FILES["workflows_dir"]

    if not workflows_dir.exists():
        findings.append(Finding(
            "REVIEW", "<publishing>",
            "no GitHub Actions workflow detected. Confirm whether GitHub Pages/build deployment "
            "is intentionally handled through repository settings or a manual publishing workflow."
        ))
        return

    workflow_files = sorted(
        list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))
    )

    if not workflow_files:
        findings.append(Finding(
            "REVIEW", "<publishing>",
            "the GitHub workflows directory exists but contains no workflow YAML files. "
            "Confirm the intended publishing mechanism."
        ))
        return

    findings.append(Finding(
        "INFO", ".github/workflows",
        f"{len(workflow_files)} workflow file(s) detected: "
        + ", ".join(rel(p) for p in workflow_files) + "."
    ))

    text_all = "\n".join(read_text(p).lower() for p in workflow_files)

    if "quarto" in text_all:
        findings.append(Finding(
            "INFO", ".github/workflows",
            "Quarto-related automation detected."
        ))
    else:
        findings.append(Finding(
            "REVIEW", "<publishing>",
            "workflow files exist but no obvious Quarto automation was detected; "
            "verify that the production build/deploy process is intentional."
        ))

    if "pages" in text_all or "github-pages" in text_all or "deploy-pages" in text_all:
        findings.append(Finding(
            "INFO", ".github/workflows",
            "GitHub Pages-related automation detected."
        ))
    else:
        findings.append(Finding(
            "INFO", ".github/workflows",
            "no obvious GitHub Pages deployment keyword detected; publishing may use another mechanism."
        ))

def check_release_artifact_state(findings: list[Finding]) -> None:
    book_dir = FILES["book_dir"]
    if not book_dir.exists():
        findings.append(Finding(
            "INFO", "_book/",
            "render output directory is not currently present; acceptable before the final production build."
        ))
        return

    html_files = list(book_dir.rglob("*.html"))
    pdf_files = list(book_dir.rglob("*.pdf"))

    if html_files:
        findings.append(Finding(
            "INFO", "_book/",
            f"{len(html_files)} HTML output file(s) currently present."
        ))
    else:
        findings.append(Finding(
            "REVIEW", "_book/",
            "render directory exists but no HTML output was detected."
        ))

    if pdf_files:
        findings.append(Finding(
            "INFO", "_book/",
            f"{len(pdf_files)} PDF output file(s) currently present."
        ))
    else:
        findings.append(Finding(
            "REVIEW", "_book/",
            "render directory exists but no PDF output was detected."
        ))


def check_license_consistency(cff: dict[str, Any] | None, findings: list[Finding]) -> None:
    if not FILES["license"].exists() or not cff:
        return

    cff_license = norm(cff.get("license"))
    license_text = read_text(FILES["license"]).lower()

    if cff_license.lower() == "cc-by-4.0":
        markers = [
            "creative commons attribution 4.0",
            "cc by 4.0",
            "creativecommons.org/licenses/by/4.0",
        ]
        if not any(m in license_text for m in markers):
            findings.append(Finding(
                "REVIEW", "LICENSE",
                "CITATION.cff declares CC-BY-4.0, but the LICENSE text does not clearly identify "
                "Creative Commons Attribution 4.0 by heuristic."
            ))
        else:
            findings.append(Finding(
                "INFO", "LICENSE",
                "license text appears consistent with CITATION.cff CC-BY-4.0 metadata."
            ))
    elif cff_license:
        findings.append(Finding(
            "INFO", "LICENSE",
            f"CITATION.cff declares license '{cff_license}'; verify repository LICENSE consistency manually."
        ))


def check_zenodo_readiness(findings: list[Finding]) -> None:
    zenodo_files = [
        ROOT / ".zenodo.json",
        ROOT / ".zenodo.yml",
        ROOT / ".zenodo.yaml",
    ]
    present = [p for p in zenodo_files if p.exists()]

    if present:
        findings.append(Finding(
            "INFO", "<zenodo>",
            "dedicated Zenodo metadata detected: " + ", ".join(rel(p) for p in present) + "."
        ))
    else:
        findings.append(Finding(
            "INFO", "<zenodo>",
            "no dedicated Zenodo metadata file detected. GitHub-Zenodo integration can still mint a DOI."
        ))

    findings.append(Finding(
        "REVIEW", "<zenodo>",
        "Zenodo repository integration status cannot be verified from local files alone; confirm it in Zenodo before tagging v2.0.0."
    ))


def print_rule(char: str = "-", width: int = 96) -> None:
    print(char * width)


def main() -> int:
    findings: list[Finding] = []

    check_core_files(findings)
    check_git_repository(findings)
    check_audit_toolchain(findings)
    check_environment_capture(findings)

    quarto = parse_quarto(findings)
    cff = parse_cff(findings)

    check_repo_metadata(quarto, cff, findings)
    check_gitignore(findings)
    check_generated_tracking(findings)
    check_workflows(findings)
    check_release_artifact_state(findings)
    check_license_consistency(cff, findings)
    check_zenodo_readiness(findings)

    errors = [f for f in findings if f.level == "ERROR"]
    reviews = [f for f in findings if f.level == "REVIEW"]
    infos = [f for f in findings if f.level == "INFO"]

    print("Machine Learning Using Python — Release Infrastructure Audit [4E-B v2]")
    print_rule("=", 96)
    print(f"Repository root:                     {ROOT}")
    print(f"Expected repository:                 {EXPECTED_REPO}")
    print(f"Development version:                 {EXPECTED_VERSION_DEV}")
    print(f"Final release version:               {EXPECTED_VERSION_RELEASE}")
    print()

    print("Expected Production Sequence")
    print_rule()
    print("development -> final freeze -> v2.0.0 -> GitHub Release -> Zenodo DOI -> DOI propagation")
    print()

    print("Infrastructure Review")
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
        "ERROR means release infrastructure is not ready. REVIEW identifies a human decision, "
        "external-service check, or configuration issue that should be resolved before tagging. "
        "INFO describes expected or useful repository state. A dirty working tree is informational "
        "during Pass 4E-B, but the final release must be committed, pushed, and clean."
    )
    print()

    print("Final Verdict")
    print_rule()
    if errors:
        print("RELEASE INFRASTRUCTURE AUDIT: FAILED")
        return 1
    if reviews:
        print("RELEASE INFRASTRUCTURE AUDIT: PASSED WITH REVIEW ITEMS")
        return 0
    print("RELEASE INFRASTRUCTURE AUDIT: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
