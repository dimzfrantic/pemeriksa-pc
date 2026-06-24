# pemeriksa-pc

Aplikasi pemantauan kelengkapan unit PC di lingkungan Kantor Wilayah Kementerian Hukum Jawa Barat. Mencatat dan memeriksa spek tiap PC (RAM, SSD/HDD, GPU, monitor), dengan pemeriksaan otomatis real-time lewat agen Windows dan kontrol penuh dari Telegram.

## Struktur repo

- `/` (root) — aplikasi web + server (Flask + SQLite), bot Telegram poller, pemeriksaan mingguan
- `agent/` — agen ringan untuk PC Windows (lapor spek ke server tiap menit)

## Fitur utama

- Dashboard web: daftar PC, spek standar, status pemeriksaan, status agen (online/IP/last seen)
- Tambah/edit PC dan input pemeriksaan manual lewat web
- Bot Telegram khusus topik "Pemeriksaan PC":
  - `pc <nama> ok` / `pc <nama> <catatan>` — catat hasil pemeriksaan manual
  - `status pc <nama>` — pemeriksaan otomatis via agen (online/offline + banding spek aktual vs standar)
  - `list` — daftar PC + spek + status, `help` — panduan
  - Pertanyaan bebas → mode AI yang dibatasi hanya data pemeriksaan PC
- Agen Windows: baca spek via WMI, lapor ke server (koneksi keluar, aman dari firewall), auto-start
- Pemeriksaan otomatis mingguan (Senin 08:00 WIB) + ringkasan terkirim ke Telegram
- Deteksi komponen hilang: bila spek aktual < standar → status TIDAK LENGKAP + rincian

## Arsitektur singkat

1. Server (Flask, port 5080) menyimpan master spek PC + riwayat pemeriksaan (SQLite).
2. Agen Windows di tiap PC mengirim heartbeat berisi spek aktual + IP tiap 60 detik (push, bukan pull) — aman untuk jaringan DHCP dan tanpa domain.
3. Bot Telegram (poller terpisah) menerima perintah di topik "Pemeriksaan PC" dan memanggil API server.
4. Server membandingkan spek AKTUAL (agen) dengan STANDAR (database) → OK / TIDAK LENGKAP / OFFLINE.

## Komponen utama

| File | Fungsi |
|------|--------|
| `app.py`, `wsgi.py` | Aplikasi Flask (app factory) |
| `models.py` | Model: PC, Inspection, PCLive |
| `routes/` | Web (dashboard, PC, inspeksi) + API (`/api/agent/report`, `/api/check`, dll) |
| `spec_compare.py` | Logika banding spek aktual vs standar |
| `tg_poller.py` | Bot Telegram poller + mode AI |
| `weekly_check.py` | Pemeriksaan otomatis mingguan |
| `agent/agent.py` | Agen Windows (baca spek + lapor) |

## Keamanan

Sebelum digunakan, ganti seluruh placeholder sensitif (lihat `.env.example`):

- `SECRET_KEY` — string acak panjang
- `TELEGRAM_BOT_TOKEN` — token bot Telegram khusus pemeriksaan PC
- `TELEGRAM_ALLOWED_CHAT_IDS`, `TELEGRAM_ALLOWED_THREAD_IDS` — grup/topik yang diizinkan
- `AGENT_TOKEN` — token rahasia laporan agen (samakan di server dan tiap agen)
- `LLM_*` — opsional, untuk mode AI

Jangan pernah commit `.env` riil ke repo. File `.env` dan database sudah diabaikan via `.gitignore`.

## Instalasi server (Ubuntu)

```bash
git clone git@github.com:dimzfrantic/pemeriksa-pc.git
cd pemeriksa-pc
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # lalu isi nilai sebenarnya
.venv/bin/gunicorn -w 2 -b 0.0.0.0:5080 wsgi:app
```

Akses dashboard di `http://<ip-server>:5080`.

### Jalankan sebagai service (systemd user)

Aplikasi web dan poller Telegram dijalankan sebagai dua service systemd user
(`pc-monitor.service` dan `pc-monitor-tg.service`). Aktifkan linger agar tetap
jalan setelah logout: `loginctl enable-linger $USER`.

### Pemeriksaan mingguan (cron)

```bash
# Senin 08:00 WIB
0 8 * * 1 /path/pemeriksa-pc/run_weekly_check.sh >> /path/pemeriksa-pc/weekly_check.log 2>&1
```

## Instalasi agen (PC Windows)

Lihat panduan lengkap di [`agent/README.md`](agent/README.md). Ringkasnya:

1. Build `.exe` sekali di satu PC ber-Python: jalankan `agent/build.bat` → `dist/pcmonitor-agent.exe`.
2. Sebar `.exe` + `.env` ke tiap PC, ubah `AGENT_NAME` sesuai nama PC, jalankan `install_agent.bat`.
3. Agen otomatis lapor tiap menit dan auto-start saat login Windows.

## Perintah Telegram (topik Pemeriksaan PC)

```
pc aula ok                 # catat Pc Aula lengkap
pc aula hilang ram         # catat tidak lengkap + catatan
status pc aula             # pemeriksaan otomatis via agen
list                       # daftar semua PC + status
help                       # panduan
```

## Catatan

- Server menganggap PC OFFLINE bila agen tidak melapor lebih dari `AGENT_OFFLINE_SECONDS` (default 3 menit).
- Identitas PC memakai `AGENT_NAME` (dipatok manual), bukan IP — aman walau IP DHCP berubah.
- Timestamp memakai waktu lokal server (WIB).
