import json
import os
from datetime import datetime

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

from constants import (
    AI_ADVISORY_WARNING,
    AIRCRAFT_TYPES,
    ATA_CHAPTERS,
    CERTIFICATION_TEXT,
    CLASSIFICATION_LEVELS,
    CUSTOM_OPTION,
    DEFECT_CATEGORIES,
    ENGINE_POSITIONS,
    ENGINE_TYPE_GROUPS,
    ENGINE_TYPES,
    INSPECTION_AREAS,
    REPORT_SUBTITLE,
    REPORT_TITLE,
    SEVERITY_LEVELS,
)
from pdf_generator import generate_borescope_report
from amm_storage import (
    get_amm_document,
    init_amm_storage,
    list_amm_documents,
    resolve_amm_file_path,
    save_amm_document,
    search_amm_documents,
)
from ai_service import get_advisory_warning, is_ai_enabled, search_amm_context, suggest_finding_classification
from report_numbering import allocate_report_number, peek_next_report_number, sync_counter_from_reports
from report_storage import (
    build_folder_name,
    ensure_storage,
    find_report_dir,
    get_pdf_path,
    get_photos_dir,
    get_report_dir,
    get_reports_root,
    load_metadata,
    pdf_filename_for,
    photo_paths_for_metadata,
    resolve_pdf_path,
    save_metadata,
    search_reports,
)
from signature_utils import save_signature_data_url
from storage_config import (
    RENDER_EPHEMERAL_STORAGE_WARNING,
    ensure_data_dirs,
    get_data_dir,
    has_configured_persistent_storage,
    show_render_ephemeral_warning,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "boro-report-dev-key-change-in-production")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_FOLDER = get_reports_root(BASE_DIR)
LOGO_PATH = os.path.join(BASE_DIR, "static", "logo", "mecawings_logo.png")
DATA_FOLDER = get_data_dir(BASE_DIR)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "heic", "heif"}

os.makedirs(REPORTS_FOLDER, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "static", "logo"), exist_ok=True)
ensure_data_dirs(BASE_DIR)
ensure_storage(BASE_DIR)
init_amm_storage(BASE_DIR)
sync_counter_from_reports(BASE_DIR)

app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB (AMM PDF uploads)


def logo_exists():
    return os.path.exists(LOGO_PATH)


@app.context_processor
def inject_globals():
    return {
        "logo_url": url_for("static", filename="logo/mecawings_logo.png") if logo_exists() else None,
        "logo_missing": not logo_exists(),
        "logo_path_hint": "static/logo/mecawings_logo.png",
        "ai_advisory_warning": get_advisory_warning(),
        "ai_enabled": is_ai_enabled(),
        "render_ephemeral_warning": RENDER_EPHEMERAL_STORAGE_WARNING,
        "show_render_ephemeral_warning": show_render_ephemeral_warning(BASE_DIR),
        "has_persistent_storage": has_configured_persistent_storage(),
        "data_dir": DATA_FOLDER,
    }


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _resolve_preset_field(preset_value, custom_value):
    preset = (preset_value or "").strip()
    custom = (custom_value or "").strip()
    if preset == CUSTOM_OPTION:
        return custom
    return preset or custom


def _preset_form_state(value, options, default=""):
    value = (value or default).strip()
    if value in options:
        return {"preset": value, "custom": ""}
    if value:
        return {"preset": CUSTOM_OPTION, "custom": value}
    return {"preset": default or options[0] if options else "", "custom": ""}


def _parse_inspected_areas(form):
    areas = [a.strip() for a in form.getlist("inspected_areas") if a.strip()]
    valid = [a for a in areas if a in INSPECTION_AREAS]
    return valid


