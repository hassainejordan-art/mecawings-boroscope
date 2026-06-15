import json
import os
import re
from datetime import datetime

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


def load_metadata(report_dir):
    path = metadata_path(report_dir)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_metadata(report_dir, data):
    os.makedirs(report_dir, exist_ok=True)
    with open(metadata_path(report_dir), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_report_dir(base_dir, key):
    """Find report folder by folder name, report number, or legacy id."""
    if not key:
        return None

    safe_key = os.path.basename(key)
    root = get_reports_root(base_dir)
    if not os.path.isdir(root):
        return None

    direct = os.path.join(root, safe_key)
    if os.path.isdir(direct) and os.path.exists(metadata_path(direct)):
        return direct

    for entry in os.listdir(root):
        folder = os.path.join(root, entry)
        if not os.path.isdir(folder):
            continue
        meta = load_metadata(folder)
        if not meta:
            continue
        if (
            meta.get("folder_name") == safe_key
            or meta.get("report_number") == safe_key
            or meta.get("id") == safe_key
        ):
            return folder
    return None


def list_all_reports(base_dir):
    """Return metadata dicts for every saved report, newest first."""
    root = get_reports_root(base_dir)
    if not os.path.isdir(root):
        return []

    reports = []
    for entry in os.listdir(root):
        folder = os.path.join(root, entry)
        if not os.path.isdir(folder):
            continue
        meta = load_metadata(folder)
        if meta:
            meta = dict(meta)
            meta["folder_name"] = meta.get("folder_name") or entry
            reports.append(meta)

    reports.sort(key=lambda r: r.get("updated_at") or r.get("created_at") or "", reverse=True)
    return reports


def search_reports(base_dir, engine_sn="", registration="", msn="", report_number=""):
    """Filter reports by optional search fields (partial, case-insensitive)."""
    reports = list_all_reports(base_dir)

    def match(value, query):
        if not query:
            return True
        return query.lower() in (value or "").lower()

    return [
        r
        for r in reports
        if match(r.get("engine_sn", ""), engine_sn)
        and match(r.get("registration", ""), registration)
        and match(r.get("msn", ""), msn)
        and match(r.get("report_number", ""), report_number)
    ]


def get_pdf_path(report_dir, report_number):
    named = os.path.join(report_dir, pdf_filename_for(report_number))
    if os.path.exists(named):
        return named
    pdfs = [f for f in os.listdir(report_dir) if f.endswith(".pdf")]
    return os.path.join(report_dir, pdfs[0]) if pdfs else None


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
