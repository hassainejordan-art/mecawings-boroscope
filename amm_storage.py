import os
import re
import shutil
import sqlite3
import uuid
from datetime import datetime

from werkzeug.utils import secure_filename

from amm_pdf import MAX_INDEX_PAGES, extract_pdf_text_isolated
from storage_config import get_amm_files_root, get_db_path

SNIPPET_MAX_LEN = 320
SNIPPET_CONTEXT = 140

INDEX_STATUS_UPLOADED = "uploaded"
INDEX_STATUS_INDEXING = "indexing"
INDEX_STATUS_INDEXED = "indexed"
INDEX_STATUS_FAILED = "indexing_failed"

INDEXING_FAILED_USER_MESSAGE = (
    "PDF uploaded but indexing failed. Try a smaller ATA section PDF."
)


def get_connection(base_dir):
    path = get_db_path(base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


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
    return os.path.join(get_amm_files_root(base_dir), aircraft, engine, ata)


def build_stored_amm_reference(document_name, ata_chapter, revision=""):
    parts = [(document_name or "").strip(), (ata_chapter or "").strip()]
    rev = (revision or "").strip()
    if rev:
        if not rev.lower().startswith("rev"):
            rev = f"Rev {rev}"
        parts.append(rev)
    return " — ".join(p for p in parts if p)


def _absolute_file_path(base_dir, file_path):
    if not file_path:
        return None
    if os.path.isabs(file_path):
        return file_path
    return os.path.join(base_dir, file_path)


def _legacy_static_amm_root(base_dir):
    return os.path.join(base_dir, "static", "amm")


def _resolve_index_status(row):
    if "index_status" in row.keys() and row["index_status"]:
        return row["index_status"]
    if row["indexed"] if "indexed" in row.keys() else False:
        return INDEX_STATUS_INDEXED
    index_error = (row["index_error"] or "").strip() if "index_error" in row.keys() else ""
    if index_error:
        return INDEX_STATUS_FAILED
    return INDEX_STATUS_UPLOADED


def _index_status_label(status):
    return {
        INDEX_STATUS_UPLOADED: "Uploaded",
        INDEX_STATUS_INDEXING: "Indexing",
        INDEX_STATUS_INDEXED: "Indexed",
        INDEX_STATUS_FAILED: "Indexing failed",
    }.get(status, status)


def _row_to_document(base_dir, row, include_text=False, text_excerpt=None):
    extracted = row["extracted_text"] or ""
    pdf_path = resolve_amm_file_path(base_dir, {"file_path": row["file_path"]})
    amm_reference = row["amm_reference"] if "amm_reference" in row.keys() else ""
    if not amm_reference:
        amm_reference = build_stored_amm_reference(
            row["document_name"], row["ata_chapter"], row["revision"]
        )

    index_status = _resolve_index_status(row)
    index_error = (row["index_error"] or "").strip() if "index_error" in row.keys() else ""
    indexed = index_status == INDEX_STATUS_INDEXED

    doc = {
        "id": row["id"],
        "aircraft_type": row["aircraft_type"],
        "engine_type": row["engine_type"],
        "ata_chapter": row["ata_chapter"],
        "document_name": row["document_name"],
        "revision": row["revision"],
        "amm_reference": amm_reference,
        "stored_filename": row["stored_filename"],
        "file_path": row["file_path"],
        "upload_date": row["upload_date"],
        "created_at": row["created_at"],
        "index_status": index_status,
        "index_status_label": _index_status_label(index_status),
        "indexed": indexed,
        "index_pending": index_status in (INDEX_STATUS_UPLOADED, INDEX_STATUS_INDEXING),
        "index_failed": index_status == INDEX_STATUS_FAILED,
        "index_error": index_error or None,
        "indexing_failed_message": (
            INDEXING_FAILED_USER_MESSAGE if index_status == INDEX_STATUS_FAILED else None
        ),
        "has_extracted_text": bool(extracted.strip()),
        "text_length": len(extracted),
        "pdf_available": pdf_path is not None,
        "search_available": indexed and bool(extracted.strip()),
    }
    if include_text:
        doc["extracted_text"] = extracted
    if text_excerpt:
        doc["text_excerpt"] = text_excerpt
    return doc


def _ensure_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS amm_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aircraft_type TEXT NOT NULL,
            engine_type TEXT NOT NULL,
            ata_chapter TEXT NOT NULL,
            document_name TEXT NOT NULL,
            revision TEXT,
            stored_filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            upload_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            extracted_text TEXT,
            amm_reference TEXT,
            indexed INTEGER NOT NULL DEFAULT 0,
            index_error TEXT,
            index_status TEXT NOT NULL DEFAULT 'uploaded'
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(amm_documents)").fetchall()}
    if "extracted_text" not in columns:
        conn.execute("ALTER TABLE amm_documents ADD COLUMN extracted_text TEXT")
    if "amm_reference" not in columns:
        conn.execute("ALTER TABLE amm_documents ADD COLUMN amm_reference TEXT")
    if "indexed" not in columns:
        conn.execute("ALTER TABLE amm_documents ADD COLUMN indexed INTEGER NOT NULL DEFAULT 0")
    if "index_error" not in columns:
        conn.execute("ALTER TABLE amm_documents ADD COLUMN index_error TEXT")
    if "index_status" not in columns:
        conn.execute(
            "ALTER TABLE amm_documents ADD COLUMN index_status TEXT NOT NULL DEFAULT 'uploaded'"
        )

    conn.execute(
        """
        UPDATE amm_documents
        SET indexed = 1,
            index_status = ?
        WHERE indexed = 1
           OR TRIM(COALESCE(extracted_text, '')) != ''
        """,
        (INDEX_STATUS_INDEXED,),
    )
    conn.execute(
        """
        UPDATE amm_documents
        SET index_status = ?
        WHERE (index_status IS NULL OR index_status = '' OR index_status = 'uploaded')
          AND indexed = 0
          AND TRIM(COALESCE(index_error, '')) != ''
        """,
        (INDEX_STATUS_FAILED,),
    )
    conn.execute(
        """
        UPDATE amm_documents
        SET index_status = ?
        WHERE index_status IS NULL OR TRIM(index_status) = ''
        """,
        (INDEX_STATUS_UPLOADED,),
    )

    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_amm_aircraft ON amm_documents(aircraft_type);
        CREATE INDEX IF NOT EXISTS idx_amm_engine ON amm_documents(engine_type);
        CREATE INDEX IF NOT EXISTS idx_amm_ata ON amm_documents(ata_chapter);
        CREATE INDEX IF NOT EXISTS idx_amm_document_name ON amm_documents(document_name);
        CREATE INDEX IF NOT EXISTS idx_amm_upload_date ON amm_documents(upload_date);
        CREATE INDEX IF NOT EXISTS idx_amm_reference ON amm_documents(amm_reference);
        """
    )

    rows = conn.execute(
        """
        SELECT id, document_name, ata_chapter, revision
        FROM amm_documents
        WHERE amm_reference IS NULL OR TRIM(amm_reference) = ''
        """
    ).fetchall()
    for row in rows:
        conn.execute(
            "UPDATE amm_documents SET amm_reference = ? WHERE id = ?",
            (
                build_stored_amm_reference(
                    row["document_name"], row["ata_chapter"], row["revision"]
                ),
                row["id"],
            ),
        )


def _migrate_file_to_persistent(base_dir, row):
    """Copy legacy/ephemeral PDF paths into persistent amm_files storage."""
    current_path = resolve_amm_file_path(base_dir, {"file_path": row["file_path"]})
    if current_path:
        return row["file_path"]

    candidates = []
    stored = row["stored_filename"]
    legacy_root = _legacy_static_amm_root(base_dir)
    if stored:
        for root, _, files in os.walk(legacy_root):
            if stored in files:
                candidates.append(os.path.join(root, stored))

    old_absolute = _absolute_file_path(base_dir, row["file_path"])
    if old_absolute and os.path.exists(old_absolute):
        candidates.insert(0, old_absolute)

    if not candidates:
        return row["file_path"]

    source = candidates[0]
    dest_dir = build_amm_dir(
        base_dir,
        row["aircraft_type"],
        row["engine_type"],
        row["ata_chapter"],
    )
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, os.path.basename(source))
    if not os.path.exists(dest_path):
        shutil.copy2(source, dest_path)

    data_dir = get_amm_files_root(base_dir)
    if dest_path.startswith(data_dir):
        return os.path.relpath(dest_path, base_dir)
    return dest_path


def _migrate_amm_file_locations(base_dir):
    with get_connection(base_dir) as conn:
        rows = conn.execute("SELECT * FROM amm_documents").fetchall()
        for row in rows:
            new_path = _migrate_file_to_persistent(base_dir, row)
            if new_path != row["file_path"]:
                conn.execute(
                    "UPDATE amm_documents SET file_path = ? WHERE id = ?",
                    (new_path, row["id"]),
                )


def _original_filename_from_stored(stored_filename):
    match = re.match(r"^[0-9a-f]{8}_(.+)$", stored_filename, re.I)
    return match.group(1) if match else stored_filename


def _parse_amm_path_metadata(base_dir, absolute_path):
    """Read aircraft, engine, and ATA folder names from an on-disk AMM path."""
    for root in (get_amm_files_root(base_dir), _legacy_static_amm_root(base_dir)):
        prefix = root + os.sep
        if not absolute_path.startswith(prefix):
            continue
        rel_parts = os.path.relpath(absolute_path, root).split(os.sep)
        if len(rel_parts) >= 4:
            aircraft, engine, ata_code = rel_parts[0], rel_parts[1], rel_parts[2]
            ata_chapter = ata_code.replace("_", "-")
            if re.match(r"\d{2}-\d{2}", ata_chapter):
                return aircraft, engine, ata_chapter
            return aircraft, engine, f"{ata_chapter} — General"
    return None, None, None


def _register_existing_amm_pdf(base_dir, absolute_path, aircraft_type, engine_type,
                               ata_chapter, document_name, revision=""):
    stored_filename = os.path.basename(absolute_path)
    amm_reference = build_stored_amm_reference(document_name, ata_chapter, revision)

    data_root = get_amm_files_root(base_dir)
    if absolute_path.startswith(data_root):
        relative_path = os.path.relpath(absolute_path, base_dir)
    elif absolute_path.startswith(base_dir):
        relative_path = os.path.relpath(absolute_path, base_dir)
    else:
        relative_path = absolute_path

    file_mtime = datetime.fromtimestamp(os.path.getmtime(absolute_path))
    upload_date = file_mtime.strftime("%Y-%m-%d")
    created_at = file_mtime.isoformat()

    with get_connection(base_dir) as conn:
        cursor = conn.execute(
            """
            INSERT INTO amm_documents (
                aircraft_type, engine_type, ata_chapter, document_name, revision,
                amm_reference, stored_filename, file_path, upload_date, created_at,
                extracted_text, indexed, index_error, index_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aircraft_type, engine_type, ata_chapter, document_name, revision,
                amm_reference, stored_filename, relative_path, upload_date, created_at,
                None, 0, None, INDEX_STATUS_UPLOADED,
            ),
        )
        doc_id = cursor.lastrowid
        row = conn.execute(
            "SELECT * FROM amm_documents WHERE id = ?",
            (doc_id,),
        ).fetchone()

    return _row_to_document(base_dir, row)