def normalize_photo_meta(meta):
    classification = (
        meta.get("classification")
        or meta.get("severity")
        or "Acceptable"
    )
    if classification not in CLASSIFICATION_LEVELS:
        classification = "Acceptable"

    area = meta.get("area") or INSPECTION_AREAS[0]
    if area not in INSPECTION_AREAS:
        pass  # keep legacy/custom photo area labels

    defect_category = meta.get("defect_category", DEFECT_CATEGORIES[0])
    if defect_category not in DEFECT_CATEGORIES:
        defect_category = DEFECT_CATEGORIES[0]

    comment = meta.get("comment") or meta.get("defect_description", "")

    result = {
        "area": area,
        "defect_category": defect_category,
        "comment": comment.strip(),
        "classification": classification,
        "severity": classification,
        "defect_description": comment.strip(),
    }

    if meta.get("amm_reference_id"):
        result["amm_reference_id"] = meta.get("amm_reference_id")
        result["amm_reference_label"] = meta.get("amm_reference_label", "")
        result["amm_reference"] = meta.get("amm_reference")

    maintenance_ref = (meta.get("maintenance_data_reference") or "").strip()
    if maintenance_ref:
        result["maintenance_data_reference"] = maintenance_ref
    elif result.get("amm_reference_label"):
        result["maintenance_data_reference"] = result["amm_reference_label"]

    return result


def _classification_counts(photos):
    counts = {"Acceptable": 0, "Monitor": 0, "Reject": 0}
    for photo in photos:
        cls = photo.get("classification") or photo.get("severity", "Acceptable")
        if cls in counts:
            counts[cls] += 1
    return counts


def _photos_for_display(photo_entries):
    return [normalize_photo_meta(p) | {
        "filename": p.get("filename", ""),
        "stored_name": p.get("stored_name", ""),
    } for p in photo_entries]


def _parse_json_field(raw, default=None):
    if default is None:
        default = []
    try:
        return json.loads(raw) if raw else default
    except json.JSONDecodeError:
        return default


def _build_report_form_context(edit_report=None, edit_folder=None):
    today = datetime.now().strftime("%Y-%m-%d")
    report = edit_report or {}
    aircraft_state = _preset_form_state(report.get("aircraft"), AIRCRAFT_TYPES, "B737-800")
    engine_state = _preset_form_state(report.get("engine_type"), ENGINE_TYPES, ENGINE_TYPES[0])

    base = {
        "today": report.get("date") or today,
        "aircraft_types": AIRCRAFT_TYPES,
        "engine_type_groups": ENGINE_TYPE_GROUPS,
        "engine_positions": ENGINE_POSITIONS,
        "inspection_areas": INSPECTION_AREAS,
        "defect_categories": DEFECT_CATEGORIES,
        "aircraft_state": aircraft_state,
        "engine_state": engine_state,
        "selected_inspected_areas": report.get("inspected_areas", []),
        "custom_option": CUSTOM_OPTION,
        "ai_advisory_warning": get_advisory_warning(),
    }

    if edit_report:
        folder = edit_folder or edit_report.get("folder_name", "")
        has_existing_signature = bool(edit_report.get("has_signature"))
        existing_signature_url = ""
        if folder and has_existing_signature:
            existing_signature_url = url_for(
                "report_files",
                folder_name=folder,
                filename="inspector_signature.png",
            )
        return base | {
            "report_number": edit_report.get("report_number", ""),
            "edit_mode": True,
            "source_folder": edit_folder,
            "report": edit_report,
            "existing_photos": edit_report.get("photos", []),
            "has_existing_signature": has_existing_signature,
            "existing_signature_url": existing_signature_url,
            "certification_text": CERTIFICATION_TEXT,
            "active_page": "new",
        }
    return base | {
        "report_number": peek_next_report_number(BASE_DIR),
        "edit_mode": False,
        "source_folder": "",
        "report": None,
        "existing_photos": [],
        "has_existing_signature": False,
        "existing_signature_url": "",
        "certification_text": CERTIFICATION_TEXT,
        "active_page": "new",
    }


def _save_photos_to_folder(photos_dir, uploaded_files, photos_meta, start_index=1):
    os.makedirs(photos_dir, exist_ok=True)
    entries = []
    file_index = 0

    for photo_file in uploaded_files:
        if not photo_file or not photo_file.filename:
            continue
        if not allowed_file(photo_file.filename):
            continue

        original_name = photo_file.filename
        safe_name = secure_filename(original_name) or f"photo_{start_index + file_index}.jpg"
        unique_name = f"{start_index + file_index:03d}_{safe_name}"
        save_path = os.path.join(photos_dir, unique_name)
        photo_file.save(save_path)

        meta = normalize_photo_meta(photos_meta[file_index] if file_index < len(photos_meta) else {})
        entry = {
            "filename": original_name,
            "stored_name": unique_name,
            "path": save_path,
            "area": meta["area"],
            "defect_category": meta["defect_category"],
            "comment": meta["comment"],
            "classification": meta["classification"],
            "severity": meta["classification"],
            "defect_description": meta["comment"],
        }
        if meta.get("amm_reference_id"):
            entry["amm_reference_id"] = meta["amm_reference_id"]
            entry["amm_reference_label"] = meta.get("amm_reference_label", "")
            entry["amm_reference"] = meta.get("amm_reference")
        if meta.get("maintenance_data_reference"):
            entry["maintenance_data_reference"] = meta["maintenance_data_reference"]
        entries.append(entry)
        file_index += 1

    return entries


