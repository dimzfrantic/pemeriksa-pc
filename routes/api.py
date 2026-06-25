import datetime as _dt
import json as _json
from flask import Blueprint, request, jsonify, abort, current_app
from extensions import db
from models import PC, Inspection, PCLive
import spec_compare
import notifier

api_bp = Blueprint("api", __name__)


def _find_pc(name):
    """Cari PC berdasarkan nama persis atau case-insensitive contains."""
    name = (name or "").strip()
    if not name:
        return None
    pc = PC.query.filter_by(name=name).first()
    if pc:
        return pc
    # Cari yang mengandung nama tsb (lower) jika nama unik
    lowered = name.lower()
    matches = [p for p in PC.query.all() if lowered in p.name.lower()]
    return matches[0] if len(matches) == 1 else None


@api_bp.post("/inspect")
def inspect():
    """Endpoint yang dipakai poller Telegram untuk mencatat hasil pemeriksaan.
    Body JSON: {"pc_name": str, "status": "OK"|"TIDAK_LENGKAP", "note": str, "source": str}
    Bila pc_name tidak ditemukan, balas 404 supaya poller tahu.
    """
    data = request.get_json(silent=True) or {}
    pc_name = (data.get("pc_name") or "").strip()
    status = (data.get("status") or "OK").upper()
    note = (data.get("note") or "").strip()
    source = (data.get("source") or "telegram").strip()

    if status not in ("OK", "TIDAK_LENGKAP"):
        status = "OK"

    pc = _find_pc(pc_name)
    if not pc:
        return jsonify(ok=False, error="PC_NOT_FOUND", pc_name=pc_name), 404

    inp = Inspection(pc_id=pc.id, status=status, note=note, source=source)
    db.session.add(inp)
    db.session.commit()
    return jsonify(ok=True, pc_id=pc.id, pc_name=pc.name, status=status, inspection_id=inp.id)


@api_bp.get("/status")
def status():
    """Ringkasan terkini semua PC (dipakai poller untuk perintah /pclist)."""
    pcs = PC.query.order_by(PC.name.asc()).all()
    out = []
    for pc in pcs:
        latest = pc.latest_inspection
        out.append({
            "id": pc.id,
            "name": pc.name,
            "status": latest.status if latest else "BELUM",
            "note": latest.note if latest else "",
            "inspected_at": (latest.inspected_at.isoformat() if latest and latest.inspected_at else None),
            "spec": pc.spec_text,
        })
    return jsonify(ok=True, total=len(out), items=out)


@api_bp.get("/fulldata")
def fulldata():
    """Data lengkap semua PC + riwayat pemeriksaan, dipakai sebagai konteks AI."""
    pcs = PC.query.order_by(PC.name.asc()).all()
    out = []
    for pc in pcs:
        latest = pc.latest_inspection
        history = []
        for inp in pc.inspections[:30]:  # batasi 30 riwayat terakhir per PC
            history.append({
                "waktu": inp.inspected_at.strftime("%Y-%m-%d %H:%M") if inp.inspected_at else None,
                "status": inp.status,
                "catatan": inp.note or "",
                "sumber": inp.source,
            })
        out.append({
            "nama": pc.name,
            "lokasi": pc.location or "",
            "spek_standar": pc.spec_text,
            "ram": f"{pc.ram_sticks} keping x {pc.ram_capacity_gb} GB",
            "ssd": f"{pc.ssd_count} x {pc.ssd_capacity_gb} GB",
            "gpu": pc.gpu_name or "tidak ada",
            "monitor": f"{pc.monitor_count} x {pc.monitor_size_inch} inch" + (f" {pc.monitor_brand}" if pc.monitor_brand else ""),
            "catatan_unit": pc.notes or "",
            "status_terkini": latest.status if latest else "BELUM DIPERIKSA",
            "catatan_terkini": latest.note if latest else "",
            "diperiksa_terakhir": latest.inspected_at.strftime("%Y-%m-%d %H:%M") if latest and latest.inspected_at else "belum pernah",
            "jumlah_pemeriksaan": len(pc.inspections),
            "riwayat_pemeriksaan": history,
        })
    return jsonify(ok=True, total=len(out), waktu_server=_dt.datetime.now().strftime("%Y-%m-%d %H:%M"), pcs=out)


