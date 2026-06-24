"""Logika perbandingan spek AKTUAL (dari agen) vs spek STANDAR (database PC).

Dipakai oleh:
- endpoint /api/agent/report (opsional, untuk info)
- perintah Telegram "status pc ..."
- cron pemeriksaan mingguan

Kebijakan perbandingan:
- RAM: total kapasitas aktual >= total standar (sticks x capacity) DAN jumlah keping aktual >= standar
- SSD: jumlah disk SSD aktual >= ssd_count standar DAN total kapasitas SSD aktual >= ssd_count x ssd_capacity
- GPU: jika standar punya gpu_name, minimal ada 1 GPU terbaca (pencocokan nama longgar)
Selisih KURANG -> TIDAK_LENGKAP. Jika lebih dari standar -> tetap OK (dianggap upgrade).
"""
import json


def _parse(s):
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def summarize_actual(live):
    """Ringkas spek aktual dari PCLive jadi teks singkat untuk laporan."""
    parts = []
    ram = _parse(live.ram_json) or {}
    sticks = ram.get("sticks") or []
    total_ram = ram.get("total_gb") or sum(int(x.get("size_gb", 0)) for x in sticks)
    if sticks:
        parts.append(f"RAM {len(sticks)} keping = {total_ram}GB")
    elif total_ram:
        parts.append(f"RAM {total_ram}GB")

    disks = _parse(live.disk_json) or []
    ssd = [d for d in disks if str(d.get("media", "")).upper() == "SSD"]
    hdd = [d for d in disks if str(d.get("media", "")).upper() == "HDD"]
    if ssd:
        cap = sum(int(d.get("size_gb", 0)) for d in ssd)
        parts.append(f"SSD {len(ssd)} unit = {cap}GB")
    if hdd:
        cap = sum(int(d.get("size_gb", 0)) for d in hdd)
        parts.append(f"HDD {len(hdd)} unit = {cap}GB")

    gpus = _parse(live.gpu_json) or []
    if gpus:
        names = ", ".join(g.get("name", "?") for g in gpus)
        parts.append(f"GPU: {names}")
    return " | ".join(parts) if parts else "(spek aktual belum terbaca)"


def compare(pc, live):
    """Bandingkan spek aktual (PCLive) vs standar (PC).

    Mengembalikan (status, detail_list) di mana status = "OK" / "TIDAK_LENGKAP".
    detail_list berisi keterangan kekurangan (kosong bila OK).
    """
    kekurangan = []

    # --- RAM ---
    ram = _parse(live.ram_json) or {}
    sticks = ram.get("sticks") or []
    actual_stick_count = len(sticks)
    actual_ram_total = ram.get("total_gb") or sum(int(x.get("size_gb", 0)) for x in sticks)
    std_stick_count = pc.ram_sticks or 0
    std_ram_total = (pc.ram_sticks or 0) * (pc.ram_capacity_gb or 0)

    if actual_ram_total and std_ram_total and actual_ram_total < std_ram_total:
        kekurangan.append(
            f"RAM kurang: aktual {actual_ram_total}GB dari standar {std_ram_total}GB"
        )
    elif actual_stick_count and std_stick_count and actual_stick_count < std_stick_count:
        kekurangan.append(
            f"Keping RAM kurang: aktual {actual_stick_count} dari standar {std_stick_count} keping"
        )

    # --- SSD ---
    disks = _parse(live.disk_json) or []
    ssd = [d for d in disks if str(d.get("media", "")).upper() == "SSD"]
    actual_ssd_count = len(ssd)
    actual_ssd_total = sum(int(d.get("size_gb", 0)) for d in ssd)
    std_ssd_count = pc.ssd_count or 0
    std_ssd_total = (pc.ssd_count or 0) * (pc.ssd_capacity_gb or 0)

    if std_ssd_count and actual_ssd_count < std_ssd_count:
        kekurangan.append(
            f"SSD kurang: aktual {actual_ssd_count} unit dari standar {std_ssd_count} unit"
        )
    elif std_ssd_total and actual_ssd_total and actual_ssd_total < std_ssd_total:
        kekurangan.append(
            f"Kapasitas SSD kurang: aktual {actual_ssd_total}GB dari standar {std_ssd_total}GB"
        )

    # --- GPU ---
    gpus = _parse(live.gpu_json) or []
    std_gpu = (pc.gpu_name or "").strip()
    if std_gpu and not gpus:
        kekurangan.append(f"GPU tidak terbaca (standar: {std_gpu})")

    status = "TIDAK_LENGKAP" if kekurangan else "OK"
    return status, kekurangan
