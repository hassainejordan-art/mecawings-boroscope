import io
import re


def normalize_extracted_text(text):
    if not text:
        return ""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_with_pypdf(source, strict=False):
    try:
        from pypdf import PdfReader

        reader = PdfReader(source, strict=strict)
        parts = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                parts.append(page_text)
        return normalize_extracted_text("\n\n".join(parts))
    except Exception:
        return ""


def extract_pdf_bytes(data):
    """Extract text from PDF bytes."""
    if not data or not data.startswith(b"%PDF"):
        return ""
    text = _extract_with_pypdf(io.BytesIO(data), strict=False)
    if text:
        return text
    return _extract_with_pypdf(io.BytesIO(data), strict=True)


def extract_pdf_text(pdf_path):
    """Extract plain text from a PDF file. Returns empty string on failure."""
    if not pdf_path or not pdf_path.lower().endswith(".pdf"):
        return ""
    try:
        with open(pdf_path, "rb") as handle:
            data = handle.read()
    except OSError:
        return ""
    if not data.startswith(b"%PDF"):
        return ""
    return extract_pdf_bytes(data)
