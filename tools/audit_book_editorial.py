#!/usr/bin/env python3
"""
Machine Learning Using Python
Pass 4D-A — Refined Editorial Consistency & Reader Experience Audit
"""

from __future__ import annotations
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_DIRS = {
    "_book", ".git", ".quarto", ".venv", "venv", "__pycache__",
    "renv", "site_libs", "freeze", "_freeze",
}

TERM_VARIANTS = {
    "cross-validation": [r"\bcross validation\b"],
    "hyperparameter": [r"\bhyper-parameter\b", r"\bhyper parameter\b"],
    "dataset": [r"\bdata set\b"],
    "decision tree": [
        r"\bdecision-tree\b(?=\s+(?:algorithm|classifier|regressor|model|method)s?\b)"
    ],
    "random forest": [
        r"\brandom-forest\b(?=\s+(?:algorithm|classifier|regressor|model|method)s?\b)"
    ],
}

PLACEHOLDER_PATTERNS = {
    "TODO": r"\bTODO\b",
    "FIXME": r"\bFIXME\b",
    "TBD": r"\bTBD\b",
    "XXX": r"\bXXX\b",
    "placeholder": r"\bplaceholder\b",
    "insert citation": r"\binsert citation\b",
    "citation needed": r"\bcitation needed\b",
    "insert figure": r"\binsert figure\b",
    "insert table": r"\binsert table\b",
}

ABSOLUTE_LANGUAGE = [
    "always", "never", "guarantees", "guaranteed", "proves",
    "proven", "perfect", "completely", "obviously", "clearly",
]

ALLOWED_REPEAT_HEADINGS = {
    "example", "examples", "exercise", "exercises",
    "research reality check", "three tracks", "knowledge check",
    "summary", "looking ahead", "why this matters",
    "central question", "practical implications", "research implications",
}

ACRONYM_ALLOWLIST = {
    "AI","ML","API","CPU","GPU","CSV","JSON","HTML","PDF","URL","DOI","ISBN",
    "IDE","SQL","OS","RAM","ROC","AUC","PR","PCA","SVM","NLP","MLP","CNN","RNN",
    "LLM","SHAP","LIME","MSE","RMSE","MAE","RSE","RNG","TF","IDF","TFIDF","KNN",
    "KMEANS","UMAP","SMOTE","RELU","OLS","RBF","DBSCAN","OOB","OSF","README",
    "NHANES","IPEDS","CV","TP","TN","FP","FN","DP","QK","HW","SNE",
}

LEARNING_HEADING_PATTERNS = [
    r"learning objectives?", r"learning goals?", r"chapter objectives?", r"what you will learn",
]
KNOWLEDGE_HEADING_PATTERNS = [
    r"knowledge check", r"knowledge checks", r"check your understanding",
    r"review questions?", r"self[- ]check",
]
ENDING_HEADING_PATTERNS = [
    r"summary", r"chapter summary", r"conclusion", r"conclusions",
    r"key takeaways", r"looking ahead", r"what comes next",
]

@dataclass
class Finding:
    level: str
    path: str
    line: int | None
    message: str
    def render(self) -> str:
        loc = self.path if self.line is None else f"{self.path}:{self.line}"
        return f"[{self.level}] {loc}: {self.message}"

@dataclass
class PageProfile:
    path: Path
    relative: str
    is_chapter: bool
    chapter_number: int | None
    title: str
    headings: list[tuple[int,str,int]] = field(default_factory=list)
    word_count: int = 0
    code_cells: int = 0
    callouts: Counter = field(default_factory=Counter)
    learning_sections: int = 0
    knowledge_sections: int = 0
    ending_sections: int = 0

def relpath(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def strip_yaml(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i+1:])
    return text

def preserve_newlines_sub(pattern: str, repl: str, text: str, flags: int = 0) -> str:
    def _r(m: re.Match) -> str:
        return repl + ("\n" * m.group(0).count("\n"))
    return re.sub(pattern, _r, text, flags=flags)

def strip_code_fences(text: str) -> str:
    out, inside = [], False
    for line in text.splitlines():
        if re.match(r"^\s*```", line):
            inside = not inside
            out.append("")
        else:
            out.append("" if inside else line)
    return "\n".join(out)

def strip_display_math(text: str) -> str:
    return preserve_newlines_sub(r"\$\$.*?\$\$", " ", text, flags=re.DOTALL)

def strip_inline_math(text: str) -> str:
    return re.sub(r"(?<!\$)\$(?!\$).*?(?<!\$)\$(?!\$)", " ", text)

