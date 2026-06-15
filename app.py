import json
import os
import uuid
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

from constants import ENGINE_AREAS, SEVERITY_LEVELS
from pdf_generator import generate_borescope_report

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "boro-report-dev-key-change-in-production")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "photos")
REPORTS_FOLDER = os.path.join(BASE_DIR, "static", "reports")
LOGO_PATH = os.path.join(BASE_DIR, "static", "img", "logo.png")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "heic", "heif"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORTS_FOLDER, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "static", "img"), exist_ok=True)

app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def normalize_photo_meta(meta):
    """Normalize photo metadata from form or legacy reports."""
    severity = meta.get("severity") or meta.get("classification", "Acceptable")
    if severity not in SEVERITY_LEVELS:
        severity = "Acceptable"

    area = meta.get("area", ENGINE_AREAS[0])
    if area not in ENGINE_AREAS:
        area = ENGINE_AREAS[0]

    defect = meta.get("defect_description") or meta.get("comment", "")

    return {
        "area": area,
        "defect_description": defect.strip(),
        "severity": severity,
    }


def save_report(report_id, report_data, photo_entries):
    """Persist report metadata and generate PDF."""
    report_dir = os.path.join(REPORTS_FOLDER, report_id)
    os.makedirs(report_dir, exist_ok=True)

    metadata = {
        "id": report_id,
        "created_at": datetime.now().isoformat(),
        **report_data,
        "photos": [
            {
                "filename": p["filename"],
                "stored_name": p["stored_name"],
                "area": p["area"],
                "defect_description": p["defect_description"],
                "severity": p["severity"],
            }
            for p in photo_entries
        ],
    }

    metadata_path = os.path.join(report_dir, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    pdf_photos = [
        {
            "path": p["path"],
            "filename": p["filename"],
            "area": p["area"],
            "defect_description": p["defect_description"],
            "severity": p["severity"],
        }
        for p in photo_entries
    ]

    pdf_path = os.path.join(report_dir, f"borescope_report_{report_id[:8]}.pdf")
    generate_borescope_report(report_data, pdf_photos, pdf_path, logo_path=LOGO_PATH)

    return pdf_path, metadata


@app.route("/", methods=["GET"])
def home():
    today = datetime.now().strftime("%Y-%m-%d")
    return render_template("index.html", today=today, engine_areas=ENGINE_AREAS)


@app.route("/submit", methods=["POST"])
def submit_report():
    report_data = {
        "customer": request.form.get("customer", "").strip(),
        "aircraft": request.form.get("aircraft", "B737-800").strip(),
        "registration": request.form.get("registration", "").strip(),
        "msn": request.form.get("msn", "").strip(),
        "engine_sn": request.form.get("engine_sn", "").strip(),
        "engine_position": request.form.get("engine_position", "").strip(),
        "date": request.form.get("date", "").strip(),
        "po": request.form.get("po", "").strip(),
        "inspector": request.form.get("inspector", "").strip(),
    }

    if not report_data["customer"] or not report_data["engine_sn"]:
        flash("Customer and Engine S/N are required.", "error")
        return redirect(url_for("home"))

    photos_meta_raw = request.form.get("photos_meta", "[]")
    try:
        photos_meta = json.loads(photos_meta_raw)
    except json.JSONDecodeError:
        photos_meta = []

    uploaded_files = request.files.getlist("photos")
    if not uploaded_files or all(f.filename == "" for f in uploaded_files):
        flash("Please upload at least one photo.", "error")
        return redirect(url_for("home"))

    report_id = str(uuid.uuid4())
    report_photo_dir = os.path.join(UPLOAD_FOLDER, report_id)
    os.makedirs(report_photo_dir, exist_ok=True)

    photo_entries = []
    for i, photo_file in enumerate(uploaded_files):
        if not photo_file or not photo_file.filename:
            continue
        if not allowed_file(photo_file.filename):
            continue

        original_name = photo_file.filename
        safe_name = secure_filename(original_name)
        if not safe_name:
            safe_name = f"photo_{i + 1}.jpg"

        unique_name = f"{i + 1:03d}_{safe_name}"
        save_path = os.path.join(report_photo_dir, unique_name)
        photo_file.save(save_path)

        meta = normalize_photo_meta(photos_meta[i] if i < len(photos_meta) else {})

        photo_entries.append(
            {
                "filename": original_name,
                "stored_name": unique_name,
                "path": save_path,
                "area": meta["area"],
                "defect_description": meta["defect_description"],
                "severity": meta["severity"],
            }
        )

    if not photo_entries:
        flash("No valid photos were uploaded.", "error")
        return redirect(url_for("home"))

    pdf_path, metadata = save_report(report_id, report_data, photo_entries)
    pdf_filename = os.path.basename(pdf_path)

    return render_template(
        "success.html",
        report=report_data,
        report_id=report_id,
        photos=photo_entries,
        pdf_filename=pdf_filename,
        photo_count=len(photo_entries),
    )


@app.route("/download/<report_id>/<filename>")
def download_pdf(report_id, filename):
    safe_report = os.path.basename(report_id)
    safe_file = os.path.basename(filename)
    full_dir = os.path.join(REPORTS_FOLDER, safe_report)

    if not os.path.isdir(full_dir):
        abort(404)

    return send_from_directory(full_dir, safe_file, as_attachment=True)


@app.route("/view/<report_id>")
def view_report(report_id):
    report_dir = os.path.join(REPORTS_FOLDER, report_id)
    metadata_path = os.path.join(report_dir, "metadata.json")

    if not os.path.exists(metadata_path):
        abort(404)

    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)

    pdf_files = [f for f in os.listdir(report_dir) if f.endswith(".pdf")]
    pdf_filename = pdf_files[0] if pdf_files else None

    photos = []
    for p in metadata.get("photos", []):
        photos.append(normalize_photo_meta(p) | {
            "filename": p.get("filename", ""),
            "stored_name": p.get("stored_name", ""),
        })

    return render_template(
        "success.html",
        report=metadata,
        report_id=report_id,
        photos=photos,
        pdf_filename=pdf_filename,
        photo_count=len(photos),
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