def _merge_existing_photos(existing_meta, photos_dir):
    entries = []
    for photo in existing_meta:
        stored = photo.get("stored_name", "")
        path = os.path.join(photos_dir, stored)
        if not os.path.exists(path):
            continue
        normalized = normalize_photo_meta(photo)
        entry = {
            "filename": photo.get("filename", stored),
            "stored_name": stored,
            "path": path,
            "area": normalized["area"],
            "defect_category": normalized["defect_category"],
            "comment": normalized["comment"],
            "classification": normalized["classification"],
            "severity": normalized["classification"],
            "defect_description": normalized["comment"],
        }
        if normalized.get("amm_reference_id"):
            entry["amm_reference_id"] = normalized["amm_reference_id"]
            entry["amm_reference_label"] = normalized.get("amm_reference_label", "")
            entry["amm_reference"] = normalized.get("amm_reference")
        if normalized.get("maintenance_data_reference"):
            entry["maintenance_data_reference"] = normalized["maintenance_data_reference"]
        entries.append(entry)
    return entries


def save_report(folder_name, report_data, photo_entries, signature_path=None, is_update=False):
    report_dir = get_report_dir(BASE_DIR, folder_name)
    os.makedirs(report_dir, exist_ok=True)

    now = datetime.now().isoformat()
    metadata = {
        "id": report_data["report_number"],
        "folder_name": folder_name,
        "report_number": report_data["report_number"],
        "created_at": report_data.get("created_at") or now,
        "updated_at": now,
        "customer": report_data.get("customer"),
        "aircraft": report_data.get("aircraft"),
        "engine_type": report_data.get("engine_type"),
        "registration": report_data.get("registration"),
        "msn": report_data.get("msn"),
        "engine_sn": report_data.get("engine_sn"),
        "engine_position": report_data.get("engine_position"),
        "inspected_areas": report_data.get("inspected_areas", []),
        "date": report_data.get("date"),
        "po": report_data.get("po"),
        "inspector": report_data.get("inspector"),
        "has_signature": bool(signature_path and os.path.exists(signature_path)),
        "photos": [
            {
                "filename": p["filename"],
                "stored_name": p["stored_name"],
                "area": p["area"],
                "defect_category": p["defect_category"],
                "comment": p["comment"],
                "classification": p["classification"],
                "severity": p["classification"],
                "defect_description": p["comment"],
                **({
                    "amm_reference_id": p["amm_reference_id"],
                    "amm_reference_label": p.get("amm_reference_label", ""),
                    "amm_reference": p.get("amm_reference"),
                } if p.get("amm_reference_id") else {}),
                **({
                    "maintenance_data_reference": p.get("maintenance_data_reference", ""),
                } if p.get("maintenance_data_reference") else {}),
            }
            for p in photo_entries
        ],
    }

    pdf_photos = []
    for p in photo_entries:
        if not p.get("path") or not os.path.exists(p["path"]):
            continue
        photo_payload = {
            "path": p["path"],
            "filename": p["filename"],
            "area": p["area"],
            "defect_category": p["defect_category"],
            "comment": p["comment"],
            "classification": p["classification"],
            "severity": p["classification"],
            "defect_description": p["comment"],
        }
        if p.get("amm_reference_id"):
            photo_payload["amm_reference_id"] = p["amm_reference_id"]
            photo_payload["amm_reference_label"] = p.get("amm_reference_label", "")
            photo_payload["amm_reference"] = p.get("amm_reference")
        if p.get("maintenance_data_reference"):
            photo_payload["maintenance_data_reference"] = p["maintenance_data_reference"]
        pdf_photos.append(photo_payload)

    pdf_path = os.path.join(report_dir, pdf_filename_for(report_data["report_number"]))
    generate_borescope_report(
        report_data,
        pdf_photos,
        pdf_path,
        logo_path=LOGO_PATH,
        signature_path=signature_path,
    )

    save_metadata(BASE_DIR, report_dir, metadata, pdf_path=pdf_path)

    return pdf_path, metadata


