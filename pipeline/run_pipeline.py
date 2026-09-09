"""
Orchestrates stages 2.1 -> 2.6 end to end.

Usage:
    python3 run_pipeline.py <source_folder> [--db path/to/catalog.db]
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict
from pathlib import Path

from intake import walk_and_hash, IntakeRecord
from extraction import extract
from metadata import tier1_extract, tier2_extract, merge_and_gate
from db import get_connection, upsert_record


def process_one_file(rec: IntakeRecord, use_tier2: bool = True) -> dict:
    """
    Runs stages 2.2-2.5 on a single already-hashed file and returns a catalog-ready
    record dict (matching db.upsert_record's expected shape). Shared by the CLI
    runner and the background job worker so both use identical logic.

    Raises on extraction failure; caller decides how to record that as a job status.
    """
    ext_result = extract(rec.path)
    metadata_text = ext_result.text[:9000]
    first_page_text = ext_result.text[:1500]

    t1 = tier1_extract(rec.filename, metadata_text)

    t2 = None
    missing_core = [f for f in ("subject", "level", "year", "session", "exam_board", "paper_number")
                     if getattr(t1, f) is None]
    if use_tier2 and missing_core:
        t2 = tier2_extract(metadata_text)

    merged, needs_review, reasons = merge_and_gate(t1, t2)
    if ext_result.needs_review:
        needs_review = True
        reasons.append(f"ocr: {ext_result.review_reason}")

    return {
        "filename": rec.filename,
        "path": rec.path,
        "hash": rec.sha256,
        "subject": merged.subject,
        "level": merged.level,
        "year": merged.year,
        "session": merged.session,
        "syllabus_era": merged.syllabus_era,
        "paper_number": merged.paper_number,
        "doc_type": merged.doc_type,
        "exam_board": merged.exam_board,
        "extraction_method": ext_result.method,
        "confidence": "needs_review" if needs_review else "auto",
        "needs_review": needs_review,
        "review_reasons": "; ".join(reasons) if reasons else None,
        "text_snippet": first_page_text[:500],
    }


def run(source_folder: str, db_path: str, use_tier2: bool = True) -> None:
    print(f"[1/4] Intake & hashing: {source_folder}")
    intake_records = walk_and_hash(source_folder)
    dupes = [r for r in intake_records if r.is_duplicate]
    print(f"      {len(intake_records)} files found, {len(dupes)} exact duplicates flagged")

    conn = get_connection(db_path)
    needs_review_rows = []
    processed = 0

    for rec in intake_records:
        if rec.is_duplicate:
            print(f"      SKIP (duplicate of {rec.duplicate_of}): {rec.filename}")
            continue

        print(f"[2/4] Extracting: {rec.filename}")
        try:
            record = process_one_file(rec, use_tier2=use_tier2)
        except Exception as e:
            print(f"      EXTRACTION FAILED: {e}")
            needs_review_rows.append({
                "filename": rec.filename, "path": rec.path, "hash": rec.sha256,
                "reason": f"extraction_error: {e}", "text_snippet": "",
            })
            continue

        upsert_record(conn, record)
        processed += 1

        status = "NEEDS REVIEW" if record["needs_review"] else "auto-accepted"
        print(f"      -> {status} | subject={record['subject']} level={record['level']} "
              f"year={record['year']} session={record['session']} paper={record['paper_number']} board={record['exam_board']}")
        if record["needs_review"]:
            needs_review_rows.append({**record, "reason": record["review_reasons"]})

    print(f"[4/4] Writing needs_review.csv ({len(needs_review_rows)} rows)")
    review_path = Path(db_path).parent / "needs_review.csv"
    if needs_review_rows:
        with open(review_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(needs_review_rows[0].keys()))
            writer.writeheader()
            writer.writerows(needs_review_rows)
        print(f"      written to {review_path}")

    print(f"\nDone. {processed} files processed, {len(dupes)} duplicates skipped, "
          f"{len(needs_review_rows)} flagged for review.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_folder")
    parser.add_argument("--db", default="../data/catalog/catalog.db")
    parser.add_argument("--no-tier2", action="store_true", help="skip LLM fallback")
    args = parser.parse_args()

    run(args.source_folder, args.db, use_tier2=not args.no_tier2)
