#!/usr/bin/env python3
"""Pass 4E-B v3 — release infrastructure audit (diagnostic only)."""
from __future__ import annotations
import re, subprocess, sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
try:
    import yaml
except ImportError:
    yaml=None

ROOT=Path(__file__).resolve().parents[1]
EXPECTED_REPO="https://github.com/amightyo/machine-learning-using-python-2e"
DEV_VERSION="2.0.0-dev"
FINAL_VERSION="2.0.0"

# Externally verified during Pass 4E-B.
PUBLISHING_METHOD="quarto publish gh-pages"
PUBLISHING_VERIFIED=True
ZENODO_GITHUB_INTEGRATION_VERIFIED=True

EXPECTED_TOOLS=[
"audit_book_code.py","audit_book_structure.py","audit_book_continuity.py",
"audit_book_accessibility.py","audit_book_tables.py","audit_book_editorial.py",
"audit_book_release.py",
]
HELPERS=["verify_environment.py","snapshot_environment.py","audit_book.ps1"]
ENV_FILES=["requirements.txt","requirements-lock.txt","environment.yml","environment.yaml",
           "pyproject.toml","uv.lock","Pipfile","Pipfile.lock","renv.lock"]

@dataclass
class Finding:
    level:str
    location:str
    message:str
    def render(self): return f"[{self.level}] {self.location}: {self.message}"

def read(path): return path.read_text(encoding="utf-8-sig")
def yload(path):
    if not path.exists() or yaml is None: return {}
    x=yaml.safe_load(read(path))
    return x if isinstance(x,dict) else {}
def git(*args):
    try:
        p=subprocess.run(["git",*args],cwd=ROOT,text=True,capture_output=True)
        return p.returncode,p.stdout.strip(),p.stderr.strip()
    except FileNotFoundError:
        return 127,"","git not found"