@api_bp.post("/agent/report")
def agent_report():
    """Terima laporan heartbeat dari agen Windows di tiap PC.

    Header: X-Agent-Token: <token>  (atau body field 'token')
    Body JSON: {
      "pc_name": "Pc Aula",
      "hostname": "DESKTOP-XXX",
      "ip": "172.16.1.23",
      "agent_version": "1.0",
      "ram": {"total_gb":16, "sticks":[{"size_gb":8},{"size_gb":8}]},
      "disks": [{"model":"...","size_gb":512,"media":"SSD"}],
      "gpus": [{"name":"Intel UHD 630","type":"integrated"}]
    }
    """
    expected = (current_app.config.get("AGENT_TOKEN") or "").strip()
    sent = (request.headers.get("X-Agent-Token") or "").strip()
    data = request.get_json(silent=True) or {}
    if not sent:
        sent = (data.get("token") or "").strip()
    if not expected or sent != expected:
        return jsonify(ok=False, error="UNAUTHORIZED"), 401

    pc_name = (data.get("pc_name") or "").strip()
    if not pc_name:
        return jsonify(ok=False, error="PC_NAME_REQUIRED"), 400

    offline_secs = int(current_app.config.get("AGENT_OFFLINE_SECONDS", 180))
    now = _dt.datetime.now()

    live = PCLive.query.filter_by(pc_name=pc_name).first()

    # Snapshot LAMA (sebelum ditimpa) untuk deteksi perubahan saat nyala ulang
    old_snapshot = None
    was_offline_before = True
    prev_fp = ""
    if live:
        old_snapshot = {
            "ram_json": live.ram_json,
            "disk_json": live.disk_json,
            "gpu_json": live.gpu_json,
        }
        # Dianggap "baru nyala" bila status tercatat offline ATAU laporan terakhir sudah basi
        was_offline_before = (not live.was_online) or (not live.is_online(offline_secs))
        prev_fp = live.prev_fingerprint or ""
    else:
        live = PCLive(pc_name=pc_name)
        db.session.add(live)

    new_fp = spec_compare.fingerprint(
        data.get("ram") and _json.dumps(data.get("ram")) or "",
        data.get("disks") and _json.dumps(data.get("disks")) or "",
        data.get("gpus") and _json.dumps(data.get("gpus")) or "",
    )

    # === BOOT-CHECK: deteksi perubahan spek saat PC baru menyala ===
    # Hanya saat transisi OFFLINE -> ONLINE, dan hanya bila ada acuan sesi sebelumnya.
    if was_offline_before and prev_fp and prev_fp != new_fp and old_snapshot is not None:
        new_snapshot = {
            "ram_json": _json.dumps(data.get("ram") or {}, ensure_ascii=False),
            "disk_json": _json.dumps(data.get("disks") or [], ensure_ascii=False),
            "gpu_json": _json.dumps(data.get("gpus") or [], ensure_ascii=False),
        }
        changes = spec_compare.diff_change(old_snapshot, new_snapshot)
        if changes:
            # Catat ke riwayat
            pc_master = _find_pc(pc_name)
            note = "Perubahan saat PC nyala ulang: " + "; ".join(changes)
            if pc_master:
                db.session.add(Inspection(
                    pc_id=pc_master.id, status="TIDAK_LENGKAP" if any("BERKURANG" in c for c in changes) else "OK",
                    note=note, source="boot-check",
                ))
            # Kirim notifikasi Telegram (sekali, di momen nyala)
            org = current_app.config.get("ORG_NAME", "Instansi")
            detail = "\n".join(f"• {c}" for c in changes)
            cmp_extra = ""
            if pc_master:
                _shim = type("S", (), {
                    "ram_json": new_snapshot["ram_json"],
                    "disk_json": new_snapshot["disk_json"],
                    "gpu_json": new_snapshot["gpu_json"],
                })()
                st, kurang = spec_compare.compare(pc_master, _shim)
                if kurang:
                    cmp_extra = "\n\nDibanding spek standar:\n" + "\n".join(f"• {k}" for k in kurang)
            notifier.send_telegram(
                f"⚠️ <b>{pc_name}</b> menyala dengan perubahan spek\n{detail}{cmp_extra}\n\n"
                f"Waktu: {now.strftime('%Y-%m-%d %H:%M')} · {org}"
            )

    # Simpan/timpa snapshot terkini
    live.hostname = (data.get("hostname") or "").strip()
    live.ip = (data.get("ip") or "").strip()
    live.agent_version = (data.get("agent_version") or "").strip()
    live.last_seen = now
    live.ram_json = _json.dumps(data.get("ram") or {}, ensure_ascii=False)
    live.disk_json = _json.dumps(data.get("disks") or [], ensure_ascii=False)
    live.gpu_json = _json.dumps(data.get("gpus") or [], ensure_ascii=False)
    live.prev_fingerprint = new_fp
    live.was_online = True
    db.session.commit()
    return jsonify(ok=True, pc_name=pc_name, last_seen=live.last_seen.isoformat())


