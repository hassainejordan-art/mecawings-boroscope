import re


def normalize_extracted_text(text):
    if not text:
        return ""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_text(pdf_path):
    """Extract plain text from a PDF file. Returns empty string on failure."""
    if not pdf_path:
        return ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(pdf_path)
        parts = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                parts.append(page_text)
        return normalize_extracted_text("\n\n".join(parts))
    except Exception:
        return ""
