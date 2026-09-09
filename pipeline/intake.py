"""
Stage 2.1 — Intake & Hashing

Walks a source folder, computes SHA-256 per file, detects exact duplicates,
and logs basic file info. This is the first stage of the pipeline and
produces the initial row set that later stages enrich.
"""
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".jpg", ".jpeg", ".png"}


@dataclass
class IntakeRecord:
    filename: str
    path: str
    size_bytes: int
    sha256: str
    file_type: str
    is_duplicate: bool = False
    duplicate_of: str | None = None


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def walk_and_hash(source_folder: str) -> list[IntakeRecord]:
    """
    Recursively walk source_folder, hash every supported file, and flag
    exact-hash duplicates (spec 2.1: skip/flag before spending processing
    time on them).
    """
    records: list[IntakeRecord] = []
    seen_hashes: dict[str, str] = {}  # sha256 -> first path that had it

    for root, _dirs, files in os.walk(source_folder):
        for fname in sorted(files):
            fpath = Path(root) / fname
            ext = fpath.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            try:
                digest = sha256_file(fpath)
            except OSError as e:
                print(f"[intake] could not read {fpath}: {e}")
                continue

            size = fpath.stat().st_size
            is_dup = digest in seen_hashes
            dup_of = seen_hashes.get(digest)
            if not is_dup:
                seen_hashes[digest] = str(fpath)

            records.append(
                IntakeRecord(
                    filename=fname,
                    path=str(fpath),
                    size_bytes=size,
                    sha256=digest,
                    file_type=ext,
                    is_duplicate=is_dup,
                    duplicate_of=dup_of,
                )
            )

    return records


if __name__ == "__main__":
    import sys
    import json

    folder = sys.argv[1] if len(sys.argv) > 1 else "data/intake"
    recs = walk_and_hash(folder)
    dupes = [r for r in recs if r.is_duplicate]
    print(f"Scanned {len(recs)} files, {len(dupes)} exact duplicates flagged.")
    for r in recs:
        print(json.dumps(r.__dict__))
