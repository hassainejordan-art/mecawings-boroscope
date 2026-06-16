import os
import re
import sqlite3
import uuid
from datetime import datetime

from werkzeug.utils import secure_filename

from amm_pdf import extract_pdf_text

AMM_SUBDIR = "amm"
DB_FILENAME = "reports.db"
SNIPPET_MAX_LEN = 320
SNIPPET_CONTEXT = 140


def get_db_path(base_dir):
    return os.path.join(base_dir, "data", DB_FILENAME)


def get_connection(base_dir):
    path = get_db_path(base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_amm_root(base_dir):
    return os.path.join(base_dir, "static", AMM_SUBDIR)


def sanitize_path_part(value, fallback="UNKNOWN"):
    if not value or not str(value).strip():
        return fallback
    cleaned = re.sub(r"[^\w\-]", "_", str(value).strip())
    return cleaned[:60] or fallback


def _extract_ata_code(ata_chapter):
    text = (ata_chapter or "").strip()
    match = re.match(r"(\d{2}-\d{2})", text)
    return match.group(1) if match else sanitize_path_part(text, "00-00")


def build_amm_dir(base_dir, aircraft_type, engine_type, ata_chapter):
    aircraft = sanitize_path_part(aircraft_type, "AIRCRAFT")
    engine = sanitize_path_part(engine_type, "ENGINE")
    ata = sanitize_path_part(_extract_ata_code(ata_chapter), "00-00")
    return os.path.join(get_amm_root(base_dir), aircraft, engine, ata)


def _row_to_document(row, include_text=False, text_excerpt=None):
    doc = {
        "id": row["id"],
        "aircraft_type": row["aircraft_type"],
        "engine_type": row["engine_type"],
        "ata_chapter": row["ata_chapter"],
        "document_name": row["document_name"],
        "revision": row["revision"],
        "stored_filename": row["stored_filename"],
        "file_path": row["file_path"],
        "upload_date": row["upload_date"],
        "created_at": row["created_at"],
        "has_extracted_text": bool((row["extracted_text"] or "").strip()),
        "text_length": len(row["extracted_text"] or ""),
    }
    if include_text:
        doc["extracted_text"] = row["extracted_text"] or ""
    if text_excerpt:
        doc["text_excerpt"] = text_excerpt
    return doc


def _ensure_extracted_text_column(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(amm_documents)").fetchall()}
    if "extracted_text" not in columns:
        conn.execute("ALTER TABLE amm_documents ADD COLUMN extracted_text TEXT")


def init_amm_storage(base_dir):
    os.makedirs(get_amm_root(base_dir), exist_ok=True)
    with get_connection(base_dir) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS amm_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                aircraft_type TEXT NOT NULL,
                engine_type TEXT NOT NULL,
                ata_chapter TEXT NOT NULL,
                document_name TEXT NOT NULL,
                revision TEXT,
                stored_filename TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                upload_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                extracted_text TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_amm_aircraft ON amm_documents(aircraft_type);
            CREATE INDEX IF NOT EXISTS idx_amm_engine ON amm_documents(engine_type);
            CREATE INDEX IF NOT EXISTS idx_amm_ata ON amm_documents(ata_chapter);
            CREATE INDEX IF NOT EXISTS idx_amm_document_name ON amm_documents(document_name);
            CREATE INDEX IF NOT EXISTS idx_amm_upload_date ON amm_documents(upload_date);
            """
        )
        _ensure_extracted_text_column(conn)

    backfill_extracted_text(base_dir)


def _update_document_text(base_dir, doc_id, extracted_text):
    with get_connection(base_dir) as conn:
        conn.execute(
            "UPDATE amm_documents SET extracted_text = ? WHERE id = ?",
            (extracted_text, doc_id),
        )


def backfill_extracted_text(base_dir):
    with get_connection(base_dir) as conn:
        rows = conn.execute(
            """
            SELECT id, file_path, extracted_text
            FROM amm_documents
            WHERE extracted_text IS NULL OR TRIM(extracted_text) = ''
            """
        ).fetchall()

    for row in rows:
        absolute = row["file_path"]
        if not os.path.isabs(absolute):
            absolute = os.path.join(base_dir, absolute)
        if not os.path.exists(absolute):
            continue
        text = extract_pdf_text(absolute)
        if text:
            _update_document_text(base_dir, row["id"], text)


def save_amm_document(base_dir, aircraft_type, engine_type, ata_chapter,
                      document_name, revision, pdf_file):
    if not pdf_file or not pdf_file.filename:
        raise ValueError("PDF file is required")

    original = pdf_file.filename
    if not original.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are allowed")

    aircraft_type = (aircraft_type or "").strip()
    engine_type = (engine_type or "").strip()
    ata_chapter = (ata_chapter or "").strip()
    document_name = (document_name or "").strip()
    revision = (revision or "").strip()

    if not all([aircraft_type, engine_type, ata_chapter, document_name]):
        raise ValueError("Aircraft type, engine type, ATA chapter, and document name are required")

    amm_dir = build_amm_dir(base_dir, aircraft_type, engine_type, ata_chapter)
    os.makedirs(amm_dir, exist_ok=True)

    safe_base = secure_filename(original) or "document.pdf"
    if not safe_base.lower().endswith(".pdf"):
        safe_base = f"{safe_base}.pdf"

    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_base}"
    absolute_path = os.path.join(amm_dir, unique_name)
    pdf_file.save(absolute_path)

    extracted_text = extract_pdf_text(absolute_path)

    now = datetime.now()
    upload_date = now.strftime("%Y-%m-%d")
    created_at = now.isoformat()
    relative_path = os.path.relpath(absolute_path, base_dir)

    with get_connection(base_dir) as conn:
        cursor = conn.execute(
            """
            INSERT INTO amm_documents (
                aircraft_type, engine_type, ata_chapter, document_name, revision,
                stored_filename, file_path, upload_date, created_at, extracted_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aircraft_type, engine_type, ata_chapter, document_name, revision,
                unique_name, relative_path, upload_date, created_at, extracted_text,
            ),
        )
        doc_id = cursor.lastrowid
        row = conn.execute(
            "SELECT * FROM amm_documents WHERE id = ?",
            (doc_id,),
        ).fetchone()

    return _row_to_document(row)


def list_amm_documents(base_dir):
    with get_connection(base_dir) as conn:
        rows = conn.execute(
            """
            SELECT * FROM amm_documents
            ORDER BY upload_date DESC, created_at DESC
            """
        ).fetchall()
    return [_row_to_document(row) for row in rows]


def _split_text_chunks(text, chunk_size=900):
    if not text:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks = []
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            chunks.append(paragraph)
            continue
        for start in range(0, len(paragraph), chunk_size):
            chunks.append(paragraph[start:start + chunk_size])
    return chunks


def _search_terms(*values):
    terms = []
    for value in values:
        if not value:
            continue
        for token in re.split(r"[^\w\-]+", str(value).lower()):
            token = token.strip()
            if len(token) >= 2:
                terms.append(token)
    return list(dict.fromkeys(terms))


def extract_text_snippet(text, terms, max_len=SNIPPET_MAX_LEN):
    if not text or not terms:
        return ""
    lower = text.lower()
    best_index = -1
    best_score = 0
    for term in terms:
        index = lower.find(term)
        while index != -1:
            score = 1
            for other in terms:
                if other in lower[max(0, index - SNIPPET_CONTEXT):index + SNIPPET_CONTEXT]:
                    score += 1
            if score > best_score:
                best_score = score
                best_index = index
            index = lower.find(term, index + 1)
    if best_index == -1:
        return text[:max_len] + ("…" if len(text) > max_len else "")

    start = max(0, best_index - SNIPPET_CONTEXT)
    end = min(len(text), best_index + max_len)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def _score_chunk(chunk, terms):
    lower = chunk.lower()
    return sum(lower.count(term) for term in terms)


def search_amm_snippets(base_dir, query="", engine_type="", ata="", inspected_area="", limit=5):
    terms = _search_terms(query, inspected_area, ata)
    combined_keyword = " ".join(part for part in [query, inspected_area] if part).strip()
    documents = search_amm_documents(
        base_dir,
        keyword=combined_keyword or query,
        engine_type=engine_type,
        ata_chapter=ata,
        amm_reference=query,
        include_text=True,
    )

    ranked = []
    for doc in documents:
        text = doc.get("extracted_text") or ""
        if not text:
            continue
        for chunk in _split_text_chunks(text):
            score = _score_chunk(chunk, terms) if terms else 1
            if terms and score == 0:
                continue
            ranked.append({
                "document_id": doc["id"],
                "document_name": doc["document_name"],
                "aircraft_type": doc["aircraft_type"],
                "engine_type": doc["engine_type"],
                "ata_chapter": doc["ata_chapter"],
                "revision": doc.get("revision") or "",
                "snippet": chunk[:SNIPPET_MAX_LEN] + ("…" if len(chunk) > SNIPPET_MAX_LEN else ""),
                "score": score,
            })

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:limit]