def import_orphan_amm_pdfs(base_dir):
    """
    Register PDFs saved on disk that are missing from amm_documents.
    This recovers uploads that failed after the file was written.
    """
    with get_connection(base_dir) as conn:
        known = {
            row[0]
            for row in conn.execute("SELECT stored_filename FROM amm_documents").fetchall()
        }

    imported = []
    scan_roots = [get_amm_files_root(base_dir), _legacy_static_amm_root(base_dir)]

    for root in scan_roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            for filename in files:
                if not filename.lower().endswith(".pdf") or filename in known:
                    continue

                absolute_path = os.path.join(dirpath, filename)
                aircraft, engine, ata = _parse_amm_path_metadata(base_dir, absolute_path)
                if not all([aircraft, engine, ata]):
                    continue

                original = _original_filename_from_stored(filename)
                document_name = os.path.splitext(original)[0].replace("_", " ").strip()
                if not document_name:
                    document_name = original

                doc = _register_existing_amm_pdf(
                    base_dir,
                    absolute_path,
                    aircraft_type=aircraft.replace("_", "-"),
                    engine_type=engine.replace("_", "-"),
                    ata_chapter=ata,
                    document_name=document_name,
                )
                imported.append(doc)
                known.add(filename)

    return imported


def init_amm_storage(base_dir):
    os.makedirs(get_amm_files_root(base_dir), exist_ok=True)
    with get_connection(base_dir) as conn:
        _ensure_schema(conn)
        conn.execute(
            """
            UPDATE amm_documents
            SET index_status = ?
            WHERE index_status = ?
            """,
            (INDEX_STATUS_UPLOADED, INDEX_STATUS_INDEXING),
        )
    _migrate_amm_file_locations(base_dir)
    import_orphan_amm_pdfs(base_dir)

    from amm_indexing import schedule_pending_amm_indexing

    schedule_pending_amm_indexing(base_dir)


