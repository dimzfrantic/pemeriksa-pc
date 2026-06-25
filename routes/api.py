import datetime as _dt
import json as _json
from flask import Blueprint, request, jsonify, abort, current_app
from extensions import db
from models import PC, Inspection, PCLive
import spec_compare
import notifier

api_bp = Blueprint("api", __name__)


def _norm(s):
    """Normalisasi nama untuk pencocokan: lower, rapikan spasi, buang prefix 'pc'."""
    s = " ".join((s or "").strip().lower().split())
    if s.startswith("pc "):
        s = s[3:].strip()
    return s


def _find_pc(name):
    """Cari PC dengan beberapa strategi berurutan (toleran besar/kecil & prefix 'Pc').

    Urutan: (1) cocok persis case-insensitive, (2) cocok setelah normalisasi
    (abaikan prefix 'Pc'/spasi), (3) cocok kata utuh unik, (4) 'mengandung' unik.
    Mengembalikan PC bila satu kandidat jelas; None bila tidak ada atau ambigu.
    """
    name = (name or "").strip()
    if not name:
        return None

    all_pcs = PC.query.all()

    # 1) Persis (case-insensitive)
    low = name.lower()
    for p in all_pcs:
        if p.name.lower() == low:
            return p

    # 2) Normalisasi (abaikan prefix 'Pc' dan spasi berlebih) — harus tepat sama
    target = _norm(name)
    norm_matches = [p for p in all_pcs if _norm(p.name) == target]
    if len(norm_matches) == 1:
        return norm_matches[0]
    if len(norm_matches) > 1:
        return None  # ambigu

    # 3) Cocok sebagai kata utuh (mis. "aula" cocok "Pc Aula", tidak ke "Pc Aula2")
    import re as _re
    word_matches = [
        p for p in all_pcs
        if _re.search(r"\b" + _re.escape(target) + r"\b", _norm(p.name))
    ]
    if len(word_matches) == 1:
        return word_matches[0]
    if len(word_matches) > 1:
        return None  # ambigu

    # 4) 'Mengandung' — hanya bila unik
    contains = [p for p in all_pcs if target and target in _norm(p.name)]
    return contains[0] if len(contains) == 1 else None


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
    new_boot_time = (data.get("boot_time") or "").strip()

    live = PCLive.query.filter_by(pc_name=pc_name).first()

    # Snapshot LAMA (sebelum ditimpa) untuk deteksi perubahan saat nyala ulang
    old_snapshot = None
    prev_fp = ""
    prev_boot = ""
    offline_transition = True
    if live:
        old_snapshot = {
            "ram_json": live.ram_json,
            "disk_json": live.disk_json,
            "gpu_json": live.gpu_json,
        }
        prev_fp = live.prev_fingerprint or ""
        prev_boot = (live.last_boot_time or "").strip()
        offline_transition = (not live.was_online) or (not live.is_online(offline_secs))
    else:
        live = PCLive(pc_name=pc_name)
        db.session.add(live)

    # "Baru boot" = waktu boot Windows berubah (andal, tak tergantung lama mati).
    # Bila agen belum mengirim boot_time (versi lama), fallback ke transisi offline.
    if new_boot_time:
        is_boot = (new_boot_time != prev_boot)
    else:
        is_boot = offline_transition
    was_offline_before = is_boot  # nama lama dipakai di blok-blok berikut

    new_fp = spec_compare.fingerprint(
        data.get("ram") and _json.dumps(data.get("ram")) or "",
        data.get("disks") and _json.dumps(data.get("disks")) or "",
        data.get("gpus") and _json.dumps(data.get("gpus")) or "",
    )

    # === BOOT-CHECK GABUNGAN: dijalankan sekali saat PC nyala ===
    # Kumpulkan (1) perubahan fisik vs sesi sebelumnya, dan (2) status kepatuhan
    # vs standar; lalu kirim SATU notif Telegram (tidak terpisah-pisah).
    new_compliance = ""
    if was_offline_before:
        pc_master = _find_pc(pc_name)
        new_snapshot = {
            "ram_json": _json.dumps(data.get("ram") or {}, ensure_ascii=False),
            "disk_json": _json.dumps(data.get("disks") or [], ensure_ascii=False),
            "gpu_json": _json.dumps(data.get("gpus") or [], ensure_ascii=False),
        }

        # (1) Perubahan fisik vs sesi nyala sebelumnya
        changes = []
        if prev_fp and prev_fp != new_fp and old_snapshot is not None:
            changes = spec_compare.diff_change(old_snapshot, new_snapshot)

        # (2) Kepatuhan vs standar
        comp_status, comp_kurang, prev_compliance = "", [], (live.last_compliance or "")
        if pc_master:
            _shim = type("S", (), new_snapshot)()
            comp_status, comp_kurang = spec_compare.compare(pc_master, _shim)
            new_compliance = comp_status

        compliance_changed = bool(pc_master) and comp_status and comp_status != prev_compliance

        # Catat riwayat bila ada sesuatu yang berubah (fisik atau status)
        if pc_master and (changes or compliance_changed):
            note_parts = []
            if changes:
                note_parts.append("Perubahan fisik: " + "; ".join(changes))
            if compliance_changed:
                note_parts.append(
                    "Status: " + (
                        "tidak sesuai standar (" + "; ".join(comp_kurang) + ")"
                        if comp_status == "TIDAK_LENGKAP" else "sudah sesuai standar"
                    )
                )
            db.session.add(Inspection(
                pc_id=pc_master.id, status=comp_status or "OK",
                note="Boot: " + " | ".join(note_parts), source="boot-check",
            ))

        # Susun SATU notif gabungan (hanya bila ada yang perlu dilaporkan)
        if changes or compliance_changed:
            org = current_app.config.get("ORG_NAME", "Instansi")
            if comp_status == "TIDAK_LENGKAP":
                header = f"⚠️ <b>{pc_name}</b> menyala — spek TIDAK SESUAI STANDAR"
            elif compliance_changed and comp_status == "OK":
                header = f"✅ <b>{pc_name}</b> menyala — spek SUDAH SESUAI STANDAR (pulih)"
            else:
                header = f"ℹ️ <b>{pc_name}</b> menyala — ada perubahan spek"

            body = []
            if changes:
                body.append("Perubahan terdeteksi:\n" + "\n".join(f"• {c}" for c in changes))
            if comp_status == "TIDAK_LENGKAP" and comp_kurang:
                body.append("Kekurangan vs standar:\n" + "\n".join(f"• {k}" for k in comp_kurang))

            actual_txt = spec_compare.summarize_actual(type("S", (), new_snapshot)())
            std_txt = pc_master.spec_text if pc_master else "-"
            body.append(f"Spek aktual: {actual_txt}\nSpek standar: {std_txt}")

            notifier.send_telegram(
                header + "\n\n" + "\n\n".join(body) +
                f"\n\nWaktu: {now.strftime('%Y-%m-%d %H:%M')} · {org}"
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
    if new_boot_time:
        live.last_boot_time = new_boot_time
    if new_compliance:
        live.last_compliance = new_compliance
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