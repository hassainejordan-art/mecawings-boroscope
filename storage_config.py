import os

DB_FILENAME = "reports.db"
AMM_FILES_SUBDIR = "amm_files"

RENDER_EPHEMERAL_STORAGE_WARNING = (
    "Render free plan uses temporary local storage. Uploaded AMM PDF files may be "
    "lost after redeploy or restart. Configure a Render Disk and set DATA_DIR=/var/data "
    "for persistent storage. Document metadata and extracted text remain searchable "
    "from the database when the PDF file is no longer available on disk."
)


def is_render_environment():
    return bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_NAME"))


def get_data_dir(base_dir):
    """
    Persistent data root. On Render, mount a disk and set DATA_DIR=/var/data
    (or RENDER_DISK_PATH / PERSISTENT_DATA_DIR).
    """
    for env_var in ("DATA_DIR", "RENDER_DISK_PATH", "PERSISTENT_DATA_DIR"):
        value = (os.environ.get(env_var) or "").strip()
        if value:
            return os.path.abspath(value)
    return os.path.join(base_dir, "data")


def has_configured_persistent_storage():
    return bool(
        os.environ.get("DATA_DIR")
        or os.environ.get("RENDER_DISK_PATH")
        or os.environ.get("PERSISTENT_DATA_DIR")
    )


def show_render_ephemeral_warning(base_dir):
    """True when running on Render without a configured persistent data directory."""
    return is_render_environment() and not has_configured_persistent_storage()


def get_db_path(base_dir):
    return os.path.join(get_data_dir(base_dir), DB_FILENAME)


def get_amm_files_root(base_dir):
    return os.path.join(get_data_dir(base_dir), AMM_FILES_SUBDIR)


def get_report_counter_path(base_dir):
    return os.path.join(get_data_dir(base_dir), "report_counter.json")


def ensure_data_dirs(base_dir):
    data_dir = get_data_dir(base_dir)
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(get_amm_files_root(base_dir), exist_ok=True)
    return data_dir
