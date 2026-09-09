"""
Stage 2.4 — Metadata Extraction (two-tier)
Stage 2.5 — Confidence Gating

Tier 1: cheap regex against filename + first-page text.
Tier 2: LLM fallback for anything Tier 1 leaves null/low-confidence.

Both tiers write into the same Metadata shape so gating (2.5) can compare
field-by-field agreement.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from dataclasses import dataclass, asdict

import requests

# --- Known ZIMSEC subjects / boards seen in filenames & headers ---
SUBJECT_KEYWORDS = {
    "mathematics": ["mathematics", "pure mathematics", "maths"],
    "history": ["history"],
    "english": ["english language", "english"],
    "biology": ["biology"],
    "chemistry": ["chemistry"],
    "physics": ["physics"],
    "geography": ["geography"],
    "economics": ["economics"],
    "accounting": ["accounting", "principles of accounts"],
    "computer_science": ["computer science"],
}

LEVEL_PATTERNS = [
    (r"\bA[\s\-]?Level\b|\bAdvanced Level\b", "A-Level"),
    (r"\bO[\s\-]?Level\b|\bOrdinary Level\b", "O-Level"),
    (r"\bForm\s*4\b", "Form 4"),
    (r"\bForm\s*6\b", "Form 6"),
]

EXAM_BOARD_PATTERNS = [
    (r"ZIMSEC|Zimbabwe School Examinations Council", "ZIMSEC"),
    (r"\bCambridge\b|\bCIE\b", "Cambridge"),
]

CURRENT_YEAR = datetime.now().year
YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
SESSION_PATTERN = re.compile(r"\b(june|november|jun|nov)\b", re.IGNORECASE)
PAPER_PATTERN = re.compile(r"paper\s*(\d)", re.IGNORECASE)
SYLLABUS_CODE_PATTERN = re.compile(r"\b(\d{4})/(\d)\b")  # e.g. 6042/2, 6006/2

SYLLABUS_ERA_CUTOFF = 2017


@dataclass
class Metadata:
    subject: str | None = None
    level: str | None = None
    year: int | None = None
    session: str | None = None  # "June" | "November"
    exam_board: str | None = None
    paper_number: int | None = None
    syllabus_code: str | None = None
    syllabus_era: str | None = None  # "pre-2017" | "post-2017"
    doc_type: str = "exam_paper"
    tier: str = "tier1"
    field_confidence: dict | None = None  # per-field bool: matched or not


def syllabus_era(year: int | None) -> str | None:
    if year is None:
        return None
    return "pre-2017" if year < SYLLABUS_ERA_CUTOFF else "post-2017"


def tier1_extract(filename: str, first_page_text: str) -> Metadata:
    """Regex-only pass against filename + first-page text (spec 2.4 Tier 1)."""
    haystack = f"{filename}\n{first_page_text}".lower()
    haystack_original_case = f"{filename}\n{first_page_text}"

    md = Metadata(tier="tier1")
    confidence = {}

    # subject
    for subj, kws in SUBJECT_KEYWORDS.items():
        if any(kw in haystack for kw in kws):
            md.subject = subj
            break
    confidence["subject"] = md.subject is not None

    # level
    for pattern, label in LEVEL_PATTERNS:
        if re.search(pattern, haystack_original_case, re.IGNORECASE):
            md.level = label
            break
    confidence["level"] = md.level is not None

    # exam board
    for pattern, label in EXAM_BOARD_PATTERNS:
        if re.search(pattern, haystack_original_case, re.IGNORECASE):
            md.exam_board = label
            break
    confidence["exam_board"] = md.exam_board is not None

    # year
    year_match = YEAR_PATTERN.search(haystack)
    if year_match:
        candidate_year = int(year_match.group(1))
        if 2000 <= candidate_year <= CURRENT_YEAR:
            md.year = candidate_year
    confidence["year"] = md.year is not None

    # exam session: only June or November are accepted; never guess.
    session_match = SESSION_PATTERN.search(haystack)
    if session_match:
        value = session_match.group(1).lower()
        md.session = "June" if value in {"june", "jun"} else "November"
    confidence["session"] = md.session is not None

    # paper number
    paper_match = PAPER_PATTERN.search(haystack)
    syllabus_match = SYLLABUS_CODE_PATTERN.search(haystack_original_case)
    if syllabus_match:
        md.syllabus_code = syllabus_match.group(0)
        md.paper_number = int(syllabus_match.group(2))
    elif paper_match:
        md.paper_number = int(paper_match.group(1))
    confidence["paper_number"] = md.paper_number is not None

    md.syllabus_era = syllabus_era(md.year)
    md.field_confidence = confidence
    return md


TIER2_SYSTEM_PROMPT = """You extract exam-paper metadata from OCR/PDF text.
Return ONLY a JSON object, no prose, no markdown fences, with exactly these keys:
subject, level, year, session, exam_board, paper_number.
Use null for any field you are not confident about. Do not guess.
Valid level values: "A-Level", "O-Level", "Form 4", "Form 6", or null.
year must be an integer between 2000 and 2026, or null.
session must be exactly "June" or "November", or null.
paper_number must be a small integer (1-4), or null.
"""


def tier2_extract(text_snippet: str, api_key: str | None = None) -> Metadata:
    """
    LLM fallback (spec 2.4 Tier 2). Calls Claude with a strict JSON-only
    extraction prompt. Falls back gracefully (returns empty Metadata) if
    no API key is configured, so the pipeline never hard-fails here.
    """
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        md = Metadata(tier="tier2")
        md.field_confidence = {"error": "no ANTHROPIC_API_KEY set"}
        return md

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 300,
            "system": TIER2_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": text_snippet[:3000]}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["content"][0]["text"]
    content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    parsed = json.loads(content)

    md = Metadata(
        subject=parsed.get("subject"),
        level=parsed.get("level"),
        year=parsed.get("year"),
        session=parsed.get("session") if parsed.get("session") in {"June", "November"} else None,
        exam_board=parsed.get("exam_board"),
        paper_number=parsed.get("paper_number"),
        tier="tier2",
    )
    md.syllabus_era = syllabus_era(md.year)
    md.field_confidence = {k: v is not None for k, v in parsed.items()}
    return md


def merge_and_gate(t1: Metadata, t2: Metadata | None) -> tuple[Metadata, bool, list[str]]:
    """
    Stage 2.5 — Confidence Gating.
    Compares Tier 1 and Tier 2 field-by-field. Where they agree (or Tier 2
    wasn't needed because Tier 1 was already complete), auto-accept.
    Where they disagree, or both are null/low-confidence, flag needs_review.
    Returns: (merged_metadata, needs_review, list_of_disagreement_reasons)
    """
    fields = ["subject", "level", "year", "session", "exam_board", "paper_number"]
    merged = Metadata(
        syllabus_code=t1.syllabus_code,
        doc_type=t1.doc_type,
        tier="merged",
    )
    disagreements = []

    for f in fields:
        v1 = getattr(t1, f)
        v2 = getattr(t2, f) if t2 else None

        if v1 is not None and v2 is not None:
            if v1 == v2:
                setattr(merged, f, v1)
            else:
                disagreements.append(f"{f}: tier1={v1!r} vs tier2={v2!r}")
                setattr(merged, f, v1)  # keep tier1 as best guess, but flagged
        elif v1 is not None:
            setattr(merged, f, v1)
        elif v2 is not None:
            setattr(merged, f, v2)
        # else both null -> stays None, contributes to needs_review below

    merged.syllabus_era = syllabus_era(merged.year)

    missing = [f for f in fields if getattr(merged, f) is None]
    needs_review = bool(disagreements) or len(missing) >= 2  # 2+ missing core fields = weak row

    reasons = list(disagreements)
    if missing:
        reasons.append(f"missing fields: {', '.join(missing)}")

    return merged, needs_review, reasons


if __name__ == "__main__":
    # quick smoke test against our two sample files' known header text
    sample_history = "ZIMSEC HISTORY 6006/2 PAPER 2 Regional and International History SPECIMEN PAPER"
    sample_math = "ZIMBABWE SCHOOL EXAMINATIONS COUNCIL PURE MATHEMATICS PAPER 2 6042/2 JUNE 2026 SESSION"

    for name, text in [("6006q02-History.pdf", sample_history), ("alevel_mathematics_J2026.pdf", sample_math)]:
        t1 = tier1_extract(name, text)
        print(name, "->", asdict(t1))
