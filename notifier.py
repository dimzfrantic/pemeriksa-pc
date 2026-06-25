"""Helper kirim notifikasi ke topik Telegram lewat bot pemeriksa PC.

Membaca TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_CHAT_IDS, TELEGRAM_ALLOWED_THREAD_IDS
dari environment (.env). Dipakai untuk boot-check dan pemeriksaan terjadwal.
Aman dipanggil dari proses web (gunicorn): gagal kirim tidak melempar error.
"""
import os
import json
import urllib.request
import urllib.error


def send_telegram(text):
    """Kirim teks ke chat+thread pertama yang diizinkan. Return True bila terkirim."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chats = [c.strip() for c in os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if c.strip()]
    threads = [t.strip() for t in os.environ.get("TELEGRAM_ALLOWED_THREAD_IDS", "").split(",") if t.strip()]
    if not (token and chats):
        return False
    payload = {
        "chat_id": chats[0],
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if threads:
        try:
            payload["message_thread_id"] = int(threads[0])
        except ValueError:
            pass
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data, method="POST",
    )
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception:
        return False
