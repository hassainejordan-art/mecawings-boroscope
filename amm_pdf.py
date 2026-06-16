import gc
import io
import os
import re
import subprocess
import sys
import tempfile

MAX_INDEX_PAGES = 300
INDEX_BATCH_SIZE = 25
GC_EVERY_N_PAGES = 10
EXTRACTION_TIMEOUT_SECONDS = 600
BATCH_TIMEOUT_SECONDS = 120
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


def get_pdf_page_count(pdf_path):
    """Return total page count for a PDF file."""
    if not pdf_path or not pdf_path.lower().endswith(".pdf"):
        return 0
    try:
        from pypdf import PdfReader

        reader = PdfReader(pdf_path, strict=False)
        return len(reader.pages)
    except Exception:
        try:
            from pypdf import PdfReader

            reader = PdfReader(pdf_path, strict=True)
            return len(reader.pages)
        except Exception:
            return 0


def extract_pdf_page_range(pdf_path, start_page, end_page, strict=False):
    """Extract text for pages [start_page, end_page) using 0-based indices."""
    if not pdf_path or start_page >= end_page:
        return ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(pdf_path, strict=strict)
        chunks = []
        upper = min(end_page, len(reader.pages))
        for index in range(start_page, upper):
            try:
                page_text = reader.pages[index].extract_text() or ""
                if page_text.strip():
                    chunks.append(f"{format_page_marker(index + 1)}\n{page_text}")
            except Exception:
                continue
            if (index - start_page) % GC_EVERY_N_PAGES == 0:
                gc.collect()
        return normalize_extracted_text("\n\n".join(chunks))
    except Exception:
        return ""


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


def _run_subprocess_worker(worker, args, timeout):
    result = subprocess.run(
        [sys.executable, "-c", worker, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(stderr or "PDF extraction subprocess failed")
    return result


def _extract_page_range_isolated(pdf_path, start_page, end_page):
    worker = """
import sys
from amm_pdf import extract_pdf_page_range

pdf_path = sys.argv[1]
start_page = int(sys.argv[2])
end_page = int(sys.argv[3])
output_path = sys.argv[4]
text = extract_pdf_page_range(pdf_path, start_page, end_page)
with open(output_path, "w", encoding="utf-8") as handle:
    handle.write(text)
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as handle:
        output_path = handle.name
    try:
        _run_subprocess_worker(
            worker,
            [pdf_path, str(start_page), str(end_page), output_path],
            BATCH_TIMEOUT_SECONDS,
        )
        with open(output_path, encoding="utf-8") as handle:
            return handle.read()
    finally:
        try:
            os.unlink(output_path)
        except OSError:
            pass


def extract_pdf_text_isolated(pdf_path, max_pages=MAX_INDEX_PAGES, batch_size=INDEX_BATCH_SIZE):
    """
    Run extraction in subprocess batches so large PDFs do not OOM the web worker.
    """
    if not pdf_path or not pdf_path.lower().endswith(".pdf"):
        return ""

    total_pages = get_pdf_page_count(pdf_path)
    if total_pages <= 0:
        return ""

    pages_to_extract = min(total_pages, max_pages)
    parts = []

    for start in range(0, pages_to_extract, batch_size):
        end = min(start + batch_size, pages_to_extract)
        batch_text = _extract_page_range_isolated(pdf_path, start, end)
        if batch_text:
            parts.append(batch_text)
        gc.collect()

    return normalize_extracted_text("\n\n".join(parts))