@app.route("/", methods=["GET"])
def home():
    return render_template("index.html", **_build_report_form_context())


@app.route("/history", methods=["GET"])
def history():
    results = search_reports(
        BASE_DIR,
        engine_sn=request.args.get("engine_sn", "").strip(),
        registration=request.args.get("registration", "").strip(),
        msn=request.args.get("msn", "").strip(),
        report_number=request.args.get("report_number", "").strip(),
    )

    for report in results:
        folder = report.get("folder_name") or report.get("report_number")
        pdf_path = resolve_pdf_path(BASE_DIR, report)
        report["pdf_filename"] = os.path.basename(pdf_path) if pdf_path else None
        report["folder_name"] = folder

    return render_template(
        "history.html",
        results=results,
        search={
            "engine_sn": request.args.get("engine_sn", "").strip(),
            "registration": request.args.get("registration", "").strip(),
            "msn": request.args.get("msn", "").strip(),
            "report_number": request.args.get("report_number", "").strip(),
        },
        active_page="history",
    )


@app.route("/edit/<folder_name>", methods=["GET"])
def edit_report(folder_name):
    report_dir = find_report_dir(BASE_DIR, folder_name)
    if not report_dir:
        flash("Report not found.", "error")
        return redirect(url_for("history"))

    metadata = load_metadata(BASE_DIR, report_dir)
    if not metadata:
        flash("Report data not found.", "error")
        return redirect(url_for("history"))

    return render_template(
        "index.html",
        **_build_report_form_context(edit_report=metadata, edit_folder=metadata.get("folder_name") or folder_name),
    )


@app.route("/submit", methods=["POST"])
def submit_report():
    source_folder = request.form.get("source_folder", "").strip()
    is_edit = bool(source_folder)

    if is_edit:
        report_dir = find_report_dir(BASE_DIR, source_folder)
        if not report_dir:
            flash("Original report not found.", "error")
            return redirect(url_for("history"))
        existing_meta = load_metadata(BASE_DIR, report_dir)
        report_number = existing_meta.get("report_number")
        folder_name = existing_meta.get("folder_name") or os.path.basename(report_dir)
        created_at = existing_meta.get("created_at")
    else:
        report_number = allocate_report_number(BASE_DIR)
        folder_name = None
        created_at = None

    report_data = {
        "report_number": report_number,
        "customer": request.form.get("customer", "").strip(),
        "aircraft": _resolve_preset_field(
            request.form.get("aircraft_preset"),
            request.form.get("aircraft_custom"),
        ) or "B737-800",
        "engine_type": _resolve_preset_field(
            request.form.get("engine_type_preset"),
            request.form.get("engine_type_custom"),
        ),
        "registration": request.form.get("registration", "").strip(),
        "msn": request.form.get("msn", "").strip(),
        "engine_sn": request.form.get("engine_sn", "").strip(),
        "engine_position": request.form.get("engine_position", ENGINE_POSITIONS[0]).strip(),
        "inspected_areas": _parse_inspected_areas(request.form),
        "date": request.form.get("date", "").strip(),
        "po": request.form.get("po", "").strip(),
        "inspector": request.form.get("inspector", "").strip(),
        "created_at": created_at or datetime.now().isoformat(),
    }

    if not report_data["customer"] or not report_data["engine_sn"]:
        flash("Customer and Engine S/N are required.", "error")
        return redirect(url_for("home"))

    if not report_data["engine_type"]:
        flash("Engine type is required.", "error")
        return redirect(url_for("home"))

    if not report_data["inspector"]:
        flash("Inspector name is required.", "error")
        if is_edit:
            return redirect(url_for("edit_report", folder_name=folder_name))
        return redirect(url_for("home"))

    if not is_edit:
        folder_name = build_folder_name(
            report_number,
            report_data["registration"],
            report_data["engine_sn"],
        )

    report_dir = get_report_dir(BASE_DIR, folder_name)
    photos_dir = get_photos_dir(report_dir)
    os.makedirs(photos_dir, exist_ok=True)

    existing_photos_meta = _parse_json_field(request.form.get("existing_photos_meta", "[]"))
    removed_photos = set(_parse_json_field(request.form.get("removed_photos", "[]")))
    new_photos_meta = _parse_json_field(request.form.get("photos_meta", "[]"))

    kept_existing = [
        normalize_photo_meta(p) | {
            "filename": p.get("filename", p.get("stored_name", "")),
            "stored_name": p.get("stored_name", ""),
        }
        for p in existing_photos_meta
        if p.get("stored_name") and p.get("stored_name") not in removed_photos
    ]

    for removed in removed_photos:
        removed_path = os.path.join(photos_dir, removed)
        if os.path.exists(removed_path):
            os.remove(removed_path)

    photo_entries = _merge_existing_photos(kept_existing, photos_dir)

    uploaded_files = request.files.getlist("photos")
    new_uploads = [f for f in uploaded_files if f and f.filename]
    if new_uploads:
        start_index = len(photo_entries) + 1
        photo_entries.extend(
            _save_photos_to_folder(photos_dir, new_uploads, new_photos_meta, start_index=start_index)
        )

    if not photo_entries:
        flash("Please keep or upload at least one photo.", "error")
        if is_edit:
            return redirect(url_for("edit_report", folder_name=folder_name))
        return redirect(url_for("home"))

    signature_data = request.form.get("inspector_signature", "")
    signature_path = os.path.join(report_dir, "inspector_signature.png")
    had_existing_signature = is_edit and os.path.exists(signature_path)

    if signature_data.strip():
        save_signature_data_url(signature_data, signature_path)
    elif not had_existing_signature:
        flash("Inspector signature is required.", "error")
        if is_edit:
            return redirect(url_for("edit_report", folder_name=folder_name))
        return redirect(url_for("home"))

    effective_signature_path = signature_path if os.path.exists(signature_path) else None

    pdf_path, metadata = save_report(
        folder_name,
        report_data,
        photo_entries,
        signature_path=effective_signature_path,
        is_update=is_edit,
    )

    display_photos = _photos_for_display(photo_entries)

    return render_template(
        "success.html",
        report=report_data,
        report_number=report_number,
        folder_name=folder_name,
        photos=display_photos,
        pdf_filename=os.path.basename(pdf_path),
        photo_count=len(photo_entries),
        classification_counts=_classification_counts(display_photos),
        has_signature=metadata.get("has_signature", False),
        signature_url=url_for(
            "report_files",
            folder_name=folder_name,
            filename="inspector_signature.png",
        ) if metadata.get("has_signature") else "",
        active_page="new",
        updated=is_edit,
    )


