import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "chronicle-dev-secret-2024")
    SESSION_PERMANENT = False

    # MySQL – Aiven for MySQL (SSL required over port 26320)
    DB_HOST     = os.environ.get("DB_HOST",     "mysql-1c6fb4b1-dbmsproject23.d.aivencloud.com")
    DB_PORT     = int(os.environ.get("DB_PORT", 26320))
    DB_USER     = os.environ.get("DB_USER",     "avnadmin")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "AVNS_poFFSVcMGs7kJFTf8gV")
    DB_NAME     = os.environ.get("DB_NAME",     "defaultdb")

    # Cloudinary
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "hlysnjzf")
    CLOUDINARY_API_KEY    = os.environ.get("CLOUDINARY_API_KEY",    "169143711234498")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "sWICOfMl-XyKp35IYliwVtXHHic")

    # Upload constraints
    MAX_UPLOAD_BYTES = 1 * 1024 * 1024  # 1 MB
