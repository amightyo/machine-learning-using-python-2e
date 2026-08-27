#!/usr/bin/env python3
"""Audit chapter-to-chapter continuity in a Quarto book.

Machine Learning Using Python, Second Edition

Run from repository root:

    python tools/audit_book_continuity.py

Purpose
-------
This audit complements audit_book_structure.py.

It checks prose-level continuity across Chapters 1–18:
- explicit references such as "Chapter 5" and "Chapters 6–10";
- impossible/stale chapter numbers;
- references to a "next" or "previous" chapter that appear inconsistent
  with the book order;
- references to Parts I–VI;
- chapter opening/closing continuity cues;
- chapter titles and order derived from _quarto.yml.

Important
---------
A chapter does NOT need to mention another chapter in order to pass.
Low continuity counts are REVIEW items, not errors.

This script does not rewrite prose. It identifies locations for human review.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUARTO = ROOT / "_quarto.yml"

CHAPTER_PATH_RE = re.compile(
    r"^\s*-\s+((?:part-\d{2}-[^/]+/)?(\d{2})-[A-Za-z0-9_.-]+\.qmd)\s*$",
    re.MULTILINE,
)

H1 = re.compile(r"^#\s+(.+?)(?:\s+\{.*\})?\s*$", re.MULTILINE)

EXPLICIT_CHAPTER = re.compile(
    r"\bChapter\s+(\d{1,2})\b",
    re.IGNORECASE,
)

CHAPTER_RANGE = re.compile(
    r"\bChapters\s+(\d{1,2})\s*[–—-]\s*(\d{1,2})\b",
    re.IGNORECASE,
)

CHAPTER_LIST = re.compile(
    r"\bChapters\s+((?:\d{1,2}\s*,\s*)+\d{1,2}(?:\s*,?\s*and\s*\d{1,2})?)",
    re.IGNORECASE,
)

PART_REF = re.compile(
    r"\bPart\s+(I|II|III|IV|V|VI|VII|VIII|IX|X)\b",
    re.IGNORECASE,
)

NEXT_CHAPTER = re.compile(
    r"\b(?:the\s+)?next\s+chapter\b",
    re.IGNORECASE,
)

PREVIOUS_CHAPTER = re.compile(
    r"\b(?:the\s+)?(?:previous|preceding)\s+chapter\b",
    re.IGNORECASE,
)

TRANSITION_TERMS = re.compile(
    r"\b("
    r"building on|builds on|as introduced|as discussed|as developed|"
    r"earlier chapter|earlier chapters|later chapter|later chapters|"
    r"previous chapter|next chapter|return to|revisit|connects to|"
    r"prepares us|sets the stage|extends|carries forward"
    r")\b",
    re.IGNORECASE,
)


@dataclass
class Chapter:
    number: int
    path: Path
    rel: str
    title: str
    prose: str


def strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]+`", "", text)
    return text


def strip_yaml(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :]
    return text


def title_from_text(text: str, fallback: str) -> str:
    m = H1.search(text)
    if not m:
        return fallback
    return re.sub(r"\s+\{.*\}\s*$", "", m.group(1)).strip()


def chapter_order() -> list[Chapter]:
    yaml_text = QUARTO.read_text(encoding="utf-8")
    items = []

    for match in CHAPTER_PATH_RE.finditer(yaml_text):
        rel = match.group(1).replace("\\", "/")
        number = int(match.group(2))
        path = ROOT / rel

        if not path.exists():
            continue

        raw = path.read_text(encoding="utf-8")
        body = strip_yaml(raw)
        prose = strip_code(body)
        title = title_from_text(prose, path.stem)

        items.append(
            Chapter(
                number=number,
                path=path,
                rel=rel,
                title=title,
                prose=prose,
            )
        )

    return sorted(items, key=lambda c: c.number)


def line_number(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def beginning(text: str, n_chars: int = 2200) -> str:
    return text[:n_chars]


def ending(text: str, n_chars: int = 2800) -> str:
    return text[-n_chars:]


def main() -> int:
    print("Machine Learning Using Python — Chapter Continuity Audit")
    print("=" * 78)

    if not QUARTO.exists():
        print("[ERROR] Missing _quarto.yml")
        return 1

    chapters = chapter_order()

    errors: list[str] = []
    reviews: list[str] = []
    infos: list[str] = []

    if len(chapters) != 18:
        errors.append(f"Expected 18 numbered chapters; found {len(chapters)}.")

    numbers = [c.number for c in chapters]
    expected = list(range(1, 19))

    if numbers != expected:
        errors.append(
            "Chapter sequence is not exactly 1–18: "
            + ", ".join(map(str, numbers))
        )

    print(f"Numbered chapters scanned:          {len(chapters)}")
    print()

    by_number = {c.number: c for c in chapters}

    chapter_refs: dict[int, list[int]] = defaultdict(list)
    range_refs: dict[int, list[tuple[int, int]]] = defaultdict(list)

    print("Chapter Continuity Summary")
    print("-" * 78)

    for chapter in chapters:
        prose = chapter.prose

        explicit = []
        for m in EXPLICIT_CHAPTER.finditer(prose):
            target = int(m.group(1))
            explicit.append(target)
            chapter_refs[chapter.number].append(target)

            if target not in by_number:
                errors.append(
                    f"{chapter.rel}:{line_number(prose, m.start())} "
                    f"references nonexistent Chapter {target}."
                )

        for m in CHAPTER_RANGE.finditer(prose):
            start = int(m.group(1))
            end = int(m.group(2))
            range_refs[chapter.number].append((start, end))

            if start < 1 or end > 18 or start > end:
                errors.append(
                    f"{chapter.rel}:{line_number(prose, m.start())} "
                    f"contains invalid chapter range Chapters {start}–{end}."
                )

        for m in CHAPTER_LIST.finditer(prose):
            nums = [int(x) for x in re.findall(r"\d{1,2}", m.group(1))]
            for target in nums:
                chapter_refs[chapter.number].append(target)
                if target not in by_number:
                    errors.append(
                        f"{chapter.rel}:{line_number(prose, m.start())} "
                        f"references nonexistent Chapter {target}."
                    )

        for m in PART_REF.finditer(prose):
            roman = m.group(1).upper()
            if roman in {"VII", "VIII", "IX", "X"}:
                errors.append(
                    f"{chapter.rel}:{line_number(prose, m.start())} "
                    f"references nonexistent Part {roman}."
                )

        for m in NEXT_CHAPTER.finditer(prose):
            if chapter.number == 18:
                errors.append(
                    f"{chapter.rel}:{line_number(prose, m.start())} "
                    "uses 'next chapter' even though Chapter 18 is the final numbered chapter."
                )

        for m in PREVIOUS_CHAPTER.finditer(prose):
            if chapter.number == 1:
                errors.append(
                    f"{chapter.rel}:{line_number(prose, m.start())} "
                    "uses 'previous chapter' even though Chapter 1 is the first numbered chapter."
                )

        transitions = list(TRANSITION_TERMS.finditer(prose))

        open_transition = bool(
            TRANSITION_TERMS.search(beginning(prose))
            or EXPLICIT_CHAPTER.search(beginning(prose))
        )
        close_transition = bool(
            TRANSITION_TERMS.search(ending(prose))
            or EXPLICIT_CHAPTER.search(ending(prose))
        )

        if chapter.number > 1 and not open_transition:
            reviews.append(
                f"Chapter {chapter.number} opening has no obvious backward/continuity cue: "
                f"{chapter.title}"
            )

        if chapter.number < 18 and not close_transition:
            reviews.append(
                f"Chapter {chapter.number} ending has no obvious forward/continuity cue: "
                f"{chapter.title}"
            )

        unique_targets = sorted(set(explicit))

        print(
            f"Ch {chapter.number:>2}  "
            f"explicit chapter refs={len(explicit):>2}  "
            f"unique targets={len(unique_targets):>2}  "
            f"transition cues={len(transitions):>2}  "
            f"{chapter.title}"
        )

    for source, targets in sorted(chapter_refs.items()):
        if source in targets:
            infos.append(
                f"Chapter {source} explicitly refers to itself; verify this is intentional."
            )

    for source, targets in sorted(chapter_refs.items()):
        for target in sorted(set(targets)):
            if abs(source - target) >= 6:
                infos.append(
                    f"Long-range continuity link: Chapter {source} → Chapter {target}."
                )

    no_explicit = [
        c.number for c in chapters
        if not chapter_refs.get(c.number) and not range_refs.get(c.number)
    ]

    print()
    print("Book-Level Continuity")
    print("-" * 78)
    print(f"Explicit Chapter-N references:      {sum(len(v) for v in chapter_refs.values())}")
    print(f"Explicit chapter-range references:  {sum(len(v) for v in range_refs.values())}")
    print(f"Chapters with no explicit refs:     {len(no_explicit)}")
    if no_explicit:
        print("  " + ", ".join(f"Ch {n}" for n in no_explicit))

    print()
    print("Continuity Review")
    print("-" * 78)
    print(f"Errors:                             {len(errors)}")
    print(f"Review items:                       {len(reviews)}")
    print(f"Informational items:                {len(infos)}")

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
    print("-" * 78)
    print(
        "A continuity cue is not required in every chapter opening or ending. "
        "Review items identify opportunities for smoother reader transitions; "
        "they are not automatically defects."
    )

    print()
    print("Final Verdict")
    print("-" * 78)

    if errors:
        print("CONTINUITY AUDIT: FAILED")
        return 1

    if reviews:
        print("CONTINUITY AUDIT: PASSED WITH REVIEW ITEMS")
        return 0

    print("CONTINUITY AUDIT: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
