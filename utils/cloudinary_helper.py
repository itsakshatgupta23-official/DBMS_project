"""utils/cloudinary_helper.py – Cloudinary upload & delete wrappers"""
import cloudinary.uploader
from config import Config

MAX_BYTES = Config.MAX_UPLOAD_BYTES  # 1 MB


def upload_file(file_storage, folder: str = "chronicle") -> dict:
    """
    Upload a Werkzeug FileStorage object to Cloudinary.
    Returns dict with: secure_url, public_id, bytes, format.
    Raises ValueError if file exceeds 1 MB.
    """
    file_storage.seek(0, 2)  # seek to end
    size = file_storage.tell()
    file_storage.seek(0)

    if size > MAX_BYTES:
        raise ValueError(f"File too large ({size} bytes). Maximum is {MAX_BYTES} bytes (1 MB).")

    result = cloudinary.uploader.upload(
        file_storage,
        folder=folder,
        resource_type="auto",
    )
    return {
        "secure_url": result["secure_url"],
        "public_id":  result["public_id"],
        "bytes":      result["bytes"],
        "format":     result.get("format", ""),
    }


def delete_file(public_id: str, resource_type: str = "image") -> bool:
    """Delete a Cloudinary asset by public_id. Returns True on success."""
    result = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
    return result.get("result") == "ok"
