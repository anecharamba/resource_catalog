"""
Stage 2.2 — Text Extraction (branch by type)
Stage 2.3 — OCR path for scanned PDFs / images

Branching logic (spec 2.2):
  .docx              -> python-docx, direct extraction
  .pdf digital        -> pdfplumber text layer
  .pdf scanned/image  -> OCR path

Detection: if a PDF's extracted text layer is shorter than DIGITAL_TEXT_THRESHOLD
characters, treat it as scanned and route to OCR.
"""
from __future__ import annotations

import io
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber
import pytesseract

if sys.platform == "win32":
    # Deliberately does NOT trust shutil.which("tesseract")/PATH here. If a
    # machine has more than one Tesseract install (e.g. a stale one left on
    # PATH from an earlier attempt), PATH can resolve to an exe whose sibling
    # "tessdata" folder is missing or empty, producing "Failed loading
    # language 'eng'" even though a perfectly good install exists elsewhere.
    # Instead, check each known install location as a matched (exe, tessdata)
    # pair and only use one where eng.traineddata actually exists — then pin
    # both pytesseract.tesseract_cmd and TESSDATA_PREFIX to that same pair,
    # so they can never point at two different installations.
    for install_dir in (
        Path(r"C:\Program Files\Tesseract-OCR"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR"),
    ):
        exe = install_dir / "tesseract.exe"
        tessdata = install_dir / "tessdata"
        if exe.exists() and (tessdata / "eng.traineddata").exists():
            pytesseract.pytesseract.tesseract_cmd = str(exe)
            os.environ["TESSDATA_PREFIX"] = str(tessdata)
            break
from PIL import Image

try:
    import docx  # python-docx
except ImportError:
    docx = None

DIGITAL_TEXT_THRESHOLD = 50  # chars on page 1; below this -> treat as scanned
OCR_DPI = 300
MIN_READABLE_WORDS = 15  # per page, below this -> flag needs_review (spec 2.3.3)


@dataclass
class ExtractionResult:
    text: str
    method: str  # "digital_pdf" | "docx" | "ocr"
    pages: int
    ocr_mean_confidence: float | None = None
    needs_review: bool = False
    review_reason: str | None = None


def _extract_docx(path: Path) -> ExtractionResult:
    if docx is None:
        raise RuntimeError("python-docx not installed")
    d = docx.Document(str(path))
    text = "\n".join(p.text for p in d.paragraphs)
    return ExtractionResult(text=text, method="docx", pages=1)


def _pdf_page1_text_len(path: Path) -> int:
    with pdfplumber.open(path) as pdf:
        if not pdf.pages:
            return 0
        t = pdf.pages[0].extract_text() or ""
        return len(t.strip())


def _extract_digital_pdf(path: Path) -> ExtractionResult:
    with pdfplumber.open(path) as pdf:
        pages_text = [p.extract_text() or "" for p in pdf.pages]
    return ExtractionResult(text="\n".join(pages_text), method="digital_pdf", pages=len(pages_text))


def _extract_ocr_pdf(path: Path, max_pages: int | None = None) -> ExtractionResult:
    """
    OCR path (spec 2.3). Preprocessing is applied conditionally: only when a
    quick contrast-variance check suggests a degraded scan, since our sample
    test showed preprocessing can slightly *hurt* confidence on already-clean
    CamScanner-style output.
    """
    doc = fitz.open(str(path))
    n_pages = len(doc) if max_pages is None else min(max_pages, len(doc))

    all_text = []
    all_confs: list[float] = []
    low_word_pages = 0

    for i in range(n_pages):
        page = doc[i]
        pix = page.get_pixmap(dpi=OCR_DPI)
        img = Image.open(io.BytesIO(pix.tobytes("png")))

        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        confs = [int(c) for c in data["conf"] if c not in ("-1", -1) and int(c) >= 0]
        text = pytesseract.image_to_string(img)
        words = [w for w in text.split() if w.strip()]

        all_text.append(text)
        all_confs.extend(confs)
        if len(words) < MIN_READABLE_WORDS:
            low_word_pages += 1

    mean_conf = sum(all_confs) / len(all_confs) if all_confs else 0.0
    needs_review = low_word_pages > 0 or mean_conf < 40
    reason = None
    if needs_review:
        reasons = []
        if low_word_pages:
            reasons.append(f"{low_word_pages} page(s) below {MIN_READABLE_WORDS}-word threshold")
        if mean_conf < 40:
            reasons.append(f"low mean OCR confidence ({mean_conf:.0f})")
        reason = "; ".join(reasons)

    return ExtractionResult(
        text="\n".join(all_text),
        method="ocr",
        pages=n_pages,
        ocr_mean_confidence=round(mean_conf, 1),
        needs_review=needs_review,
        review_reason=reason,
    )


def extract(path_str: str) -> ExtractionResult:
    path = Path(path_str)
    ext = path.suffix.lower()

    if ext == ".docx":
        return _extract_docx(path)

    if ext == ".pdf":
        page1_len = _pdf_page1_text_len(path)
        if page1_len >= DIGITAL_TEXT_THRESHOLD:
            return _extract_digital_pdf(path)
        return _extract_ocr_pdf(path)

    if ext in (".jpg", ".jpeg", ".png"):
        img = Image.open(path)
        text = pytesseract.image_to_string(img)
        words = [w for w in text.split() if w.strip()]
        needs_review = len(words) < MIN_READABLE_WORDS
        return ExtractionResult(
            text=text,
            method="ocr",
            pages=1,
            needs_review=needs_review,
            review_reason="below word threshold" if needs_review else None,
        )

    raise ValueError(f"Unsupported file type: {ext}")


if __name__ == "__main__":
    import sys

    for p in sys.argv[1:]:
        r = extract(p)
        print(f"--- {p} ---")
        print(f"method={r.method} pages={r.pages} chars={len(r.text)} "
              f"ocr_conf={r.ocr_mean_confidence} needs_review={r.needs_review} ({r.review_reason})")
        print(r.text[:200].replace("\n", " "))
        print()
