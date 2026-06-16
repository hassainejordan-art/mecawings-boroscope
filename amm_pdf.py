import io
import re

MAX_INDEX_PAGES = 500


def normalize_extracted_text(text):
    if not text:
        return ""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pages(reader, max_pages=MAX_INDEX_PAGES):
    parts = []
    for index, page in enumerate(reader.pages):
        if index >= max_pages:
            break
        page_text = page.extract_text() or ""
        if page_text.strip():
            parts.append(page_text)
    return normalize_extracted_text("\n\n".join(parts))


def _extract_with_pypdf(source, max_pages=MAX_INDEX_PAGES, strict=False):
    try:
        from pypdf import PdfReader

        reader = PdfReader(source, strict=strict)
        return _extract_pages(reader, max_pages=max_pages)
    except Exception:
        return ""


def extract_pdf_text(pdf_path, max_pages=MAX_INDEX_PAGES):
    """Extract plain text page by page from a PDF file."""
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
