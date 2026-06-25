# Pemeriksa-PC

Aplikasi pemantauan kelengkapan unit PC, mencatat dan memeriksa spek tiap PC (RAM, SSD/HDD, GPU, monitor), dengan pemeriksaan otomatis real-time lewat agen Windows dan kontrol penuh dari Telegram.

> Catatan: seluruh ID grup, IP, token, dan nama pada dokumentasi ini hanya CONTOH. Ganti dengan nilai milik Anda sendiri sebelum dipakai.

## Struktur repo

- `/` (root) — aplikasi web + server (Flask + SQLite), bot Telegram poller, pemeriksaan mingguan
- `agent/` — agen ringan untuk PC Windows (lapor spek ke server tiap menit)

## Fitur utama

- Dashboard web: daftar PC, spek standar, status pemeriksaan, status agen (online/IP/last seen)
- Tambah/edit PC dan input pemeriksaan manual lewat web
- Bot Telegram khusus satu topik forum:
  - `pc <nama> ok` / `pc <nama> <catatan>` — catat hasil pemeriksaan manual
  - `status pc <nama>` — pemeriksaan otomatis via agen (online/offline + banding spek aktual vs standar)
  - `list` — daftar PC + spek + status, `help` — panduan
  - Pertanyaan bebas → mode AI yang dibatasi hanya data pemeriksaan PC (opsional)
- Agen Windows: baca spek via WMI, lapor ke server (koneksi keluar, aman dari firewall), auto-start
- Deteksi perubahan saat PC nyala ulang (boot-check): saat PC kembali online, server (1) membandingkan spek fisik aktual dengan kondisi terakhir sebelum mati untuk mendeteksi komponen dicabut/ditambah (label BERKURANG/BERTAMBAH), dan (2) membandingkan spek aktual dengan spek standar — bila tidak sesuai, kirim notifikasi Telegram sekali (diam sampai kondisinya berubah). Keduanya dicatat ke riwayat.
- Pemeriksaan otomatis mingguan + ringkasan terkirim ke Telegram
- Deteksi komponen hilang: bila spek aktual < standar → status TIDAK LENGKAP + rincian

## Arsitektur singkat

1. Server (Flask, port 5080) menyimpan master spek PC + riwayat pemeriksaan (SQLite).
2. Agen Windows di tiap PC mengirim heartbeat berisi spek aktual + IP tiap 60 detik (push, bukan pull) — aman untuk jaringan DHCP dan tanpa domain.
3. Bot Telegram (poller terpisah) menerima perintah di satu topik forum dan memanggil API server.
4. Server membandingkan spek AKTUAL (agen) dengan STANDAR (database) → OK / TIDAK LENGKAP / OFFLINE.
5. Boot-check: pada transisi OFFLINE → ONLINE, server membandingkan "sidik jari" spek sesi nyala sebelumnya dengan yang baru. Bila berbeda, perubahan dicatat ke riwayat dan dikirim sekali ke Telegram. Perbandingan tidak dilakukan tiap heartbeat (anti-spam) dan tidak saat PC offline.

## Komponen utama

| File | Fungsi |
|------|--------|
| `app.py`, `wsgi.py` | Aplikasi Flask (app factory) |
| `models.py` | Model: PC, Inspection, PCLive |
| `routes/` | Web (dashboard, PC, inspeksi) + API (`/api/agent/report`, `/api/check`, dll) |
| `spec_compare.py` | Logika banding spek aktual vs standar |
| `tg_poller.py` | Bot Telegram poller + mode AI |
| `notifier.py` | Kirim notifikasi ke topik Telegram (boot-check) |
| `weekly_check.py` | Pemeriksaan otomatis mingguan |
| `agent/agent.py` | Agen Windows (baca spek + lapor) |

## Keamanan

Sebelum digunakan, ganti seluruh placeholder sensitif (lihat `.env.example`):

- `SECRET_KEY` — string acak panjang
- `TELEGRAM_BOT_TOKEN` — token bot Telegram khusus aplikasi ini
- `TELEGRAM_ALLOWED_CHAT_IDS`, `TELEGRAM_ALLOWED_THREAD_IDS` — grup/topik yang diizinkan
- `AGENT_TOKEN` — token rahasia laporan agen (samakan di server dan tiap agen)
- `LLM_*` — opsional, untuk mode AI

Jangan pernah commit `.env` riil ke repo. File `.env` dan database sudah diabaikan via `.gitignore`.

## Instalasi server (Linux)

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
# Contoh: tiap Senin 08:00
0 8 * * 1 /opt/pemeriksa-pc/run_weekly_check.sh >> /opt/pemeriksa-pc/weekly_check.log 2>&1
```

## Instalasi agen (PC Windows)

Lihat panduan lengkap di [`agent/README.md`](agent/README.md). Ringkasnya:

1. Build `.exe` sekali di satu PC ber-Python: jalankan `agent/build.bat` → `dist/pcmonitor-agent.exe`.
2. Sebar `.exe` + `.env` ke tiap PC, ubah `AGENT_NAME` sesuai nama PC, jalankan `install_agent.bat`.
3. Agen otomatis lapor tiap menit dan auto-start saat login Windows.

## Perintah Telegram (di topik yang diizinkan)

```
pc contoh1 ok              # catat PC "contoh1" lengkap
pc contoh1 hilang ram      # catat tidak lengkap + catatan
status pc contoh1          # pemeriksaan otomatis via agen
list                       # daftar semua PC + status
help                       # panduan
```

## Catatan

- Server menganggap PC OFFLINE bila agen tidak melapor lebih dari `AGENT_OFFLINE_SECONDS` (default 3 menit).
- Identitas PC memakai `AGENT_NAME` (dipatok manual), bukan IP — aman walau IP DHCP berubah.
- Timestamp memakai waktu lokal server.

## Lisensi

Internal / sesuai kebijakan pemilik repo.
