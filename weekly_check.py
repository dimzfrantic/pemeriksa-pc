#!/usr/bin/env python3
"""
Pemeriksaan otomatis mingguan PC.

Dijalankan oleh cron (Senin 08:00 WIB). Untuk setiap PC terdaftar:
- ambil snapshot agen terakhir (PCLive)
- offline bila laporan basi -> catat status OFFLINE
- online -> bandingkan spek aktual vs standar -> catat OK / TIDAK_LENGKAP
Lalu cetak ringkasan ke stdout (dikirim ke topik Telegram "Pemeriksaan PC"
oleh penjadwal cron / dipakai oleh skrip pengirim).

Dijalankan sebagai: python weekly_check.py
"""
import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from app import create_app
from extensions import db
from models import PC, Inspection, PCLive
import spec_compare
import datetime as _dt


def run():
    app = create_app()
    with app.app_context():
        offline_secs = int(app.config.get("AGENT_OFFLINE_SECONDS", 180))
        pcs = PC.query.order_by(PC.name.asc()).all()
        ok = []
        tidak = []
        offline = []

        for pc in pcs:
            live = PCLive.query.filter_by(pc_name=pc.name).first()
            if not live or not live.is_online(offline_secs):
                last = live.last_seen.strftime("%Y-%m-%d %H:%M") if (live and live.last_seen) else "belum pernah lapor"
                note = f"Agen tidak aktif (laporan terakhir: {last})"
                db.session.add(Inspection(pc_id=pc.id, status="OFFLINE", note=note, source="auto-weekly"))
                offline.append(pc.name)
                continue
            status, kekurangan = spec_compare.compare(pc, live)
            note = "; ".join(kekurangan) if kekurangan else "Spek sesuai standar"
            db.session.add(Inspection(pc_id=pc.id, status=status, note=note, source="auto-weekly"))
            if status == "OK":
                ok.append(pc.name)
            else:
                tidak.append((pc.name, note))

        db.session.commit()

        # Ringkasan untuk dikirim ke Telegram
        org_name = app.config.get("ORG_NAME", "Instansi")
        now = _dt.datetime.now().strftime("%d %b %Y, %H:%M")
        total = len(pcs)
        lines = [
            f"📋 Pemeriksaan Otomatis Mingguan PC",
            f"{org_name} — {now}",
            "",
            f"Total unit: {total}",
            f"✅ Lengkap (OK): {len(ok)}",
            f"⚠️ Tidak lengkap: {len(tidak)}",
            f"🔴 Offline: {len(offline)}",
        ]
        if tidak:
            lines.append("")
            lines.append("Perlu perhatian (tidak lengkap):")
            for nama, note in tidak:
                lines.append(f"• {nama}: {note}")
        if offline:
            lines.append("")
            lines.append("Offline saat diperiksa:")
            for nama in offline:
                lines.append(f"• {nama}")
        lines.append("")
        lines.append("Detail lengkap dapat dilihat di portal web atau ketik 'list'.")
        summary = "\n".join(lines)
        print(summary)
        return summary


def send_telegram(summary):
    """Kirim ringkasan ke topik Pemeriksaan PC via bot @pemeriksapc_bot."""
    import urllib.request, urllib.error, json as _json
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE, ".env"))
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chats = [c.strip() for c in os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if c.strip()]
    threads = [t.strip() for t in os.environ.get("TELEGRAM_ALLOWED_THREAD_IDS", "").split(",") if t.strip()]
    if not (token and chats):
        print("[WARN] TELEGRAM_BOT_TOKEN/CHAT belum diset; lewati kirim.")
        return
    chat_id = chats[0]
    payload = {"chat_id": chat_id, "text": summary, "disable_web_page_preview": True}
    if threads:
        payload["message_thread_id"] = int(threads[0])
    data = _json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data, method="POST",
    )
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"[OK] Ringkasan terkirim ke Telegram ({r.status}).")
    except Exception as e:
        print(f"[ERR] Gagal kirim Telegram: {e}")


if __name__ == "__main__":
    summary = run()
    if "--send" in sys.argv:
        send_telegram(summary)
