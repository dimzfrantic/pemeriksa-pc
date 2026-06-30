import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "ganti-dengan-string-acak")
    db_path = os.environ.get("SQLALCHEMY_DATABASE_PATH", "instance/pcmonitor.db")
    # Absolutkan path DB supaya konsisten saat dijalankan via gunicorn maupun langsung
    if not os.path.isabs(db_path):
        db_path = os.path.join(BASE_DIR, db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    raw_chats = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
    TELEGRAM_ALLOWED_CHAT_IDS = [
        int(x.strip()) for x in raw_chats.split(",") if x.strip().isdigit()
    ]

    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

    # Token rahasia untuk endpoint laporan agen (agen Windows -> server)
    AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "").strip()
    # Ambang detik untuk menganggap PC offline (laporan agen terakhir lebih tua dari ini)
    AGENT_OFFLINE_SECONDS = int(os.environ.get("AGENT_OFFLINE_SECONDS", "180"))

    # Passcode sederhana untuk mengunci akses web (API tetap bebas)
    WEB_PASSCODE = os.environ.get("WEB_PASSCODE", "1234").strip()

    # Branding (diisi via .env; default generik agar repo netral)
    ORG_NAME = os.environ.get("ORG_NAME", "Instansi").strip()
    APP_TITLE = os.environ.get("APP_TITLE", "Pemantauan PC").strip()
    ASSISTANT_NAME = os.environ.get("ASSISTANT_NAME", "Asisten PC").strip()
    ASSISTANT_SAPAAN = os.environ.get("ASSISTANT_SAPAAN", "Bos").strip()