@app.route("/download/<report_key>/<filename>")
def download_pdf(report_key, filename):
    report_dir = find_report_dir(BASE_DIR, report_key)
    if not report_dir:
        abort(404)
    return send_from_directory(report_dir, os.path.basename(filename), as_attachment=True)


@app.route("/report-files/<folder_name>/<path:filename>")
def report_files(folder_name, filename):
    report_dir = find_report_dir(BASE_DIR, folder_name)
    if not report_dir:
        abort(404)
    safe = os.path.normpath(filename)
    if safe.startswith(".."):
        abort(404)
    return send_from_directory(report_dir, safe)


@app.route("/view/<report_key>")
def view_report(report_key):
    report_dir = find_report_dir(BASE_DIR, report_key)
    if not report_dir:
        abort(404)

    metadata = load_metadata(BASE_DIR, report_dir)
    pdf_path = resolve_pdf_path(BASE_DIR, metadata)
    folder_name = metadata.get("folder_name") or os.path.basename(report_dir)

    photos = _photos_for_display(metadata.get("photos", []))

    return render_template(
        "success.html",
        report=metadata,
        report_number=metadata.get("report_number"),
        folder_name=folder_name,
        photos=photos,
        pdf_filename=os.path.basename(pdf_path) if pdf_path else None,
        photo_count=len(photos),
        classification_counts=_classification_counts(photos),
        has_signature=metadata.get("has_signature", False),
        signature_url=url_for(
            "report_files",
            folder_name=folder_name,
            filename="inspector_signature.png",
        ) if metadata.get("has_signature") else "",
        active_page="new",
        updated=False,
    )


