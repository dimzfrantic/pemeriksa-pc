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
  SSD (jumlah & kapasitas), HDD (kapasitas tiap unit via `hdd_capacities` CSV, mis. "500,1000"; 0/kosong = tidak wajib), GPU, monitor, catatan.
- `inspections` — riwayat: pc_id, waktu, status, catatan, sumber.
- `pc_live` — snapshot agen terakhir (1 baris/PC): ip, hostname, last_seen,
  ram/disk/gpu (JSON), prev_fingerprint, was_online. Online bila last_seen <= ambang offline.

## Boot-check (deteksi perubahan saat PC nyala ulang)
- Pemicu boot: agen (v1.1+) mengirim `boot_time` (LastBootUpTime Windows). Server
  menjalankan boot-check saat `boot_time` berubah dari yang tersimpan (`last_boot_time`).
  Ini andal untuk restart cepat dan tahan terhadap jaringan yang telat siap saat startup.
  Fallback ke transisi OFFLINE→ONLINE bila agen lama belum kirim `boot_time`.
- Saat boot, server menjalankan dua pemeriksaan:
  1. **Boot-check fisik** — bandingkan "sidik jari" spek aktual sesi sebelumnya
     (`prev_fingerprint`) dengan yang baru. Deteksi komponen benar-benar berubah
     (RAM/SSD/HDD/GPU dicabut/ditambah), dengan label BERKURANG/BERTAMBAH.
  2. **Boot compliance check** — bandingkan spek aktual vs spek STANDAR (tabel pcs).
     Notif SEKALI saat status kepatuhan berubah: OK→TIDAK_LENGKAP ("⚠️ tidak sesuai standar")
     maupun TIDAK_LENGKAP→OK ("✅ pulih/sudah sesuai"). Status disimpan di `last_compliance`
     (anti-spam: diam selama status tidak berubah). Menangkap kasus standar diubah lalu PC di-restart.
- Keduanya catat riwayat (sumber `boot-check`) + kirim notifikasi Telegram.
- Pemeriksaan hanya saat boot (bukan tiap heartbeat), jadi tidak spam.
- Lihat `spec_compare.fingerprint()` / `diff_change()` / `compare()` dan `notifier.send_telegram()`.

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
