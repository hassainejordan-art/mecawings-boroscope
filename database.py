import json
import os
import sqlite3
from datetime import datetime

from storage_config import get_db_path as persistent_db_path

COLUMN_FIELDS = frozenset({
    "report_number",
    "folder_name",
    "customer",
    "aircraft_type",
    "registration",
    "msn",
    "engine_type",
    "engine_sn",
    "date",
    "inspector",
    "pdf_path",
    "created_at",
    "updated_at",
})


def get_db_path(base_dir):
    return persistent_db_path(base_dir)


def get_connection(base_dir):
    path = get_db_path(base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(base_dir):
    with get_connection(base_dir) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_number TEXT NOT NULL UNIQUE,
                folder_name TEXT NOT NULL UNIQUE,
                customer TEXT,
                aircraft_type TEXT,
                registration TEXT,
                msn TEXT,
                engine_type TEXT,
                engine_sn TEXT,
                date TEXT,
                inspector TEXT,
                pdf_path TEXT,
                created_at TEXT,
                updated_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_reports_engine_sn ON reports(engine_sn);
            CREATE INDEX IF NOT EXISTS idx_reports_registration ON reports(registration);
            CREATE INDEX IF NOT EXISTS idx_reports_msn ON reports(msn);
            CREATE INDEX IF NOT EXISTS idx_reports_report_number ON reports(report_number);
            CREATE INDEX IF NOT EXISTS idx_reports_updated_at ON reports(updated_at);
            """
        )


def _metadata_json_from_dict(metadata):
    extra = {}
    for key, value in metadata.items():
        if key in COLUMN_FIELDS:
            continue
        if key == "aircraft":
            continue
        extra[key] = value
    return json.dumps(extra, ensure_ascii=False)


def _row_to_metadata(row):
    meta = json.loads(row["metadata_json"] or "{}")
    meta.update({
        "id": meta.get("id") or row["report_number"],
        "report_number": row["report_number"],
        "folder_name": row["folder_name"],
        "customer": row["customer"],
        "aircraft": row["aircraft_type"],
        "aircraft_type": row["aircraft_type"],
        "registration": row["registration"],
        "msn": row["msn"],
        "engine_type": row["engine_type"],
        "engine_sn": row["engine_sn"],
        "date": row["date"],
        "inspector": row["inspector"],
        "pdf_path": row["pdf_path"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    })
    return meta


def _normalize_metadata(metadata, pdf_path=None):
    now = datetime.now().isoformat()
    report_number = metadata.get("report_number") or metadata.get("id")
    folder_name = metadata.get("folder_name") or report_number

    row = {
        "report_number": report_number,
        "folder_name": folder_name,
        "customer": metadata.get("customer"),
        "aircraft_type": metadata.get("aircraft_type") or metadata.get("aircraft"),
        "registration": metadata.get("registration"),
        "msn": metadata.get("msn"),
        "engine_type": metadata.get("engine_type"),
        "engine_sn": metadata.get("engine_sn"),
        "date": metadata.get("date"),
        "inspector": metadata.get("inspector"),
        "pdf_path": pdf_path or metadata.get("pdf_path"),
        "created_at": metadata.get("created_at") or now,
        "updated_at": metadata.get("updated_at") or now,
    }
    return row, _metadata_json_from_dict(metadata)


def upsert_report(base_dir, metadata, pdf_path=None):
    row, metadata_json = _normalize_metadata(metadata, pdf_path=pdf_path)
    if not row["report_number"] or not row["folder_name"]:
        raise ValueError("report_number and folder_name are required")

    row["updated_at"] = datetime.now().isoformat()

    with get_connection(base_dir) as conn:
        conn.execute(
            """
            INSERT INTO reports (
                report_number, folder_name, customer, aircraft_type, registration,
                msn, engine_type, engine_sn, date, inspector, pdf_path,
                created_at, updated_at, metadata_json
            ) VALUES (
                :report_number, :folder_name, :customer, :aircraft_type, :registration,
                :msn, :engine_type, :engine_sn, :date, :inspector, :pdf_path,
                :created_at, :updated_at, :metadata_json
            )
            ON CONFLICT(folder_name) DO UPDATE SET
                report_number = excluded.report_number,
                customer = excluded.customer,
                aircraft_type = excluded.aircraft_type,
                registration = excluded.registration,
                msn = excluded.msn,
                engine_type = excluded.engine_type,
                engine_sn = excluded.engine_sn,
                date = excluded.date,
                inspector = excluded.inspector,
                pdf_path = excluded.pdf_path,
                updated_at = excluded.updated_at,
                metadata_json = excluded.metadata_json
            """,
            {**row, "metadata_json": metadata_json},
        )
        saved = conn.execute(
            "SELECT * FROM reports WHERE folder_name = ?",
            (row["folder_name"],),
        ).fetchone()

    return _row_to_metadata(saved)


def get_report_by_key(base_dir, key):
    if not key:
        return None

    safe_key = os.path.basename(key)
    with get_connection(base_dir) as conn:
        row = conn.execute(
            """
            SELECT * FROM reports
            WHERE folder_name = ?
               OR report_number = ?
               OR json_extract(metadata_json, '$.id') = ?
            LIMIT 1
            """,
            (safe_key, safe_key, safe_key),
        ).fetchone()

    return _row_to_metadata(row) if row else None


def list_all_reports(base_dir):
    with get_connection(base_dir) as conn:
        rows = conn.execute(
            """
            SELECT * FROM reports
            ORDER BY COALESCE(updated_at, created_at, '') DESC
            """
        ).fetchall()
    return [_row_to_metadata(row) for row in rows]


def search_reports(base_dir, engine_sn="", registration="", msn="", report_number=""):
    query = """
        SELECT * FROM reports
        WHERE (? = '' OR LOWER(COALESCE(engine_sn, '')) LIKE '%' || LOWER(?) || '%')
          AND (? = '' OR LOWER(COALESCE(registration, '')) LIKE '%' || LOWER(?) || '%')
          AND (? = '' OR LOWER(COALESCE(msn, '')) LIKE '%' || LOWER(?) || '%')
          AND (? = '' OR LOWER(COALESCE(report_number, '')) LIKE '%' || LOWER(?) || '%')
        ORDER BY COALESCE(updated_at, created_at, '') DESC
    """
    params = (
        engine_sn, engine_sn,
        registration, registration,
        msn, msn,
        report_number, report_number,
    )

    with get_connection(base_dir) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_metadata(row) for row in rows]


def report_exists(base_dir, folder_name):
    with get_connection(base_dir) as conn:
        row = conn.execute(
            "SELECT 1 FROM reports WHERE folder_name = ? LIMIT 1",
            (folder_name,),
        ).fetchone()
    return row is not None
