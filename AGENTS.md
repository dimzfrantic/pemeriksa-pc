# AGENTS.md - Pemeriksaan PC Kantor Wilayah Kemenkum Jawa Barat

## Fokus Folder
Aplikasi pemantauan kelengkapan unit PC di lingkungan Kanwil Kemenkum Jabar.
`/home/ubnt/pc-monitor`

## Aturan Utama
1. Data live dari aplikasi ini saja; jangan ambil angka dari history chat.
2. Gunakan istilah `Kementerian Hukum` / `Kemenkum`.
3. Output ringkas, HP-friendly, operasional.
4. Mode AI HANYA boleh menjawab dari data pemeriksaan PC; tolak pertanyaan di luar topik.

## Sapaan
Untuk konteks folder ini (pemantauan PC, inspeksi unit, spek PC) DAN di topik Telegram "Pemeriksaan PC", gunakan sapaan:
`Bos`
(Catatan: berbeda dari domain dashboard pimpinan yang memakai `Pak Kakanwil`.)

## Arsitektur
- Web: Flask + SQLAlchemy + SQLite
- DB: `/home/ubnt/pc-monitor/instance/pcmonitor.db`
- Web service: systemd user `pc-monitor.service` (gunicorn, port 5080), auto-start (linger ubnt ON)
- Poller Telegram: systemd user `pc-monitor-tg.service` menjalankan `tg_poller.py` (AKTIF)

## Model Data
- `pcs`: name (unique), location, ram_sticks, ram_capacity_gb, ssd_count, ssd_capacity_gb,
  gpu_name (opsional), monitor_count, monitor_size_inch, monitor_brand (opsional), notes
- `inspections`: pc_id, inspected_at (WIB, datetime.now), status (OK / TIDAK_LENGKAP / OFFLINE),
  note, source (web/telegram/api/agent/auto-weekly)
- `pc_live`: snapshot agen terakhir (1 baris/PC): pc_name, ip, hostname, last_seen,
  ram_json, disk_json, gpu_json, agent_version. Online bila last_seen <= AGENT_OFFLINE_SECONDS (180s).
- Timestamp pakai waktu lokal WIB (datetime.now), bukan UTC.

## Pemeriksaan Otomatis via Agen (real-time)
- Agen Windows ringan di tiap PC (folder `/home/ubnt/pc-monitor/agent/`, zip: `pcmonitor-agent.zip`).
  Baca spek via PowerShell/WMI (RAM keping, disk SSD/HDD + kapasitas, GPU), lapor ke server tiap 60s
  (heartbeat, koneksi KELUAR -> aman dari firewall). Identitas pakai pc_name manual (bukan IP, aman utk DHCP).
  Pasang via `install_agent.bat` (Scheduled Task ONSTART, akun SYSTEM). Token = AGENT_TOKEN di .env.
- Server membandingkan spek AKTUAL (agen) vs STANDAR (tabel pcs) -> OK / TIDAK_LENGKAP, lihat `spec_compare.py`.
- Perintah Telegram `status pc <nama>` / `status <nama>`:
  offline -> "OFFLINE" + catat; online -> bandingkan spek -> "OK"/"TIDAK LENGKAP" + rincian, lalu catat.
  Kalimat tanya (ada "?"/kata tanya) tidak diperlakukan sebagai nama PC -> ke mode AI.
- Pemeriksaan otomatis mingguan: `weekly_check.py` (cron user Senin 08:00 WIB via `run_weekly_check.sh`),
  catat semua PC + kirim ringkasan ke topik Pemeriksaan PC via bot @pemeriksapc_bot (flag --send).
  Log: `weekly_check.log`.

## Rute Web
- `/` dashboard tabel semua PC + status pemeriksaan terakhir
- `/pc/` daftar PC; `/pc/add`; `/pc/<id>`; `/pc/<id>/edit`; `/pc/<id>/delete`
- `/inspection/add` catat pemeriksaan manual
- `/inspection/history` riwayat semua pemeriksaan
- Form web pakai CSRF token; blueprint API di-exempt dari CSRF.

## Rute API (dipakai poller Telegram)
- `POST /api/inspect` JSON `{pc_name, status, note, source}` -> catat pemeriksaan (404 bila PC tak ada)
- `GET  /api/status` ringkasan terkini semua PC
- `GET  /api/fulldata` data lengkap PC + riwayat (konteks untuk mode AI)

## Telegram (bot @pemeriksapc_bot)
- Token bot BARU khusus (BUKAN token Hermes/Sikumjabar) -> hindari 409 Conflict. Tersimpan di `/home/ubnt/pc-monitor/.env`.
- Hanya proses pesan dari grup "Ops TI Kemenkum Jabar" (chat -1003857568129) di topik "Pemeriksaan PC" (thread 587).
- Env: TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_CHAT_IDS=-1003857568129, TELEGRAM_ALLOWED_THREAD_IDS=587,
  PC_MONITOR_API_URL, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL.

### Perintah baku (cepat, tanpa AI)
- `pc <nama> ok` -> catat OK
- `pc <nama> <catatan>` -> catat TIDAK_LENGKAP + catatan (mis. "pc saharjo hilang ram")
- `list` / `/pclist` / `pc list` -> daftar PC + spek + status + waktu pemeriksaan (icon ✅/⚠️/▫️)
- `help` / `bantuan` / `/pchelp` -> panduan perintah

### Mode AI fallback
- Pesan yang tidak cocok perintah baku -> `ai_answer()` memanggil LLM (router mexia, model dari config Hermes)
  dengan konteks `/api/fulldata`.
- SYSTEM_PROMPT membatasi: hanya jawab dari data pemeriksaan PC, tolak di luar topik, sapaan "Bos", gaya ringkas.
- Router mexia mengembalikan SSE stream -> poller parse delta `choices[].delta.content` baris `data:`.
- Bila LLM gagal/kuota habis -> fallback pesan arahkan ke `list`/`help`.

## Integrasi dengan Hermes Gateway (Sikumjabar)
- `~/.hermes/.env`: `TELEGRAM_IGNORED_THREADS=2,587` -> Sikumjabar TIDAK merespon di topik Pemeriksaan PC (587).
- `gateway/run.py` (sebelum `_maybe_handle_telegram_incident_controls`): redirect pre-agent.
  Jika pesan diawali "pc " DAN thread BUKAN di TELEGRAM_IGNORED_THREADS -> balas arahan ke @pemeriksapc_bot,
  agar perintah "pc ..." di topik insiden tidak diproses Sikumjabar.
- Setelah edit gateway: `hermes gateway stop && hermes gateway start && hermes gateway status` (cek Main PID berubah).

## Batasan
- Jangan ubah/timpa token Hermes gateway.
- Jangan memindahkan folder ini tanpa update path service.
- Jangan hapus/migrate `instance/pcmonitor.db` tanpa backup.
- Menambah kolom PC: ALTER TABLE pcs + tambah field di model/form/detail/route + restart pc-monitor.service.