def main():
    f=[]
    required=["_quarto.yml",".gitignore","LICENSE","CITATION.cff","README.md",
              "references.bib","citation.qmd","about.qmd","tools"]
    for name in required:
        if not (ROOT/name).exists():
            f.append(Finding("ERROR",name,"required release-infrastructure item is missing."))

    # Git
    rc,out,err=git("rev-parse","--show-toplevel")
    if rc: f.append(Finding("ERROR","<git>",f"repository root unavailable: {err or out}."))
    rc,remote,_=git("remote","get-url","origin")
    if not rc and remote:
        n=re.sub(r"\.git$","",remote.rstrip("/")).replace("git@github.com:","https://github.com/")
        lvl="INFO" if n.lower()==EXPECTED_REPO.lower() else "REVIEW"
        msg=("origin remote matches expected repository: "+EXPECTED_REPO+"." if lvl=="INFO"
             else f"origin remote is '{remote}'; expected '{EXPECTED_REPO}'.")
        f.append(Finding(lvl,"<git>",msg))
    else: f.append(Finding("ERROR","<git>","origin remote is not configured."))

    rc,branch,_=git("branch","--show-current")
    if not rc and branch: f.append(Finding("INFO","<git>",f"current branch is '{branch}'."))

    rc,status,_=git("status","--short")
    if not rc:
        n=len([x for x in status.splitlines() if x.strip()])
        f.append(Finding("INFO","<git>",
            f"working tree has {n} uncommitted/untracked item(s); acceptable during 4E-B, but final release must be committed and clean."
            if n else "working tree is clean."))

    rc,tags,_=git("tag","--list","v2.0.0")
    f.append(Finding("REVIEW" if tags.strip() else "INFO","<git>",
        "tag 'v2.0.0' already exists; verify before final release."
        if tags.strip() else "tag 'v2.0.0' does not yet exist; expected during pre-release development."))

    # Tools/environment
    tools=ROOT/"tools"
    missing=[x for x in EXPECTED_TOOLS if not (tools/x).exists()]
    f.append(Finding("ERROR" if missing else "INFO","tools/",
        "expected audit tools are missing: "+", ".join(missing)+"."
        if missing else f"all {len(EXPECTED_TOOLS)} expected audit tools are present."))
    helpers=[x for x in HELPERS if (tools/x).exists()]
    if helpers: f.append(Finding("INFO","tools/","additional reproducibility helpers detected: "+", ".join(helpers)+"."))
    envs=[x for x in ENV_FILES if (ROOT/x).exists()]
    f.append(Finding("INFO" if envs else "REVIEW","<environment>",
        "environment/dependency file(s) detected: "+", ".join(envs)+"."
        if envs else "no standard dependency/environment manifest detected."))

    # Metadata
    q=yload(ROOT/"_quarto.yml"); c=yload(ROOT/"CITATION.cff")
    ver=str(c.get("version","")).strip()
    if ver==DEV_VERSION: f.append(Finding("INFO","CITATION.cff",f"version '{DEV_VERSION}' is correct for the current pre-release state."))
    elif ver==FINAL_VERSION: f.append(Finding("REVIEW","CITATION.cff","version is already 2.0.0; verify final release freeze has occurred."))

    book=q.get("book",{}) if isinstance(q.get("book"),dict) else {}
    repo=book.get("repo-url") or q.get("repo-url")
    site=book.get("site-url") or q.get("site-url")
    if repo and str(repo).rstrip("/").lower()==EXPECTED_REPO.lower():
        f.append(Finding("INFO","_quarto.yml","repo-url matches the expected GitHub repository."))
    else: f.append(Finding("REVIEW","_quarto.yml","repo-url is missing or does not match the expected repository."))
    if site: f.append(Finding("INFO","_quarto.yml",f"published site URL configured as '{site}'."))
    else: f.append(Finding("REVIEW","_quarto.yml","no site-url detected."))

    # gitignore semantic coverage
    gi=read(ROOT/".gitignore") if (ROOT/".gitignore").exists() else ""
    lines={x.strip() for x in gi.splitlines() if x.strip() and not x.lstrip().startswith("#")}
    ok_quarto=bool({".quarto/","/.quarto/"} & lines)
    ok_book=bool({"_book/","/_book/"} & lines)
    ok_pyc=bool({"*.pyc","*.py[cod]","**/*.pyc","**/*.py[cod]"} & lines)
    if ok_quarto and ok_book and ok_pyc:
        f.append(Finding("INFO",".gitignore","generated Quarto output/cache and Python bytecode are covered by equivalent ignore patterns."))
    else: f.append(Finding("REVIEW",".gitignore","generated artifact ignore coverage is incomplete."))

    # Tracked generated artifacts
    rc,tracked,_=git("ls-files")
    bad=[]
    if not rc:
        for x in tracked.splitlines():
            x=x.replace("\\","/")
            if x.startswith(("_book/",".quarto/")) or "/__pycache__/" in f"/{x}/" or x.endswith(".pyc") or ".ipynb_checkpoints/" in x:
                bad.append(x)
    f.append(Finding("REVIEW" if bad else "INFO","<git>",
        f"{len(bad)} generated/cache file(s) are tracked." if bad else "no obvious Quarto/Python cache artifacts are tracked."))

    # Publishing architecture
    wf=ROOT/".github"/"workflows"
    if PUBLISHING_VERIFIED and PUBLISHING_METHOD=="quarto publish gh-pages":
        f.append(Finding("INFO","<publishing>",
            "GitHub Pages publishing was externally verified using 'quarto publish gh-pages'; a repository-managed GitHub Actions workflow is not required for this architecture."))
    elif not wf.exists():
        f.append(Finding("REVIEW","<publishing>","publishing mechanism has not been verified."))

    # Render artifacts
    bd=ROOT/"_book"
    if bd.exists():
        html=len(list(bd.rglob("*.html"))); pdf=len(list(bd.rglob("*.pdf")))
        f.append(Finding("INFO" if html else "REVIEW","_book/",f"{html} HTML output file(s) currently present."))
        f.append(Finding("INFO" if pdf else "REVIEW","_book/",f"{pdf} PDF output file(s) currently present."))
    else: f.append(Finding("INFO","_book/","render output directory is not currently present; acceptable before final production build."))

    # License
    lic=read(ROOT/"LICENSE").lower() if (ROOT/"LICENSE").exists() else ""
    if str(c.get("license","")).lower()=="cc-by-4.0":
        ok=any(x in lic for x in ["creative commons attribution 4.0","cc by 4.0","creativecommons.org/licenses/by/4.0"])
        f.append(Finding("INFO" if ok else "REVIEW","LICENSE",
            "license text appears consistent with CITATION.cff CC-BY-4.0 metadata."
            if ok else "CITATION.cff declares CC-BY-4.0 but LICENSE could not be matched by heuristic."))

    # Zenodo
    zfiles=[x for x in [".zenodo.json",".zenodo.yml",".zenodo.yaml"] if (ROOT/x).exists()]
    f.append(Finding("INFO","<zenodo>",
        "dedicated Zenodo metadata detected: "+", ".join(zfiles)+"."
        if zfiles else "no dedicated Zenodo metadata file detected; CITATION.cff plus GitHub-Zenodo integration is sufficient for the planned workflow."))
    if ZENODO_GITHUB_INTEGRATION_VERIFIED:
        f.append(Finding("INFO","<zenodo>",
            "GitHub-Zenodo integration for 'amightyo/machine-learning-using-python-2e' was externally verified as enabled during Pass 4E-B; do not create the final GitHub Release until the v2.0.0 release freeze."))
    else: f.append(Finding("REVIEW","<zenodo>","Zenodo integration has not been externally verified."))

    errors=[x for x in f if x.level=="ERROR"]; reviews=[x for x in f if x.level=="REVIEW"]; infos=[x for x in f if x.level=="INFO"]
    print("Machine Learning Using Python — Release Infrastructure Audit [4E-B v3]")
    print("="*96)
    print(f"Repository root:                     {ROOT}")
    print(f"Expected repository:                 {EXPECTED_REPO}")
    print(f"Development version:                 {DEV_VERSION}")
    print(f"Final release version:               {FINAL_VERSION}")
    print(f"Verified publishing method:          {PUBLISHING_METHOD}")
    print(f"Zenodo integration verified:         {'yes' if ZENODO_GITHUB_INTEGRATION_VERIFIED else 'no'}")
    print("\nExpected Production Sequence\n"+"-"*96)
    print("development -> final freeze -> v2.0.0 -> GitHub Release -> Zenodo DOI -> DOI propagation")
    print("\nInfrastructure Review\n"+"-"*96)
    print(f"Errors:                              {len(errors)}")
    print(f"Review items:                        {len(reviews)}")
    print(f"Informational items:                 {len(infos)}")
    for label,items in [("Errors",errors),("Review items",reviews),("Informational items",infos)]:
        if items:
            print(f"\n{label}:")
            for x in items: print(x.render())
    print("\nFinal Verdict\n"+"-"*96)
    if errors:
        print("RELEASE INFRASTRUCTURE AUDIT: FAILED"); return 1
    if reviews:
        print("RELEASE INFRASTRUCTURE AUDIT: PASSED WITH REVIEW ITEMS"); return 0
    print("RELEASE INFRASTRUCTURE AUDIT: PASSED"); return 0

if __name__=="__main__":
    sys.exit(main())
