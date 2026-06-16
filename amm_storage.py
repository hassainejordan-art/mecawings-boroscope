import os
import re
import sqlite3
import uuid
from datetime import datetime

from werkzeug.utils import secure_filename

AMM_SUBDIR = "amm"
DB_FILENAME = "reports.db"


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
    """Return the numeric ATA prefix (e.g. '72-00') from a chapter label."""
    text = (ata_chapter or "").strip()
    match = re.match(r"(\d{2}-\d{2})", text)
    return match.group(1) if match else sanitize_path_part(text, "00-00")


def build_amm_dir(base_dir, aircraft_type, engine_type, ata_chapter):
    aircraft = sanitize_path_part(aircraft_type, "AIRCRAFT")
    engine = sanitize_path_part(engine_type, "ENGINE")
    ata = sanitize_path_part(_extract_ata_code(ata_chapter), "00-00")
    return os.path.join(get_amm_root(base_dir), aircraft, engine, ata)


def _row_to_document(row):
    return {
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
    }


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
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_amm_aircraft ON amm_documents(aircraft_type);
            CREATE INDEX IF NOT EXISTS idx_amm_engine ON amm_documents(engine_type);
            CREATE INDEX IF NOT EXISTS idx_amm_ata ON amm_documents(ata_chapter);
            CREATE INDEX IF NOT EXISTS idx_amm_document_name ON amm_documents(document_name);
            CREATE INDEX IF NOT EXISTS idx_amm_upload_date ON amm_documents(upload_date);
            """
        )


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

    now = datetime.now()
    upload_date = now.strftime("%Y-%m-%d")
    created_at = now.isoformat()
    relative_path = os.path.relpath(absolute_path, base_dir)

    with get_connection(base_dir) as conn:
        cursor = conn.execute(
            """
            INSERT INTO amm_documents (
                aircraft_type, engine_type, ata_chapter, document_name, revision,
                stored_filename, file_path, upload_date, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aircraft_type, engine_type, ata_chapter, document_name, revision,
                unique_name, relative_path, upload_date, created_at,
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


def search_amm_documents(base_dir, aircraft_type="", engine_type="",
                         ata_chapter="", document_name="", revision=""):
    query = """
        SELECT * FROM amm_documents
        WHERE (? = '' OR LOWER(COALESCE(aircraft_type, '')) LIKE '%' || LOWER(?) || '%')
          AND (? = '' OR LOWER(COALESCE(engine_type, '')) LIKE '%' || LOWER(?) || '%')
          AND (? = '' OR LOWER(COALESCE(ata_chapter, '')) LIKE '%' || LOWER(?) || '%')
          AND (? = '' OR LOWER(COALESCE(document_name, '')) LIKE '%' || LOWER(?) || '%')
          AND (? = '' OR LOWER(COALESCE(revision, '')) LIKE '%' || LOWER(?) || '%')
        ORDER BY upload_date DESC, created_at DESC
    """
    params = (
        aircraft_type, aircraft_type,
        engine_type, engine_type,
        ata_chapter, ata_chapter,
        document_name, document_name,
        revision, revision,
    )
    with get_connection(base_dir) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_document(row) for row in rows]


def get_amm_document(base_dir, doc_id):
    with get_connection(base_dir) as conn:
        row = conn.execute(
            "SELECT * FROM amm_documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
    return _row_to_document(row) if row else None


def resolve_amm_file_path(base_dir, document):
    if not document:
        return None
    file_path = document.get("file_path")
    if not file_path:
        return None
    absolute = file_path if os.path.isabs(file_path) else os.path.join(base_dir, file_path)
    return absolute if os.path.exists(absolute) else None


def format_amm_reference_label(document):
    if not document:
        return ""
    parts = [
        document.get("document_name", ""),
        f"ATA {document.get('ata_chapter', '')}",
    ]
    if document.get("revision"):
        parts.append(f"Rev {document['revision']}")
    return " — ".join(p for p in parts if p)
