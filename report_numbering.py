import json
import os
import re
from datetime import datetime

from storage_config import get_report_counter_path

REPORT_NUMBER_PATTERN = re.compile(r"^MW_(\d{4})_(\d{4})$")


def _counter_path(base_dir):
    return get_report_counter_path(base_dir)


def _load_counter(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"year": None, "last_number": 0}


def _save_counter(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def peek_next_report_number(base_dir=None):
    """Return the report number that will be assigned on next submission."""
    base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
    year = datetime.now().year
    counter = _load_counter(_counter_path(base_dir))
    last_number = counter.get("last_number", 0)
    if counter.get("year") != year:
        next_number = 1
    else:
        next_number = last_number + 1
    return f"MW_{year}_{next_number:04d}"


def allocate_report_number(base_dir=None):
    """Reserve and return the next report number, persisting the counter."""
    base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
    path = _counter_path(base_dir)
    year = datetime.now().year

    try:
        import fcntl

        with open(path, "a+", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.seek(0)
            content = f.read().strip()
            counter = json.loads(content) if content else {"year": None, "last_number": 0}

            if counter.get("year") != year:
                next_number = 1
            else:
                next_number = counter.get("last_number", 0) + 1

            report_number = f"MW_{year}_{next_number:04d}"
            counter = {"year": year, "last_number": next_number}
            f.seek(0)
            f.truncate()
            json.dump(counter, f, indent=2)
            return report_number
    except ImportError:
        counter = _load_counter(path)
        if counter.get("year") != year:
            next_number = 1
        else:
            next_number = counter.get("last_number", 0) + 1
        report_number = f"MW_{year}_{next_number:04d}"
        _save_counter(path, {"year": year, "last_number": next_number})
        return report_number


def is_valid_report_number(value):
    return bool(value and REPORT_NUMBER_PATTERN.match(value))


def parse_report_number(value):
    """Return (year, sequence) for a valid report number, else (None, None)."""
    match = REPORT_NUMBER_PATTERN.match(value or "")
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def report_number_from_folder_name(folder_name):
    """Extract MW_YYYY_NNNN prefix from a report folder name."""
    if not folder_name or not folder_name.startswith("MW_"):
        return None
    parts = folder_name.split("_")
    if len(parts) < 3:
        return None
    candidate = f"MW_{parts[1]}_{parts[2]}"
    return candidate if is_valid_report_number(candidate) else None


def sync_counter_from_reports(base_dir=None):
    """
    Ensure the stored counter is at least as high as existing reports.
    Prevents duplicate numbers after counter file loss or manual folder creation.
    """
    base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
    year = datetime.now().year
    max_number = 0

    try:
        from report_storage import list_all_reports

        for report in list_all_reports(base_dir):
            report_year, number = parse_report_number(report.get("report_number"))
            if report_year == year and number:
                max_number = max(max_number, number)
    except Exception:
        pass

    reports_root = os.path.join(base_dir, "static", "reports")
    if os.path.isdir(reports_root):
        for entry in os.listdir(reports_root):
            report_year, number = parse_report_number(report_number_from_folder_name(entry))
            if report_year == year and number:
                max_number = max(max_number, number)

    path = _counter_path(base_dir)
    counter = _load_counter(path)
    current = counter.get("last_number", 0) if counter.get("year") == year else 0

    if max_number > current:
        _save_counter(path, {"year": year, "last_number": max_number})
