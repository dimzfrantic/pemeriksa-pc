# PC Monitor Agent - Panduan (EXE, tanpa Python di tiap PC)

Agen ringan Windows. Membaca spek (RAM keping, SSD/HDD + kapasitas, GPU) lalu
melaporkan ke server pemeriksa-pc tiap 60 detik. Dipakai untuk perintah Telegram
`status pc <nama>` dan pemeriksaan otomatis mingguan.

Pola: build .exe via PyInstaller, config via `.env`, auto-start via registry Run
(tidak perlu hak admin).

> Catatan: semua nilai (IP, token, nama) pada contoh di bawah hanya CONTOH.

## Isi folder
- `agent.py` — kode agen (Python)
- `.env.example` — contoh konfigurasi (placeholder)
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
3. Salin `.env.example` menjadi `.env`, buka, lalu sesuaikan:
   - `AGENT_NAME` — sama persis dengan nama PC di aplikasi web (mis. `contoh1`).
   - `SERVER_URL` — alamat server, mis. `http://10.0.0.10:5080`. Pastikan PC dapat
     menjangkau alamat ini (1 jaringan / VPN).
   - `AGENT_TOKEN` — samakan dengan `AGENT_TOKEN` di `.env` server.
4. Klik dobel `install_agent.bat`.
   - Agen jalan, lapor sekali, dan memasang dirinya auto-start (registry Run).
5. Cek di server: ketik `status pc contoh1` di topik Telegram yang diizinkan.

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
- Agen v1.1+ mengirim waktu boot Windows (`boot_time`) agar server bisa mendeteksi
  setiap restart secara andal (untuk notifikasi perubahan/ketidaksesuaian spek saat PC nyala).
- Server menganggap PC OFFLINE bila tidak ada laporan > 3 menit.
- Auto-start pakai registry Run user (aktif setelah login Windows).
- Bila antivirus memblokir .exe PyInstaller: whitelist folder agen, atau pakai
  alternatif Python embeddable.

## Spek aktual vs standar
Server membandingkan spek aktual (dari agen) dengan spek STANDAR yang diisi di web
(jumlah keping RAM + kapasitas, jumlah SSD + kapasitas, GPU). Bila aktual kurang dari
standar -> status "TIDAK LENGKAP" + rincian. Pastikan spek standar tiap PC sudah benar.
