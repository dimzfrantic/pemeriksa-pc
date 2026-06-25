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

    # --- HDD (hanya dicek bila standar mensyaratkan HDD) ---
    hdd = [d for d in disks if str(d.get("media", "")).upper() == "HDD"]
    actual_hdd_caps = sorted((int(d.get("size_gb", 0)) for d in hdd), reverse=True)
    std_hdd_caps = sorted((getattr(pc, "hdd_list", None) or []), reverse=True)

    if std_hdd_caps:
        if len(actual_hdd_caps) < len(std_hdd_caps):
            kekurangan.append(
                f"HDD kurang: aktual {len(actual_hdd_caps)} unit dari standar {len(std_hdd_caps)} unit"
            )
        else:
            # Cocokkan tiap HDD standar (terbesar->terkecil) dengan HDD aktual.
            sisa = list(actual_hdd_caps)
            for need in std_hdd_caps:
                # cari HDD aktual yang kapasitasnya >= kebutuhan
                match = next((c for c in sisa if c >= need), None)
                if match is None:
                    kekurangan.append(
                        f"HDD kurang: tidak ada unit >= {need}GB (standar: {'+'.join(str(c)+'GB' for c in std_hdd_caps)})"
                    )
                    break
                sisa.remove(match)

    # --- GPU ---
    gpus = _parse(live.gpu_json) or []
    std_gpu = (pc.gpu_name or "").strip()
    if std_gpu and not gpus:
        kekurangan.append(f"GPU tidak terbaca (standar: {std_gpu})")
    status = "TIDAK_LENGKAP" if kekurangan else "OK"
    return status, kekurangan


def _ram_summary(ram):
    sticks = ram.get("sticks") or []
    total = ram.get("total_gb") or sum(int(x.get("size_gb", 0)) for x in sticks)
    return len(sticks), int(total or 0)


def _disk_summary(disks):
    ssd = [d for d in disks if str(d.get("media", "")).upper() == "SSD"]
    hdd = [d for d in disks if str(d.get("media", "")).upper() == "HDD"]
    return (
        len(ssd), sum(int(d.get("size_gb", 0)) for d in ssd),
        len(hdd), sum(int(d.get("size_gb", 0)) for d in hdd),
    )


def fingerprint(ram_json, disk_json, gpu_json):
    """Sidik jari spek dari JSON mentah. Dipakai deteksi perubahan antar sesi nyala.

    Bentuk: 'RAM:2x16|SSD:2u/1024|HDD:1u/1000|GPU:Intel UHD 630'
    (jumlah keping x total RAM | jumlah & total SSD | jumlah & total HDD | nama GPU urut)
    """
    ram = _parse(ram_json) or {}
    disks = _parse(disk_json) or []
    gpus = _parse(gpu_json) or []
    sc, rt = _ram_summary(ram)
    ss, sst, hc, hct = _disk_summary(disks)
    gnames = "+".join(sorted(g.get("name", "?") for g in gpus)) if gpus else "-"
    return f"RAM:{sc}x{rt}|SSD:{ss}u/{sst}|HDD:{hc}u/{hct}|GPU:{gnames}"


def diff_change(old_json, new_json):
    """Bandingkan dua snapshot (lama vs baru) -> daftar perubahan berlabel.

    old_json / new_json: dict berisi {"ram_json","disk_json","gpu_json"}.
    Mengembalikan list string, mis. ["RAM BERKURANG: 16GB -> 8GB (-8GB, 2 -> 1 keping)"].
    Kosong bila tidak ada perubahan terdeteksi.
    """
    changes = []
    old_ram = _parse(old_json.get("ram_json")) or {}
    new_ram = _parse(new_json.get("ram_json")) or {}
    o_sc, o_rt = _ram_summary(old_ram)
    n_sc, n_rt = _ram_summary(new_ram)
    if o_rt != n_rt or o_sc != n_sc:
        arah = "BERTAMBAH" if n_rt > o_rt else "BERKURANG"
        selisih = n_rt - o_rt
        changes.append(
            f"RAM {arah}: {o_rt}GB -> {n_rt}GB ({selisih:+d}GB, {o_sc} -> {n_sc} keping)"
        )

    old_disks = _parse(old_json.get("disk_json")) or []
    new_disks = _parse(new_json.get("disk_json")) or []
    o_ss, o_sst, o_hc, o_hct = _disk_summary(old_disks)
    n_ss, n_sst, n_hc, n_hct = _disk_summary(new_disks)
    if o_ss != n_ss or o_sst != n_sst:
        arah = "BERTAMBAH" if n_sst > o_sst else "BERKURANG"
        changes.append(
            f"SSD {arah}: {o_ss} unit/{o_sst}GB -> {n_ss} unit/{n_sst}GB"
        )
    if o_hc != n_hc or o_hct != n_hct:
        arah = "BERTAMBAH" if n_hct > o_hct else "BERKURANG"
        changes.append(
            f"HDD {arah}: {o_hc} unit/{o_hct}GB -> {n_hc} unit/{n_hct}GB"
        )

    old_gpus = sorted(g.get("name", "?") for g in (_parse(old_json.get("gpu_json")) or []))
    new_gpus = sorted(g.get("name", "?") for g in (_parse(new_json.get("gpu_json")) or []))
    if old_gpus != new_gpus:
        changes.append(
            f"GPU BERUBAH: [{', '.join(old_gpus) or '-'}] -> [{', '.join(new_gpus) or '-'}]"
        )
    return changes
