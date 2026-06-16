import gc
import io
import os
import re
import subprocess
import sys
import tempfile

MAX_INDEX_PAGES = 300
GC_EVERY_N_PAGES = 10
EXTRACTION_TIMEOUT_SECONDS = 600
PAGE_MARKER_PREFIX = "[[PAGE:"
PAGE_MARKER_SUFFIX = "]]"


def normalize_extracted_text(text):
    if not text:
        return ""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def format_page_marker(page_number):
    return f"{PAGE_MARKER_PREFIX}{page_number}{PAGE_MARKER_SUFFIX}"


def _extract_pages(reader, max_pages=MAX_INDEX_PAGES):
    """Extract text one page at a time to limit peak memory."""
    chunks = []
    page_count = min(len(reader.pages), max_pages)
    for index in range(page_count):
        try:
            page_text = reader.pages[index].extract_text() or ""
            if page_text.strip():
                chunks.append(f"{format_page_marker(index + 1)}\n{page_text}")
        except Exception:
            continue
        if index % GC_EVERY_N_PAGES == 0:
            gc.collect()
    result = normalize_extracted_text("\n\n".join(chunks))
    del chunks
    gc.collect()
    return result


def _extract_with_pypdf(source, max_pages=MAX_INDEX_PAGES, strict=False):
    try:
        from pypdf import PdfReader

        reader = PdfReader(source, strict=strict)
        return _extract_pages(reader, max_pages=max_pages)
    except Exception:
        return ""


def extract_pdf_text(pdf_path, max_pages=MAX_INDEX_PAGES):
    """Extract plain text page by page from a PDF file path."""
    if not pdf_path or not pdf_path.lower().endswith(".pdf"):
        return ""
    try:
        text = _extract_with_pypdf(pdf_path, max_pages=max_pages, strict=False)
        if text:
            return text
        return _extract_with_pypdf(pdf_path, max_pages=max_pages, strict=True)
    except Exception:
        return ""


def extract_pdf_bytes(data, max_pages=MAX_INDEX_PAGES):
    """Extract text from PDF bytes page by page."""
    if not data or not data.startswith(b"%PDF"):
        return ""
    text = _extract_with_pypdf(io.BytesIO(data), max_pages=max_pages, strict=False)
    if text:
        return text
    return _extract_with_pypdf(io.BytesIO(data), max_pages=max_pages, strict=True)


def extract_pdf_text_isolated(pdf_path, max_pages=MAX_INDEX_PAGES):
    """
    Run extraction in a subprocess so OOM during PyPDF parsing
    does not take down the web worker.
    """
    if not pdf_path or not pdf_path.lower().endswith(".pdf"):
        return ""

    worker = """
import sys
from amm_pdf import extract_pdf_text, MAX_INDEX_PAGES

pdf_path = sys.argv[1]
max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else MAX_INDEX_PAGES
output_path = sys.argv[3]
text = extract_pdf_text(pdf_path, max_pages=max_pages)
with open(output_path, "w", encoding="utf-8") as handle:
    handle.write(text)
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as handle:
        output_path = handle.name

    try:
        result = subprocess.run(
            [sys.executable, "-c", worker, pdf_path, str(max_pages), output_path],
            capture_output=True,
            text=True,
            timeout=EXTRACTION_TIMEOUT_SECONDS,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(stderr or "PDF extraction subprocess failed")

        with open(output_path, encoding="utf-8") as handle:
            return handle.read()
    finally:
        try:
            os.unlink(output_path)
        except OSError:
            pass
