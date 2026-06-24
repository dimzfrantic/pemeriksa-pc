"""
PC Monitor Agent
================================================

Agen ringan untuk PC Windows. Membaca spek (RAM/SSD/HDD/GPU) lalu melaporkan
ke server pc-monitor tiap interval (heartbeat). Hanya koneksi KELUAR (aman dari firewall).

Konvensi:
- Config via .env di folder yang sama dengan exe (frozen-aware)
- Auto-start via registry Run HKCU (tidak perlu admin)
- Build .exe via PyInstaller --onefile --noconsole (build.bat)

Identitas PC pakai AGENT_NAME (dipatok manual di .env), agar cocok dengan
nama PC di database server (mis. "Pc Aula").
"""
import os
import sys
import json
import time
import socket
import subprocess
from pathlib import Path

import requests
from dotenv import load_dotenv

AGENT_VERSION = "1.0"

# Frozen-aware base dir (mendukung PyInstaller --onefile)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "pcmonitor-agent.log"

SERVER_URL = os.getenv("SERVER_URL", "http://10.0.0.10:5080").rstrip("/")
AGENT_NAME = os.getenv("AGENT_NAME", os.getenv("COMPUTERNAME", "windows-agent"))
AGENT_TOKEN = os.getenv("AGENT_TOKEN", "change-me")
INTERVAL_SECONDS = int(os.getenv("INTERVAL_SECONDS", "60"))
START_WITH_WINDOWS = os.getenv("START_WITH_WINDOWS", "true").lower() == "true"


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def add_to_startup():
    """Auto-start via registry Run HKCU."""
    if not START_WITH_WINDOWS:
        return
    try:
        import winreg
    except ImportError:
        return
    exe_path = os.path.realpath(sys.executable)
    # Saat frozen, sys.executable = path exe agen. Saat dev (python), lewati.
    if not getattr(sys, "frozen", False):
        return
    app_name = f"PCMonitorAgent_{AGENT_NAME}".replace(" ", "_")
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
        log(f"[startup] Registry Run terpasang: {app_name}")
    except Exception as e:
        log(f"[startup] Gagal pasang registry: {e}")


def _ps(cmd):
    """Jalankan PowerShell tanpa popup window, kembalikan stdout."""
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = 0x08000000  # CREATE_NO_WINDOW
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=30,
            startupinfo=startupinfo, creationflags=creationflags,
        )
        return out.stdout.strip()
    except Exception as e:
        log(f"[warn] PowerShell error: {e}")
        return ""


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return ""


def read_ram():
    raw = _ps("Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity | ConvertTo-Json -Compress")
    sticks, total = [], 0
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            for d in data:
                gb = round(int(d.get("Capacity", 0)) / (1024 ** 3))
                if gb > 0:
                    sticks.append({"size_gb": gb})
                    total += gb
        except Exception as e:
            log(f"[warn] parse RAM: {e}")
    return {"total_gb": total, "sticks": sticks}


def read_disks():
    raw = _ps("Get-PhysicalDisk | Select-Object FriendlyName, MediaType, Size | ConvertTo-Json -Compress")
    disks = []
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            for d in data:
                gb = round(int(d.get("Size", 0) or 0) / (1000 ** 3))
                media = str(d.get("MediaType", "") or "").upper()
                if "SSD" in media:
                    media = "SSD"
                elif "HDD" in media:
                    media = "HDD"
                else:
                    media = media or "UNKNOWN"
                disks.append({
                    "model": str(d.get("FriendlyName", "") or "").strip(),
                    "size_gb": gb,
                    "media": media,
                })
        except Exception as e:
            log(f"[warn] parse Disk: {e}")
    return disks


def read_gpus():
    raw = _ps("Get-CimInstance Win32_VideoController | Select-Object Name, AdapterCompatibility | ConvertTo-Json -Compress")
    gpus = []
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            for d in data:
                name = str(d.get("Name", "") or "").strip()
                vendor = str(d.get("AdapterCompatibility", "") or "").strip()
                low = (name + " " + vendor).lower()
                if any(k in low for k in ("intel", "uhd", "hd graphics", "amd radeon graphics", "vega")):
                    jenis = "integrated"
                elif any(k in low for k in ("nvidia", "geforce", "quadro", "radeon rx", "radeon pro")):
                    jenis = "dedicated"
                else:
                    jenis = "unknown"
                if name:
                    gpus.append({"name": name, "type": jenis, "vendor": vendor})
        except Exception as e:
            log(f"[warn] parse GPU: {e}")
    return gpus


def collect():
    return {"ram": read_ram(), "disks": read_disks(), "gpus": read_gpus()}


def report():
    payload = {
        "pc_name": AGENT_NAME,
        "hostname": socket.gethostname(),
        "ip": get_local_ip(),
        "agent_version": AGENT_VERSION,
    }
    payload.update(collect())
    url = SERVER_URL + "/api/agent/report"
    try:
        r = requests.post(url, json=payload, headers={"X-Agent-Token": AGENT_TOKEN}, timeout=20)
        if r.status_code == 200:
            log(f"[ok] Lapor {AGENT_NAME} -> 200")
            return True
        log(f"[err] HTTP {r.status_code}: {r.text[:160]}")
    except Exception as e:
        log(f"[err] Koneksi: {e}")
    return False


def main():
    log(f"PC Monitor Agent v{AGENT_VERSION} | PC={AGENT_NAME} | server={SERVER_URL} | tiap {INTERVAL_SECONDS}s")
    add_to_startup()
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        report()
        return
    while True:
        report()
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