@app.route("/amm-library", methods=["GET"])
def amm_library():
    search = {
        "keyword": request.args.get("keyword", "").strip(),
        "engine_type": request.args.get("engine_type", "").strip(),
        "ata_chapter": request.args.get("ata_chapter", "").strip(),
        "amm_reference": request.args.get("amm_reference", "").strip(),
        "aircraft_type": request.args.get("aircraft_type", "").strip(),
        "document_name": request.args.get("document_name", "").strip(),
        "revision": request.args.get("revision", "").strip(),
    }
    has_search = any(search.values())
    if has_search:
        results = search_amm_documents(
            BASE_DIR,
            keyword=search["keyword"],
            engine_type=search["engine_type"],
            ata_chapter=search["ata_chapter"],
            amm_reference=search["amm_reference"],
            aircraft_type=search["aircraft_type"],
            document_name=search["document_name"],
            revision=search["revision"],
        )
    else:
        results = list_amm_documents(BASE_DIR)

    return render_template(
        "amm_library.html",
        results=results,
        search=search,
        aircraft_types=AIRCRAFT_TYPES,
        engine_type_groups=ENGINE_TYPE_GROUPS,
        ata_chapters=ATA_CHAPTERS,
        custom_option=CUSTOM_OPTION,
        active_page="amm",
    )


@app.route("/amm-library/upload", methods=["POST"])
def amm_library_upload():
    aircraft_type = _resolve_preset_field(
        request.form.get("aircraft_type"),
        request.form.get("aircraft_custom"),
    )
    engine_type = _resolve_preset_field(
        request.form.get("engine_type"),
        request.form.get("engine_custom"),
    )

    try:
        save_amm_document(
            BASE_DIR,
            aircraft_type=aircraft_type,
            engine_type=engine_type,
            ata_chapter=request.form.get("ata_chapter", "").strip(),
            document_name=request.form.get("document_name", "").strip(),
            revision=request.form.get("revision", "").strip(),
            pdf_file=request.files.get("amm_pdf"),
        )
        flash("AMM document uploaded successfully.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    except Exception as exc:
        flash(f"Failed to upload AMM document: {exc}", "error")

    return redirect(url_for("amm_library"))


@app.route("/amm-library/<int:doc_id>/download")
def amm_library_download(doc_id):
    document = get_amm_document(BASE_DIR, doc_id)
    if not document:
        abort(404)
    file_path = resolve_amm_file_path(BASE_DIR, document)
    if not file_path:
        flash(
            "PDF file is not available on disk. Metadata and extracted text search remain available.",
            "error",
        )
        return redirect(url_for("amm_library"))
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    return send_from_directory(directory, filename, as_attachment=True)


@app.route("/amm-library/<int:doc_id>/view")
def amm_library_view(doc_id):
    document = get_amm_document(BASE_DIR, doc_id)
    if not document:
        abort(404)
    file_path = resolve_amm_file_path(BASE_DIR, document)
    if not file_path:
        flash(
            "PDF file is not available on disk. Metadata and extracted text search remain available.",
            "error",
        )
        return redirect(url_for("amm_library"))
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    return send_from_directory(directory, filename, as_attachment=False)


@app.route("/api/amm-documents", methods=["GET"])
def api_amm_documents():
    documents = search_amm_documents(
        BASE_DIR,
        keyword=request.args.get("keyword", "").strip(),
        engine_type=request.args.get("engine_type", "").strip(),
        ata_chapter=request.args.get("ata_chapter", "").strip(),
        amm_reference=request.args.get("amm_reference", "").strip(),
        aircraft_type=request.args.get("aircraft_type", "").strip(),
        document_name=request.args.get("document_name", "").strip(),
        revision=request.args.get("revision", "").strip(),
    )
    return {
        "documents": documents,
        "advisory_warning": get_advisory_warning(),
    }


@app.route("/api/amm-context", methods=["GET"])
def api_amm_context():
    return search_amm_context(
        BASE_DIR,
        query=request.args.get("query", "").strip(),
        engine_type=request.args.get("engine_type", "").strip(),
        ata=request.args.get("ata", "").strip(),
        inspected_area=request.args.get("inspected_area", "").strip(),
    )


@app.route("/api/ai/suggest-finding", methods=["POST"])
def api_ai_suggest_finding():
    """Future AI endpoint — returns advisory-only placeholder until enabled."""
    payload = request.get_json(silent=True) or {}
    suggestion = suggest_finding_classification(
        finding_context=payload.get("finding"),
        amm_reference=payload.get("amm_reference"),
    )
    return suggestion


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