def build_metadata_index_text(row):
    """Fallback index content when PDF text cannot be extracted."""
    parts = [
        row.get("document_name") if isinstance(row, dict) else row["document_name"],
        row.get("aircraft_type") if isinstance(row, dict) else row["aircraft_type"],
        row.get("engine_type") if isinstance(row, dict) else row["engine_type"],
        row.get("ata_chapter") if isinstance(row, dict) else row["ata_chapter"],
        row.get("amm_reference") if isinstance(row, dict) else row["amm_reference"],
        row.get("revision") if isinstance(row, dict) else row["revision"],
        row.get("stored_filename") if isinstance(row, dict) else row["stored_filename"],
    ]
    return normalize_index_text("\n".join(str(p).strip() for p in parts if p))


def normalize_index_text(text):
    return (text or "").strip()


def _extract_text_for_row(base_dir, row):
    """Extract PDF text page by page in an isolated subprocess."""
    document = dict(row)
    absolute = resolve_amm_file_path(base_dir, document)
    if not absolute:
        absolute = _absolute_file_path(base_dir, row["file_path"])

    if absolute and os.path.exists(absolute):
        return extract_pdf_text_isolated(absolute, max_pages=MAX_INDEX_PAGES)
    return ""


def _update_document_index(base_dir, doc_id, extracted_text, index_status, index_error=None):
    indexed = index_status == INDEX_STATUS_INDEXED
    with get_connection(base_dir) as conn:
        conn.execute(
            """
            UPDATE amm_documents
            SET extracted_text = ?, indexed = ?, index_error = ?, index_status = ?
            WHERE id = ?
            """,
            (extracted_text or None, 1 if indexed else 0, index_error, index_status, doc_id),
        )