@api_bp.post("/check")
def check():
    """Pemeriksaan otomatis berbasis agen untuk perintah Telegram 'status pc ...'.

    Body JSON: {"pc_name": str, "record": bool, "source": str}
    - Cek apakah PC terdaftar (master spek)
    - Cek snapshot agen terakhir (PCLive): online/offline
    - Jika online: bandingkan spek aktual vs standar -> OK / TIDAK_LENGKAP
    - Jika record=True: catat hasil ke riwayat Inspection
    Mengembalikan status + pesan siap-kirim.
    """
    data = request.get_json(silent=True) or {}
    pc_name = (data.get("pc_name") or "").strip()
    do_record = bool(data.get("record", True))
    source = (data.get("source") or "agent").strip()

    pc = _find_pc(pc_name)
    if not pc:
        return jsonify(ok=False, error="PC_NOT_FOUND", pc_name=pc_name), 404

    live = PCLive.query.filter_by(pc_name=pc.name).first()
    offline_secs = int(current_app.config.get("AGENT_OFFLINE_SECONDS", 180))

    # OFFLINE bila tidak ada agen atau laporan basi
    if not live or not live.is_online(offline_secs):
        last = live.last_seen.strftime("%Y-%m-%d %H:%M") if (live and live.last_seen) else "belum pernah lapor"
        status = "OFFLINE"
        note = f"Agen tidak aktif (laporan terakhir: {last})"
        if do_record:
            db.session.add(Inspection(pc_id=pc.id, status=status, note=note, source=source))
            db.session.commit()
        return jsonify(
            ok=True, pc_name=pc.name, status=status, online=False,
            note=note, detail=[], actual="", spec_standar=pc.spec_text,
        )

    # ONLINE -> bandingkan spek
    cmp_status, kekurangan = spec_compare.compare(pc, live)
    actual = spec_compare.summarize_actual(live)
    note = "; ".join(kekurangan) if kekurangan else "Spek sesuai standar"
    if do_record:
        db.session.add(Inspection(pc_id=pc.id, status=cmp_status, note=note, source=source))
        db.session.commit()
    return jsonify(
        ok=True, pc_name=pc.name, status=cmp_status, online=True,
        note=note, detail=kekurangan, actual=actual,
        spec_standar=pc.spec_text, ip=live.ip,
        last_seen=live.last_seen.strftime("%Y-%m-%d %H:%M"),
    )