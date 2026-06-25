# AGENTS.md — Panduan Proyek pemeriksa-pc

Catatan untuk asisten AI / developer yang bekerja pada repo ini. Semua nilai
(path, ID, IP, token, nama) di bawah bersifat CONTOH — sesuaikan dengan
lingkungan Anda sendiri.

## Tujuan
Aplikasi pemantauan kelengkapan unit PC pada sebuah instansi: mencatat spek
standar tiap PC, memeriksa spek aktual lewat agen, dan melaporkan status
(OK / TIDAK LENGKAP / OFFLINE) melalui web dan Telegram.

## Prinsip kerja
1. Data hanya diambil dari database aplikasi ini; jangan mengarang angka.
2. Output ke chat dibuat ringkas dan ramah layar HP.
3. Mode AI (opsional) hanya menjawab dari data pemeriksaan PC; tolak topik lain.

## Gaya sapaan
Pada konteks aplikasi ini, sapaan ke pengguna utama memakai panggilan informal
yang ditetapkan operator (mis. `Pimpinan`). Hindari memakai gelar jabatan riil.

## Tata letak kode
```
app.py / wsgi.py     aplikasi Flask (app factory)
config.py            konfigurasi dari .env
models.py            PC, Inspection, PCLive
routes/              web (dashboard/PC/inspeksi) + API
spec_compare.py      banding spek aktual vs standar
tg_poller.py         bot Telegram poller + mode AI
weekly_check.py      pemeriksaan otomatis terjadwal
agent/               agen Windows (baca spek + lapor)
```

## Model data (ringkas)
- `pcs` — master spek standar: nama (unik), lokasi, RAM (keping & kapasitas),
  SSD (jumlah & kapasitas), GPU, monitor, catatan.
- `inspections` — riwayat: pc_id, waktu, status, catatan, sumber.
- `pc_live` — snapshot agen terakhir (1 baris/PC): ip, hostname, last_seen,
  ram/disk/gpu (JSON), prev_fingerprint, was_online. Online bila last_seen <= ambang offline.

## Boot-check (deteksi perubahan saat PC nyala ulang)
- Pada transisi OFFLINE → ONLINE (heartbeat masuk setelah PC sempat offline),
  server bandingkan "sidik jari" spek sesi sebelumnya (`prev_fingerprint`) dengan yang baru.
- Bila beda → catat riwayat (sumber `boot-check`) + kirim notifikasi Telegram sekali,
  dengan label BERKURANG/BERTAMBAH dan perbandingan ke spek standar.
- Tidak membandingkan tiap heartbeat (anti-spam) dan tidak saat PC offline.
- Lihat `spec_compare.fingerprint()` / `spec_compare.diff_change()` dan `notifier.send_telegram()`.

## API internal (dipakai poller & agen)
- `POST /api/inspect` — catat pemeriksaan manual.
- `GET  /api/status` — ringkasan terkini semua PC.
- `GET  /api/fulldata` — data lengkap + riwayat (konteks mode AI).
- `POST /api/agent/report` — laporan heartbeat agen (butuh token).
- `POST /api/check` — pemeriksaan otomatis (online/offline + banding spek).

## Perintah Telegram
- `pc <nama> ok` / `pc <nama> <catatan>` — catat manual.
- `status pc <nama>` — pemeriksaan otomatis via agen.
- `list` — daftar PC + status. `help` — panduan.
- Kalimat tanya → mode AI (dibatasi data pemeriksaan PC).

## Konfigurasi (lihat .env.example)
Variabel penting: `SECRET_KEY`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_ALLOWED_CHAT_IDS`, `TELEGRAM_ALLOWED_THREAD_IDS`, `AGENT_TOKEN`,
`AGENT_OFFLINE_SECONDS`, dan `LLM_*` (opsional).

Contoh nilai (palsu): chat `-1001234567890`, thread `99`,
server `http://10.0.0.10:5080`, dijalankan dari `/opt/pemeriksa-pc`.

## Operasional
- Web dan poller dijalankan sebagai dua service systemd user.
- Pemeriksaan terjadwal via cron memanggil `run_weekly_check.sh`.
- Penambahan kolom PC: ubah model + form + halaman detail + route, lalu
  migrasi tabel dan restart service web.

## Batasan
- Jangan commit `.env` atau database ke repo.
- Token agen di server dan di tiap agen harus sama.
- Jangan hapus/migrasi database tanpa backup.