def _set_index_status(base_dir, doc_id, index_status, index_error=None):
    indexed = index_status == INDEX_STATUS_INDEXED
    with get_connection(base_dir) as conn:
        conn.execute(
            """
            UPDATE amm_documents
            SET indexed = ?, index_error = ?, index_status = ?
            WHERE id = ?
            """,
            (1 if indexed else 0, index_error, index_status, doc_id),
        )


def list_unindexed_amm_document_ids(base_dir):
    with get_connection(base_dir) as conn:
        rows = conn.execute(
            """
            SELECT id FROM amm_documents
            WHERE index_status = ?
            ORDER BY created_at ASC
            """,
            (INDEX_STATUS_UPLOADED,),
        ).fetchall()
    return [row[0] for row in rows]


def mark_amm_indexing_failed(base_dir, doc_id, technical_error=None):
    _update_document_index(
        base_dir,
        doc_id,
        extracted_text=None,
        index_status=INDEX_STATUS_FAILED,
        index_error=INDEXING_FAILED_USER_MESSAGE,
    )


def extract_and_index_amm_document(base_dir, doc_id):
    """Extract PDF text page by page and update indexing status."""
    with get_connection(base_dir) as conn:
        row = conn.execute(
            "SELECT * FROM amm_documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
    if not row:
        return None
    if _resolve_index_status(row) == INDEX_STATUS_INDEXED:
        return get_amm_document(base_dir, doc_id)

    _set_index_status(base_dir, doc_id, INDEX_STATUS_INDEXING)

    try:
        extracted_text = _extract_text_for_row(base_dir, row)
        if extracted_text.strip():
            _update_document_index(
                base_dir,
                doc_id,
                extracted_text,
                INDEX_STATUS_INDEXED,
                index_error=None,
            )
        else:
            mark_amm_indexing_failed(base_dir, doc_id)
    except Exception:
        mark_amm_indexing_failed(base_dir, doc_id)

    return get_amm_document(base_dir, doc_id)


def backfill_extracted_text(base_dir):
    return reindex_all_amm_documents(base_dir, only_missing=True)


def reindex_all_amm_documents(base_dir, only_missing=False):
    """Schedule background indexing for AMM documents."""
    from amm_indexing import schedule_amm_indexing

    query = "SELECT id FROM amm_documents"
    params = ()
    if only_missing:
        query += " WHERE index_status = ?"
        params = (INDEX_STATUS_UPLOADED,)

    with get_connection(base_dir) as conn:
        rows = conn.execute(query, params).fetchall()

    for row in rows:
        schedule_amm_indexing(base_dir, row[0])

    return {
        "total": len(rows),
        "scheduled": len(rows),
    }


def index_amm_document(base_dir, doc_id):
    """Re-index a single AMM document by id."""
    return extract_and_index_amm_document(base_dir, doc_id)


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

    with open(absolute_path, "wb") as handle:
        shutil.copyfileobj(pdf_file.stream, handle)

    if not os.path.exists(absolute_path) or os.path.getsize(absolute_path) == 0:
        raise ValueError("Failed to save PDF file")

    amm_reference = build_stored_amm_reference(document_name, ata_chapter, revision)

    now = datetime.now()
    upload_date = now.strftime("%Y-%m-%d")
    created_at = now.isoformat()
    relative_path = os.path.relpath(absolute_path, base_dir)

    with get_connection(base_dir) as conn:
        cursor = conn.execute(
            """
            INSERT INTO amm_documents (
                aircraft_type, engine_type, ata_chapter, document_name, revision,
                amm_reference, stored_filename, file_path, upload_date, created_at,
                extracted_text, indexed, index_error, index_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aircraft_type, engine_type, ata_chapter, document_name, revision,
                amm_reference, unique_name, relative_path, upload_date, created_at,
                None, 0, None, INDEX_STATUS_UPLOADED,
            ),
        )
        doc_id = cursor.lastrowid
        row = conn.execute(
            "SELECT * FROM amm_documents WHERE id = ?",
            (doc_id,),
        ).fetchone()

    return _row_to_document(base_dir, row)


def list_amm_documents(base_dir):
    with get_connection(base_dir) as conn:
        rows = conn.execute(
            """
            SELECT * FROM amm_documents
            ORDER BY upload_date DESC, created_at DESC
            """
        ).fetchall()
    return [_row_to_document(base_dir, row) for row in rows]


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
                "amm_reference": doc.get("amm_reference", ""),
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
                OR LOWER(COALESCE(amm_reference, '')) LIKE '%' || LOWER(?) || '%'
                OR LOWER(COALESCE(document_name, '')) LIKE '%' || LOWER(?) || '%'
                OR LOWER(COALESCE(revision, '')) LIKE '%' || LOWER(?) || '%'
                OR LOWER(COALESCE(ata_chapter, '')) LIKE '%' || LOWER(?) || '%'
          )
          AND (
                ? = ''
                OR LOWER(COALESCE(extracted_text, '')) LIKE '%' || LOWER(?) || '%'
                OR LOWER(COALESCE(amm_reference, '')) LIKE '%' || LOWER(?) || '%'
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
        amm_reference, amm_reference, amm_reference, amm_reference, amm_reference,
        keyword, keyword, keyword, keyword, keyword, keyword, keyword,
    )
    terms = _search_terms(keyword, amm_reference)

    with get_connection(base_dir) as conn:
        rows = conn.execute(query, params).fetchall()

    results = []
    for row in rows:
        excerpt = None
        extracted = row["extracted_text"] or ""
        if keyword or amm_reference:
            excerpt = extract_text_snippet(extracted, terms)
        results.append(
            _row_to_document(base_dir, row, include_text=include_text, text_excerpt=excerpt)
        )
    return results


def get_amm_document(base_dir, doc_id, include_text=False):
    with get_connection(base_dir) as conn:
        row = conn.execute(
            "SELECT * FROM amm_documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
    if not row:
        return None
    return _row_to_document(base_dir, row, include_text=include_text)


def resolve_amm_file_path(base_dir, document):
    if not document:
        return None
    file_path = document.get("file_path")
    if not file_path:
        return None

    candidates = [
        file_path if os.path.isabs(file_path) else os.path.join(base_dir, file_path),
        _absolute_file_path(base_dir, file_path),
    ]
    stored = document.get("stored_filename")
    if stored:
        legacy_root = _legacy_static_amm_root(base_dir)
        for root, _, files in os.walk(legacy_root):
            if stored in files:
                candidates.append(os.path.join(root, stored))

    for absolute in candidates:
        if absolute and os.path.exists(absolute):
            return absolute
    return None


def format_amm_reference_label(document, snippet=None):
    if not document:
        return ""
    label = document.get("amm_reference") or build_stored_amm_reference(
        document.get("document_name", ""),
        document.get("ata_chapter", ""),
        document.get("revision", ""),
    )
    if snippet:
        label = f"{label}\n{snippet.strip()}"
    return label


def build_maintenance_data_reference(document, snippet=None):
    return format_amm_reference_label(document, snippet=snippet)
