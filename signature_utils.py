import base64
import os
import re


def save_signature_data_url(data_url, output_path):
    """Decode a canvas data URL and save as PNG. Returns path or None."""
    if not data_url or not data_url.strip():
        return None

    match = re.match(r"data:image/(png|jpeg|jpg);base64,(.+)", data_url.strip(), re.I)
    if not match:
        return None

    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except (ValueError, TypeError):
        return None

    if len(raw) < 100:
        return None

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(raw)
    return output_path
