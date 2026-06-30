#!/usr/bin/env python3
"""Telegram poller untuk aplikasi Pemantauan PC.

Poller ini berjalan sebagai proses terpisah (service systemd terpisah).
Memakai token bot Telegram khusus aplikasi ini (bot terpisah).

Hanya memproses pesan dari:
- Chat ID yang ada di TELEGRAM_ALLOWED_CHAT_IDS (CSV)
- Thread/topic ID yang ada di TELEGRAM_ALLOWED_THREAD_IDS (CSV)
  Jika kosong, proses semua thread di chat yang diizinkan.

Perintah yang dikenali:
  pc <nama pc> ok            -> catat status OK
  pc <nama pc> [<catatan>]   -> catat status TIDAK_LENGKAP + catatan bebas
  pc list                    -> tampilkan status terkini semua PC
  /pclist                    -> alias 'pc list'
  /pchelp                    -> bantuan

Override lewat environment di /home/ubnt/pc-monitor/.env:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_ALLOWED_CHAT_IDS   (CSV, opsional; kosong = terima semua chat)
  TELEGRAM_ALLOWED_THREAD_IDS (CSV, opsional; kosong = terima semua thread)
  PC_MONITOR_API_URL          (default http://127.0.0.1:5080/api)
"""
import os
import sys
import time
import json
import logging
import requests
from dotenv import load_dotenv

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
API_URL = os.environ.get("PC_MONITOR_API_URL", "http://127.0.0.1:5080/api").rstrip("/")
ALLOWED_CHATS = set()
for x in os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").split(","):
    x = x.strip()
    if x.lstrip("-").isdigit():
        ALLOWED_CHATS.add(int(x))

ALLOWED_THREADS = set()
for x in os.environ.get("TELEGRAM_ALLOWED_THREAD_IDS", "").split(","):
    x = x.strip()
    if x.lstrip("-").isdigit():
        ALLOWED_THREADS.add(int(x))

# Branding (diisi via .env; default generik agar kode netral)
ORG_NAME = os.environ.get("ORG_NAME", "Instansi").strip()
APP_TITLE = os.environ.get("APP_TITLE", "Pemantauan PC").strip()
ASSISTANT_NAME = os.environ.get("ASSISTANT_NAME", "Asisten PC").strip()
SAPAAN = os.environ.get("ASSISTANT_SAPAAN", "Bos").strip()

# Konfigurasi AI fallback
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()
LLM_MODEL = os.environ.get("LLM_MODEL", "").strip()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [poller] %(levelname)s %(message)s",
)
log = logging.getLogger("pc-poller")

TG = f"https://api.telegram.org/bot{TOKEN}"