def search_amm_documents(base_dir, keyword="", engine_type="", ata_chapter="",
                         amm_reference="", aircraft_type="", document_name="",
                         revision="", include_text=False):
    query = """
        SELECT * FROM amm_documents
        WHERE (? = '' OR LOWER(COALESCE(aircraft_type, '')) LIKE '%' || LOWER(?) || '%')
          AND (? = '' OR LOWER(COALESCE(engine_type, '')) LIKE '%' || LOWER(?) || '%')
          AND (? = '' OR LOWER(COALESCE(ata_chapter, '')) LIKE '%' || LOWER(?) || '%')
          AND (? = '' OR LOWER(COALESCE(document_name, '')) LIKE '%' || LOWER(?) || '%')
          AND (? = '' OR LOWER(COALESCE(revision, '')) LIKE '%' || LOWER(?) || '%')
          AND (
                ? = ''
                OR LOWER(COALESCE(document_name, '')) LIKE '%' || LOWER(?) || '%'
                OR LOWER(COALESCE(revision, '')) LIKE '%' || LOWER(?) || '%'
                OR LOWER(COALESCE(ata_chapter, '')) LIKE '%' || LOWER(?) || '%'
          )
          AND (
                ? = ''
                OR LOWER(COALESCE(extracted_text, '')) LIKE '%' || LOWER(?) || '%'
                OR LOWER(COALESCE(document_name, '')) LIKE '%' || LOWER(?) || '%'
                OR LOWER(COALESCE(ata_chapter, '')) LIKE '%' || LOWER(?) || '%'
                OR LOWER(COALESCE(engine_type, '')) LIKE '%' || LOWER(?) || '%'
                OR LOWER(COALESCE(revision, '')) LIKE '%' || LOWER(?) || '%'
          )
        ORDER BY upload_date DESC, created_at DESC
    """
    params = (
        aircraft_type, aircraft_type,
        engine_type, engine_type,
        ata_chapter, ata_chapter,
        document_name, document_name,
        revision, revision,
        amm_reference, amm_reference, amm_reference, amm_reference,
        keyword, keyword, keyword, keyword, keyword, keyword,
    )
    terms = _search_terms(keyword, amm_reference)

    with get_connection(base_dir) as conn:
        rows = conn.execute(query, params).fetchall()

    results = []
    for row in rows:
        excerpt = None
        if keyword or amm_reference:
            excerpt = extract_text_snippet(row["extracted_text"] or "", terms)
        results.append(_row_to_document(row, include_text=include_text, text_excerpt=excerpt))
    return results


def get_amm_document(base_dir, doc_id, include_text=False):
    with get_connection(base_dir) as conn:
        row = conn.execute(
            "SELECT * FROM amm_documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
    if not row:
        return None
    return _row_to_document(row, include_text=include_text)


def resolve_amm_file_path(base_dir, document):
    if not document:
        return None
    file_path = document.get("file_path")
    if not file_path:
        return None
    absolute = file_path if os.path.isabs(file_path) else os.path.join(base_dir, file_path)
    return absolute if os.path.exists(absolute) else None


def format_amm_reference_label(document, snippet=None):
    if not document:
        return ""
    parts = [
        document.get("document_name", ""),
        document.get("ata_chapter", ""),
    ]
    if document.get("revision"):
        parts.append(f"Rev {document['revision']}")
    label = " — ".join(p for p in parts if p)
    if snippet:
        label = f"{label}\n{snippet.strip()}"
    return label


def build_maintenance_data_reference(document, snippet=None):
    return format_amm_reference_label(document, snippet=snippet)
