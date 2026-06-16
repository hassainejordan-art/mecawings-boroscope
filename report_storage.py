import json
import os
import re

from database import (
    get_report_by_key,
    init_db,
    list_all_reports as db_list_all_reports,
    report_exists,
    search_reports as db_search_reports,
    upsert_report,
)
from report_numbering import report_number_from_folder_name

REPORTS_SUBDIR = "reports"


def sanitize_folder_part(value, fallback="UNKNOWN"):
    if not value or not str(value).strip():
        return fallback
    cleaned = re.sub(r"[^\w\-]", "_", str(value).strip().upper())
    return cleaned[:40] or fallback


def build_folder_name(report_number, registration, engine_sn):
    """Folder format: report_number + registration + engine serial number."""
    reg = sanitize_folder_part(registration, "NO-REG")
    eng = sanitize_folder_part(engine_sn, "NO-ENG")
    return f"{report_number}_{reg}_{eng}"


def get_reports_root(base_dir):
    return os.path.join(base_dir, "static", REPORTS_SUBDIR)


def get_report_dir(base_dir, folder_name):
    return os.path.join(get_reports_root(base_dir), folder_name)


def get_photos_dir(report_dir):
    return os.path.join(report_dir, "photos")


def metadata_path(report_dir):
    return os.path.join(report_dir, "metadata.json")


def pdf_filename_for(report_number):
    return f"borescope_report_{report_number}.pdf"


def _relative_pdf_path(base_dir, absolute_pdf_path):
    if not absolute_pdf_path:
        return None
    return os.path.relpath(absolute_pdf_path, base_dir)


def _absolute_pdf_path(base_dir, pdf_path):
    if not pdf_path:
        return None
    if os.path.isabs(pdf_path):
        return pdf_path if os.path.exists(pdf_path) else None
    absolute = os.path.join(base_dir, pdf_path)
    return absolute if os.path.exists(absolute) else None


def ensure_storage(base_dir):
    """Initialize SQLite and migrate legacy metadata.json files once."""
    init_db(base_dir)
    return migrate_existing_reports(base_dir)


def _load_legacy_metadata_json(report_dir):
    path = metadata_path(report_dir)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def migrate_existing_reports(base_dir):
    """Import reports from legacy metadata.json files into SQLite."""
    root = get_reports_root(base_dir)
    if not os.path.isdir(root):
        return 0

    migrated = 0
    for entry in os.listdir(root):
        folder = os.path.join(root, entry)
        if not os.path.isdir(folder):
            continue
        if report_exists(base_dir, entry):
            continue

        meta = _load_legacy_metadata_json(folder)
        if not meta:
            continue

        folder_name = meta.get("folder_name") or entry
        report_number = (
            meta.get("report_number")
            or report_number_from_folder_name(entry)
            or meta.get("id")
            or entry
        )
        meta["folder_name"] = folder_name
        meta["report_number"] = report_number

        pdf_path = get_pdf_path(folder, report_number)
        relative_pdf = _relative_pdf_path(base_dir, pdf_path)

        upsert_report(base_dir, meta, pdf_path=relative_pdf)
        migrated += 1

    return migrated


def load_metadata(base_dir, key):
    """Load report metadata from SQLite by folder path, folder name, or report key."""
    if key and (os.path.sep in key or key.startswith(base_dir)):
        key = os.path.basename(key.rstrip(os.sep))

    meta = get_report_by_key(base_dir, key)
    if meta:
        return meta

    report_dir = get_report_dir(base_dir, key)
    legacy = _load_legacy_metadata_json(report_dir)
    if legacy:
        folder_name = legacy.get("folder_name") or key
        report_number = (
            legacy.get("report_number")
            or report_number_from_folder_name(key)
            or legacy.get("id")
            or key
        )
        legacy["folder_name"] = folder_name
        legacy["report_number"] = report_number
        pdf_path = get_pdf_path(report_dir, report_number)
        return upsert_report(base_dir, legacy, pdf_path=_relative_pdf_path(base_dir, pdf_path))

    return None


def save_metadata(base_dir, report_dir, data, pdf_path=None):
    """Persist report metadata to SQLite."""
    folder_name = data.get("folder_name") or os.path.basename(report_dir)
    data["folder_name"] = folder_name

    if pdf_path is None:
        pdf_path = data.get("pdf_path")
    if pdf_path and os.path.isabs(pdf_path):
        pdf_path = _relative_pdf_path(base_dir, pdf_path)

    return upsert_report(base_dir, data, pdf_path=pdf_path)


def find_report_dir(base_dir, key):
    """Find report folder by folder name, report number, or legacy id."""
    meta = get_report_by_key(base_dir, key)
    if not meta:
        return None

    folder_name = meta.get("folder_name") or key
    report_dir = get_report_dir(base_dir, os.path.basename(folder_name))
    if os.path.isdir(report_dir):
        return report_dir
    return None


def list_all_reports(base_dir):
    """Return metadata dicts for every saved report, newest first."""
    return db_list_all_reports(base_dir)


def search_reports(base_dir, engine_sn="", registration="", msn="", report_number=""):
    """Filter reports by optional search fields (partial, case-insensitive)."""
    return db_search_reports(
        base_dir,
        engine_sn=engine_sn,
        registration=registration,
        msn=msn,
        report_number=report_number,
    )


def get_pdf_path(report_dir, report_number, base_dir=None):
    named = os.path.join(report_dir, pdf_filename_for(report_number))
    if os.path.exists(named):
        return named
    pdfs = [f for f in os.listdir(report_dir) if f.endswith(".pdf")]
    return os.path.join(report_dir, pdfs[0]) if pdfs else None


def resolve_pdf_path(base_dir, metadata):
    """Return absolute PDF path from stored metadata."""
    stored = metadata.get("pdf_path")
    absolute = _absolute_pdf_path(base_dir, stored)
    if absolute:
        return absolute

    folder_name = metadata.get("folder_name")
    if not folder_name:
        return None
    report_dir = find_report_dir(base_dir, folder_name)
    if not report_dir:
        return None
    return get_pdf_path(report_dir, metadata.get("report_number", ""))


def photo_paths_for_metadata(base_dir, folder_name, photos_meta):
    """Resolve absolute paths for photo entries in a report folder."""
    report_dir = find_report_dir(base_dir, folder_name)
    if not report_dir:
        return []

    photos_dir = get_photos_dir(report_dir)
    entries = []
    for photo in photos_meta:
        stored = photo.get("stored_name", "")
        path = os.path.join(photos_dir, stored)
        if not os.path.exists(path):
            path = os.path.join(report_dir, stored)
        entries.append({
            "filename": photo.get("filename", stored),
            "stored_name": stored,
            "path": path if os.path.exists(path) else None,
            "area": photo.get("area", ""),
            "defect_description": photo.get("defect_description", ""),
            "severity": photo.get("severity", "Acceptable"),
        })
    return entries