def send(chat_id, text, thread_id=None):
    """Kirim pesan balasan ke chat, dengan thread_id agar masuk ke topik yang benar."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if thread_id:
        payload["message_thread_id"] = thread_id
    try:
        requests.post(f"{TG}/sendMessage", json=payload, timeout=20)
    except Exception as e:
        log.warning("sendMessage error: %s", e)


def handle(text, chat_id, thread_id=None):
    text = (text or "").strip()
    if not text:
        return
    low = text.lower()
    if low in ("/pclist", "pc list", "list", "/list"):
        try:
            r = requests.get(f"{API_URL}/status", timeout=20)
            data = r.json()
        except Exception as e:
            send(chat_id, f"Gagal mengambil status: {e}", thread_id)
            return
        if not data.get("ok"):
            send(chat_id, "API error.", thread_id)
            return
        items = data.get("items", [])
        if not items:
            send(chat_id, "Belum ada PC terdaftar.", thread_id)
            return
        lines = [f"<b>Daftar PC — {APP_TITLE}</b>", ""]
        for it in items:
            spec = it.get("spec", "")
            status = it.get("status", "BELUM")
            display_status = "BELUM DIPERIKSA" if status == "BELUM" else status
            icon = "✅" if status == "OK" else ("⚠️" if status == "TIDAK_LENGKAP" else "▫️")
            lines.append(f"{icon} <b>{it['name']}</b> — {display_status}")
            if spec:
                lines.append(f"   Spek: {spec}")
            if it.get("note"):
                lines.append(f"   Catatan: {it['note']}")
            ts = it.get("inspected_at")
            if ts:
                # Format ISO -> tanggal jam ringkas
                disp = ts.replace("T", " ")[:16]
                lines.append(f"   Diperiksa: {disp}")
            else:
                lines.append("   Diperiksa: belum pernah")
            lines.append("")
        send(chat_id, "\n".join(lines).rstrip(), thread_id)
        return

    if low in ("/pchelp", "pc help", "help", "/help", "bantuan"):
        send(chat_id, (
            f"<b>Panduan Pemeriksaan PC — {APP_TITLE}</b>\n\n"
            "<b>1. Mencatat hasil pemeriksaan (manual):</b>\n"
            "<code>pc &lt;nama&gt; ok</code> — tandai PC lengkap/normal\n"
            "<code>pc &lt;nama&gt; hilang ram</code> — tandai TIDAK LENGKAP + catatan\n"
            "<code>pc &lt;nama&gt; ssd rusak</code> — catatan bebas lain\n\n"
            "<b>2. Pemeriksaan otomatis (via agen):</b>\n"
            "<code>status pc &lt;nama&gt;</code> — cek PC hidup/mati + baca spek aktual\n"
            "    (RAM/SSD/GPU) lalu bandingkan dengan spek standar:\n"
            "    🔴 OFFLINE jika PC/agen mati\n"
            "    ✅ OK jika spek lengkap\n"
            "    ⚠️ TIDAK LENGKAP + rincian jika ada yang kurang\n\n"
            "<b>3. Melihat data:</b>\n"
            "<code>list</code> — daftar semua PC + spek + status + last seen\n"
            "<code>help</code> — tampilkan panduan ini\n\n"
            "<b>4. Tanya bebas (mode AI):</b>\n"
            "Ketik pertanyaan apa saja seputar data PC, mis.\n"
            "<i>\"PC mana yang tidak lengkap?\"</i> atau <i>\"kapan Pc Aula terakhir diperiksa?\"</i>\n\n"
            "<i>Contoh cepat:</i> <code>pc saharjo ok</code> atau <code>status pc aula</code>"
        ), thread_id)
        return

    # Perintah "status pc <nama>" / "status <nama>" -> pemeriksaan otomatis via agen.
    # Cek online/offline + bandingkan spek aktual vs standar, lalu catat ke riwayat.
    _status_name = None
    _looks_question = "?" in text or any(
        w in low.split() for w in ("apa", "mana", "siapa", "kapan", "berapa", "kenapa", "mengapa", "bagaimana", "gimana", "adakah", "apakah")
    )
    if not _looks_question:
        if low.startswith("status pc "):
            _status_name = text[len("status pc "):].strip()
        elif low.startswith("status "):
            _status_name = text[len("status "):].strip()
    if _status_name:
        try:
            r = requests.post(f"{API_URL}/check", json={
                "pc_name": _status_name,
                "record": True,
                "source": "telegram",
            }, timeout=30)
            if r.status_code == 404:
                send(chat_id, f"PC '<b>{_status_name}</b>' tidak terdaftar. Tambahkan dulu via web atau cek namanya.", thread_id)
                return
            d = r.json()
            if not d.get("ok"):
                send(chat_id, f"Gagal memeriksa: {d.get('error','unknown')}", thread_id)
                return
            st = d.get("status")
            nama = d.get("pc_name", _status_name)
            if st == "OFFLINE":
                msg = (
                    f"🔴 <b>{nama}</b> — OFFLINE\n"
                    f"{d.get('note','')}\n\n"
                    f"Status offline sudah dicatat, Bos."
                )
            elif st == "OK":
                msg = (
                    f"✅ <b>{nama}</b> — OK (lengkap)\n"
                    f"Spek aktual: {d.get('actual','-')}\n"
                    f"IP: {d.get('ip','-')} · diperiksa {d.get('last_seen','-')}\n\n"
                    f"Hasil pemeriksaan sudah dicatat, Bos."
                )
            else:  # TIDAK_LENGKAP
                detail = d.get("detail") or []
                detail_txt = "\n".join(f"  • {x}" for x in detail) if detail else f"  • {d.get('note','')}"
                msg = (
                    f"⚠️ <b>{nama}</b> — TIDAK LENGKAP\n"
                    f"{detail_txt}\n"
                    f"Spek aktual: {d.get('actual','-')}\n"
                    f"Spek standar: {d.get('spec_standar','-')}\n\n"
                    f"Hasil pemeriksaan sudah dicatat, Bos."
                )
            send(chat_id, msg, thread_id)
        except Exception as e:
            send(chat_id, f"Error memeriksa PC: {e}", thread_id)
        return

    # Deteksi kalimat tanya: rutekan ke mode AI, bukan perintah catat.
    # Contoh: "PC mana saja yang pakai monitor ASUS?", "pc apa yang tidak lengkap?"
    _question_words = ("apa", "mana", "siapa", "kapan", "berapa", "kenapa", "mengapa",
                       "bagaimana", "gimana", "adakah", "apakah", "yang mana")
    _is_question = "?" in text or any(low.startswith("pc " + w) or (" " + w + " ") in (" " + low + " ") for w in _question_words)

    if low.startswith("pc ") and not _is_question:
        rest = text[3:].strip()
        if not rest:
            send(chat_id, "Format: <code>pc &lt;nama&gt; ok</code> atau <code>pc &lt;nama&gt; &lt;catatan&gt;</code>", thread_id)
            return
        if rest.lower().endswith(" ok") or rest.lower() == "ok":
            pc_name = rest[:-3].strip() if rest.lower() != "ok" else ""
            status = "OK"
            note = ""
        else:
            parts = rest.split(maxsplit=1)
            pc_name = parts[0]
            note = parts[1] if len(parts) > 1 else ""
            status = "TIDAK_LENGKAP"

        if not pc_name:
            send(chat_id, "Format: <code>pc &lt;nama&gt; ok</code>", thread_id)
            return

        try:
            r = requests.post(f"{API_URL}/inspect", json={
                "pc_name": pc_name,
                "status": status,
                "note": note,
                "source": "telegram",
            }, timeout=20)
            data = r.json()
            if r.status_code == 404:
                send(chat_id, f"PC '<b>{pc_name}</b>' tidak ditemukan. Periksa nama atau tambahkan via web.", thread_id)
                return
            if data.get("ok"):
                send(chat_id, f"Tercatat: PC <b>{pc_name}</b> -> {status}" + (f"\nCatatan: {note}" if note else ""), thread_id)
            else:
                send(chat_id, f"Gagal mencatat: {data.get('error', 'unknown')}", thread_id)
        except Exception as e:
            send(chat_id, f"Error API: {e}", thread_id)
        return

    # Bukan perintah baku -> aktifkan mode AI (dibatasi data pemeriksaan PC)
    ai_answer(text, chat_id, thread_id)


SYSTEM_PROMPT = (
    f"Anda adalah {ASSISTANT_NAME}, asisten digital untuk {ORG_NAME}, "
    "khusus untuk topik PEMERIKSAAN/PEMANTAUAN UNIT PC.\n\n"
    "ATURAN KETAT:\n"
    "1. Anda HANYA boleh menjawab berdasarkan DATA PEMERIKSAAN PC yang diberikan di bawah. "
    "Dilarang mengarang, menebak, atau memakai pengetahuan di luar data tersebut.\n"
    "2. Jika pertanyaan di luar topik pemantauan PC (politik, cuaca, pengetahuan umum, "
    "atau urusan lain di luar data PC), tolak dengan sopan dan arahkan kembali ke topik pemeriksaan PC.\n"
    "3. Jika data yang diminta tidak ada, katakan apa adanya bahwa data belum tersedia.\n"
    f"4. Gunakan sapaan '{SAPAAN}'. Jawaban ringkas, rapi, HP-friendly (teks polos, boleh emoji ringan).\n"
    "5. Untuk waktu/tanggal, pakai apa adanya dari data.\n"
)


def ai_answer(question, chat_id, thread_id=None):
    """Mode AI fallback: jawab pertanyaan bebas, dibatasi pada data pemeriksaan PC."""
    if not (LLM_BASE_URL and LLM_API_KEY and LLM_MODEL):
        send(chat_id, (
            f"Maaf {SAPAAN}, perintah tidak dikenali. Ketik <code>help</code> untuk "
            "melihat daftar perintah, atau <code>list</code> untuk melihat data PC."
        ), thread_id)
        return
    # Ambil data lengkap sebagai konteks
    try:
        r = requests.get(f"{API_URL}/fulldata", timeout=20)
        data = r.json()
    except Exception as e:
        send(chat_id, f"Gagal mengambil data PC untuk mode AI: {e}", thread_id)
        return
    if not data.get("ok"):
        send(chat_id, "Data PC tidak tersedia untuk mode AI.", thread_id)
        return

    import json as _json
    konteks = _json.dumps(data, ensure_ascii=False, indent=1)
    user_content = (
        f"DATA PEMERIKSAAN PC (sumber tunggal kebenaran, waktu server {data.get('waktu_server','')}):\n"
        f"{konteks}\n\n"
        f"PERTANYAAN/PERINTAH PENGGUNA:\n{question}\n\n"
        "Jawab HANYA dari data di atas, sesuai aturan sistem."
    )
    import json as _json
    try:
        resp = requests.post(
            f"{LLM_BASE_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.2,
                "max_tokens": 1200,
                "stream": True,
            },
            timeout=120,
            stream=True,
        )
        if resp.status_code != 200:
            log.warning("LLM HTTP %s: %s", resp.status_code, resp.text[:300])
            send(chat_id, f"Maaf {SAPAAN}, mode AI sedang tidak tersedia. Silakan gunakan <code>list</code> atau <code>help</code>.", thread_id)
            return
        # Router mengembalikan SSE stream; kumpulkan delta content.
        # Paksa UTF-8 agar emoji tidak rusak (mojibake): tanpa ini requests
        # menebak Latin-1 saat server tidak mendeklarasikan charset.
        resp.encoding = "utf-8"
        chunks = []
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                continue
            line = raw.strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if line in ("", "[DONE]"):
                continue
            try:
                obj = _json.loads(line)
            except Exception:
                continue
            try:
                choices = obj.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                piece = delta.get("content")
                if piece is None:
                    # fallback: non-stream shape
                    piece = choices[0].get("message", {}).get("content")
                if piece:
                    chunks.append(piece)
            except Exception:
                continue
        answer = ("".join(chunks)).strip()
        if not answer:
            send(chat_id, f"Maaf {SAPAAN}, mode AI tidak mengembalikan jawaban.", thread_id)
            return
        # Telegram HTML aman: escape < & >
        safe = answer.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        send(chat_id, safe, thread_id)
    except Exception as e:
        log.exception("ai_answer error: %s", e)
        send(chat_id, f"Maaf {SAPAAN}, terjadi kendala pada mode AI: {e}", thread_id)



def main():
    if not TOKEN:
        log.error("TELEGRAM_BOT_TOKEN kosong. Isi di .env lalu restart service.")
        sys.exit(2)
    log.info("Poller started. API=%s chats=%s threads=%s", API_URL, ALLOWED_CHATS, ALLOWED_THREADS)
    offset = 0
    while True:
        try:
            params = {"timeout": 30, "offset": offset}
            r = requests.get(f"{TG}/getUpdates", params=params, timeout=40)
            payload = r.json()
            if not payload.get("ok"):
                log.error("getUpdates not ok: %s", payload)
                time.sleep(5)
                continue
            for upd in payload.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("channel_post")
                if not msg:
                    continue
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "")
                # Ekstrak thread_id dari pesan di forum/supergroup
                thread_id = (
                    msg.get("message_thread_id")
                    or msg.get("reply_to_message", {}).get("message_thread_id")
                    or None
                )

                # Filter: hanya chat yang diizinkan
                if ALLOWED_CHATS and chat_id not in ALLOWED_CHATS:
                    continue
                # Filter: hanya thread yang diizinkan (jika diset)
                if ALLOWED_THREADS and thread_id not in ALLOWED_THREADS:
                    continue

                log.info("Processing: chat=%s thread=%s text=%r", chat_id, thread_id, text[:80])
                try:
                    handle(text, chat_id, thread_id)
                except Exception as e:
                    log.exception("handler error: %s", e)
        except requests.exceptions.ConnectionError:
            log.warning("Connection error; retry in 5s")
            time.sleep(5)
        except Exception as e:
            log.exception("loop error: %s", e)
            time.sleep(5)

if __name__ == "__main__":
    main()