def strip_raw_latex(text: str) -> str:
    text = preserve_newlines_sub(
        r"\\begin\{[^}]+\}.*?\\end\{[^}]+\}", " ", text, flags=re.DOTALL
    )
    return re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})*", " ", text)

def prose_for_analysis(text: str) -> str:
    text = strip_yaml(text)
    text = strip_code_fences(text)
    text = strip_display_math(text)
    text = strip_inline_math(text)
    text = strip_raw_latex(text)
    text = preserve_newlines_sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"\[@[^\]]+\]", " ", text)
    text = re.sub(r"(?<!\w)@[A-Za-z0-9_:\-]+", " ", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\{[.#][^}]+\}", " ", text)
    text = re.sub(
        r"(?m)^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", " ", text
    )
    return text

def manuscript_files() -> list[Path]:
    return sorted(
        [
            p for p in ROOT.rglob("*.qmd")
            if not any(part in EXCLUDED_DIRS for part in p.parts)
        ],
        key=lambda p: relpath(p).lower()
    )

def chapter_number(path: Path) -> int | None:
    m = re.match(r"^(\d{2})-", path.name)
    return int(m.group(1)) if m else None

def extract_title(text: str, path: Path) -> str:
    for line in strip_yaml(text).splitlines():
        m = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if m:
            title = re.sub(r"\s*\{[^}]+\}\s*$", "", m.group(1))
            return re.sub(r"[*_`]", "", title).strip()
    return path.stem

def extract_headings(text: str) -> list[tuple[int,str,int]]:
    out = []
    body = strip_code_fences(strip_yaml(text))
    for lineno, line in enumerate(body.splitlines(), start=1):
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if m:
            title = re.sub(r"\s*\{[^}]+\}\s*$", "", m.group(2))
            title = re.sub(r"[*_`]", "", title).strip()
            out.append((len(m.group(1)), title, lineno))
    return out

def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", prose_for_analysis(text), flags=re.UNICODE))

def count_code_cells(text: str) -> int:
    return len(re.findall(r"^\s*```\{python\b", text, flags=re.MULTILINE))

def extract_callouts(text: str) -> Counter:
    c = Counter()
    for m in re.finditer(r"\.callout-([A-Za-z0-9_-]+)", text, flags=re.I):
        c[m.group(1).lower()] += 1
    return c

def heading_matches(title: str, patterns: list[str]) -> bool:
    norm = re.sub(r"\s+", " ", title.strip().lower())
    return any(re.fullmatch(p, norm, flags=re.I) for p in patterns)

def build_profile(path: Path) -> PageProfile:
    text = read_text(path)
    num = chapter_number(path)
    headings = extract_headings(text)
    return PageProfile(
        path=path,
        relative=relpath(path),
        is_chapter=num is not None,
        chapter_number=num,
        title=extract_title(text, path),
        headings=headings,
        word_count=count_words(text),
        code_cells=count_code_cells(text),
        callouts=extract_callouts(text),
        learning_sections=sum(heading_matches(t, LEARNING_HEADING_PATTERNS) for _,t,_ in headings),
        knowledge_sections=sum(heading_matches(t, KNOWLEDGE_HEADING_PATTERNS) for _,t,_ in headings),
        ending_sections=sum(heading_matches(t, ENDING_HEADING_PATTERNS) for _,t,_ in headings),
    )

def audit_heading_hierarchy(profile, findings):
    prev = None
    for level, title, line in profile.headings:
        if prev is not None and level > prev + 1:
            findings.append(Finding(
                "REVIEW", profile.relative, line,
                f"heading jumps from H{prev} to H{level} at '{title}'."
            ))
        prev = level

def audit_duplicate_headings(profile, findings):
    seen = {}
    for _, title, line in profile.headings:
        key = re.sub(r"\s+", " ", title.lower()).strip()
        seen.setdefault(key, []).append(line)
    for title, lines in seen.items():
        if len(lines) > 1 and title not in ALLOWED_REPEAT_HEADINGS:
            findings.append(Finding(
                "REVIEW", profile.relative, lines[1],
                f"structural heading '{title}' appears {len(lines)} times "
                f"(lines {', '.join(map(str, lines))}); verify intentional duplication."
            ))

def audit_placeholders(path, findings):
    text = prose_for_analysis(read_text(path))
    for label, pat in PLACEHOLDER_PATTERNS.items():
        for m in re.finditer(pat, text, flags=re.I):
            line = text.count("\n", 0, m.start()) + 1
            findings.append(Finding(
                "ERROR", relpath(path), line,
                f"possible unfinished manuscript marker: '{label}'."
            ))

def audit_term_variants(path, findings):
    text = prose_for_analysis(read_text(path))
    for preferred, variants in TERM_VARIANTS.items():
        for pat in variants:
            ms = list(re.finditer(pat, text, flags=re.I))
            if ms:
                line = text.count("\n", 0, ms[0].start()) + 1
                findings.append(Finding(
                    "REVIEW", relpath(path), line,
                    f"found {len(ms)} occurrence(s) of a possible variant "
                    f"of preferred form '{preferred}'."
                ))

def audit_whitespace_and_punctuation(path, findings):
    text = prose_for_analysis(read_text(path))
    issues = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if not s or s.startswith("|") or s.startswith(":::"):
            continue
        if re.search(r"\b[\w'’”-]+\s+[,.!?;:](?=\s|$)", line):
            issues.append((lineno, "possible space before punctuation"))
        if re.search(r"[a-z0-9][.!?][A-Z][a-z]", line):
            issues.append((lineno, "possible missing space after sentence punctuation"))
        if re.search(r"[!?]{2,}", line):
            issues.append((lineno, "repeated exclamation/question punctuation"))
        if re.search(r"\.{4,}", line):
            issues.append((lineno, "four or more consecutive periods"))
    if issues:
        grouped = Counter(msg for _,msg in issues)
        first = min(line for line,_ in issues)
        detail = "; ".join(f"{msg}={count}" for msg,count in grouped.items())
        findings.append(Finding(
            "INFO", relpath(path), first,
            f"punctuation/spacing heuristic found: {detail}."
        ))

def audit_absolute_language(profile, findings):
    if not profile.is_chapter:
        return
    text = prose_for_analysis(read_text(profile.path)).lower()
    counts = Counter()
    for term in ABSOLUTE_LANGUAGE:
        n = len(re.findall(rf"\b{re.escape(term)}\b", text))
        if n:
            counts[term] = n
    if sum(counts.values()) >= 10:
        detail = ", ".join(f"{k}={v}" for k,v in counts.items())
        findings.append(Finding(
            "REVIEW", profile.relative, None,
            f"frequent absolute-language terms ({detail}); review claims "
            "for appropriate qualification."
        ))

def audit_acronyms(profile, findings):
    if not profile.is_chapter:
        return
    text = prose_for_analysis(read_text(profile.path))
    counts = Counter(re.findall(r"\b[A-Z]{2,8}\b", text))
    for acronym, count in sorted(counts.items()):
        if acronym in ACRONYM_ALLOWLIST or count < 3:
            continue
        expanded_after = re.search(
            rf"\b[A-Z][A-Za-z0-9,\-/ ]{{3,100}}\s+\({re.escape(acronym)}\)", text
        )
        expanded_before = re.search(
            rf"\b{re.escape(acronym)}\s+\([A-Za-z][A-Za-z0-9,\-/ ]{{3,100}}\)", text
        )
        if expanded_after or expanded_before:
            continue
        first = re.search(rf"\b{re.escape(acronym)}\b", text)
        line = text.count("\n", 0, first.start()) + 1 if first else None
        findings.append(Finding(
            "REVIEW", profile.relative, line,
            f"acronym '{acronym}' appears {count} times but no obvious local expansion was detected."
        ))

def audit_chapter_reader_experience(profile, findings):
    if not profile.is_chapter:
        return
    if profile.learning_sections == 0:
        findings.append(Finding("REVIEW", profile.relative, None, "no explicit learning-objective/learning-goal heading detected."))
    if profile.knowledge_sections == 0:
        findings.append(Finding("REVIEW", profile.relative, None, "no explicit knowledge-check/review-question heading detected."))
    if profile.ending_sections == 0:
        findings.append(Finding("REVIEW", profile.relative, None, "no conventional chapter-ending heading detected."))

def audit_chapter_length(chapters, findings):
    if not chapters:
        return
    counts = sorted(p.word_count for p in chapters)
    median = counts[len(counts)//2]
    if not median:
        return
    for p in chapters:
        ratio = p.word_count / median
        if ratio < 0.40:
            findings.append(Finding(
                "REVIEW", p.relative, None,
                f"chapter is comparatively short ({p.word_count:,} words; median {median:,}); verify intentional scope."
            ))
        elif ratio > 2.35:
            findings.append(Finding(
                "REVIEW", p.relative, None,
                f"chapter is comparatively long ({p.word_count:,} words; median {median:,}); verify pacing and section balance."
            ))

def audit_heading_form_consistency(chapters, patterns, label, findings):
    names = Counter()
    for p in chapters:
        for _, title, _ in p.headings:
            if heading_matches(title, patterns):
                names[title.strip()] += 1
    if len(names) > 1:
        detail = "; ".join(f"'{name}'={count}" for name,count in names.most_common())
        findings.append(Finding(
            "REVIEW", "<book>", None,
            f"multiple {label} heading forms are used: {detail}."
        ))

def audit_callout_consistency(profiles, findings):
    all_callouts = Counter()
    for p in profiles:
        all_callouts.update(p.callouts)
    unusual = sorted(name for name,count in all_callouts.items() if count == 1)
    if unusual:
        findings.append(Finding(
            "INFO", "<book>", None,
            "single-use callout type(s): " + ", ".join(unusual) + ". Verify these are intentional."
        ))

def print_rule(char="-", width=88):
    print(char * width)

def print_profile_table(chapters):
    print("Chapter Editorial Profile")
    print_rule()
    for p in chapters:
        print(
            f"Ch {p.chapter_number:>2}  "
            f"words={p.word_count:>6,}  "
            f"headings={len(p.headings):>3}  "
            f"code={p.code_cells:>2}  "
            f"callouts={sum(p.callouts.values()):>2}  "
            f"learning={p.learning_sections}  "
            f"checks={p.knowledge_sections}  "
            f"ending={p.ending_sections}  "
            f"{p.title}"
        )
    print()

def main() -> int:
    files = manuscript_files()
    profiles = [build_profile(p) for p in files]
    chapters = sorted([p for p in profiles if p.is_chapter], key=lambda p: p.chapter_number or 999)
    findings = []

    for p in profiles:
        audit_heading_hierarchy(p, findings)
        audit_duplicate_headings(p, findings)
        audit_placeholders(p.path, findings)
        audit_term_variants(p.path, findings)
        audit_whitespace_and_punctuation(p.path, findings)
        audit_absolute_language(p, findings)
        audit_acronyms(p, findings)
        audit_chapter_reader_experience(p, findings)

    audit_chapter_length(chapters, findings)
    audit_heading_form_consistency(chapters, LEARNING_HEADING_PATTERNS, "learning-section", findings)
    audit_heading_form_consistency(chapters, KNOWLEDGE_HEADING_PATTERNS, "knowledge-check", findings)
    audit_callout_consistency(profiles, findings)

    errors = [f for f in findings if f.level == "ERROR"]
    reviews = [f for f in findings if f.level == "REVIEW"]
    infos = [f for f in findings if f.level == "INFO"]

    print("Machine Learning Using Python — Editorial Consistency & Reader Experience Audit")
    print_rule("=", 88)
    print(f"Repository QMD pages scanned:       {len(files)}")
    print(f"Numbered chapters scanned:          {len(chapters)}")
    print()

    print_profile_table(chapters)

    print("Book-Level Editorial Summary")
    print_rule()
    print(f"Approximate chapter prose words:    {sum(p.word_count for p in chapters):,}")
    print(f"Executable Python cells:            {sum(p.code_cells for p in chapters)}")
    print(f"Quarto callouts in chapters:        {sum(sum(p.callouts.values()) for p in chapters)}")
    print(f"Chapters with learning sections:    {sum(p.learning_sections > 0 for p in chapters)}/{len(chapters)}")
    print(f"Chapters with knowledge checks:     {sum(p.knowledge_sections > 0 for p in chapters)}/{len(chapters)}")
    print(f"Chapters with ending sections:      {sum(p.ending_sections > 0 for p in chapters)}/{len(chapters)}")
    print()

    print("Editorial Review")
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
        "This refined audit is intentionally conservative. Errors are reserved for likely unfinished "
        "manuscript artifacts. Review items identify structural, terminological, acronym, punctuation, "
        "or reader-experience issues that may require human judgment. Recurring pedagogical headings, "
        "ordinary compound modifiers, and common field acronyms are deliberately tolerated."
    )
    print()

    print("Final Verdict")
    print_rule()
    if errors:
        print("EDITORIAL AUDIT: FAILED")
        return 1
    if reviews:
        print("EDITORIAL AUDIT: PASSED WITH REVIEW ITEMS")
        return 0
    print("EDITORIAL AUDIT: PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
