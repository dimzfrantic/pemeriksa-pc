# PC Monitor Agent - Panduan (EXE, tanpa Python di tiap PC)
Kementerian Hukum Jawa Barat

Agen ringan Windows. Membaca spek (RAM keping, SSD/HDD + kapasitas, GPU) lalu
melaporkan ke server pc-monitor tiap 60 detik. Dipakai untuk perintah Telegram
`status pc <nama>` dan pemeriksaan otomatis mingguan.

Mengikuti pola spybot windows-agent kantor: build .exe via PyInstaller,
config via `.env`, auto-start via registry Run (tidak perlu admin).

## Isi folder
- `agent.py` — kode agen (Python)
- `.env.example` — contoh konfigurasi (token sudah terisi)
- `build.bat` — build jadi .exe (dijalankan SEKALI di 1 PC ber-Python)
- `install_agent.bat` — pasang & jalankan agen di tiap PC (pakai .exe)
- `uninstall_agent.bat` — hentikan & hapus auto-start
- `requirements.txt`, `README.md`

## ALUR PEMAKAIAN (2 langkah besar)

### LANGKAH 1 — Build .exe SEKALI (di 1 PC Windows yang ada Python 3)
1. Pasang Python 3 di satu PC saja (https://python.org, centang "Add to PATH").
2. Salin folder `agent` ini ke PC tersebut.
3. Klik dobel `build.bat`. Tunggu sampai selesai.
4. Hasilnya: `dist\pcmonitor-agent.exe` (file mandiri, tidak perlu Python lagi).

### LANGKAH 2 — Sebar ke tiap PC (TANPA Python)
Di setiap PC yang mau dipantau:
1. Buat folder, mis. `C:\PCMonitorAgent`.
2. Salin ke sana: `pcmonitor-agent.exe`, `.env.example`, `install_agent.bat`, `uninstall_agent.bat`.
3. Salin `.env.example` menjadi `.env`, buka, ubah HANYA `AGENT_NAME` agar sama
   persis dengan nama PC di aplikasi web (mis. `Pc Aula`).
   - `SERVER_URL`: http://10.147.20.78:5080 (IP ZeroTier server). Pastikan PC bisa
     menjangkau IP ini (ZeroTier terpasang), atau ganti ke IP lokal server bila 1 jaringan.
   - `AGENT_TOKEN`: jangan diubah (sudah benar).
4. Klik dobel `install_agent.bat`.
   - Agen jalan, lapor sekali, dan memasang dirinya auto-start (registry Run).
5. Cek di server: ketik `status pc aula` di topik Telegram "Pemeriksaan PC".

## Uji manual (opsional)
Dobel-klik exe dengan argumen `once` lewat CMD:
```
pcmonitor-agent.exe once
```
Lihat hasil di `logs\pcmonitor-agent.log` -> baris `[ok] Lapor ... -> 200`.

## Menghapus agen
Dobel-klik `uninstall_agent.bat` (menghentikan proses + hapus auto-start).

## Catatan
- Agen hanya koneksi KELUAR ke server (tidak buka port di PC, aman dari firewall).
- Identitas pakai `AGENT_NAME` (manual), bukan IP -> aman walau IP DHCP berubah.
- Server menganggap PC OFFLINE bila tidak ada laporan > 3 menit.
- Auto-start pakai registry Run user (aktif setelah login Windows), sama seperti spybot.
- Bila antivirus memblokir .exe PyInstaller: whitelist folder agen, atau pakai
  alternatif Python embeddable (minta dibuatkan).

## Spek aktual vs standar
Server membandingkan spek aktual (dari agen) dengan spek STANDAR yang diisi di web
(jumlah keping RAM + kapasitas, jumlah SSD + kapasitas, GPU). Bila aktual kurang dari
standar -> status "TIDAK LENGKAP" + rincian. Pastikan spek standar tiap PC sudah benar.
