import datetime as _dt
from flask import Blueprint, render_template, request, current_app
from extensions import db
from models import PC, Inspection, PCLive

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    q = (request.args.get("q") or "").strip().lower()
    status_filter = (request.args.get("status") or "").strip()

    stmt = PC.query
    if q:
        stmt = stmt.filter(PC.name.ilike(f"%{q}%") | PC.location.ilike(f"%{q}%"))
    pcs = stmt.order_by(PC.name.asc()).all()

    # Ambil snapshot agen (PCLive) untuk semua PC sekaligus
    offline_secs = int(current_app.config.get("AGENT_OFFLINE_SECONDS", 180))
    live_map = {l.pc_name: l for l in PCLive.query.all()}

    rows = []
    online_count = 0
    for pc in pcs:
        latest = pc.latest_inspection
        status = latest.status if latest else "BELUM"
        if status_filter and status != status_filter:
            continue
        live = live_map.get(pc.name)
        is_online = bool(live and live.is_online(offline_secs))
        if is_online:
            online_count += 1
        rows.append({
            "pc": pc,
            "latest": latest,
            "status": status,
            "live": live,
            "online": is_online,
            "ip": (live.ip if live else ""),
            "last_seen": (live.last_seen if live else None),
        })

    # Statistik ringkas
    total = len(rows)
    ok = sum(1 for r in rows if r["status"] == "OK")
    tidak = sum(1 for r in rows if r["status"] == "TIDAK_LENGKAP")
    belum = sum(1 for r in rows if r["status"] == "BELUM")

    return render_template(
        "index.html",
        rows=rows,
        q=q,
        status_filter=status_filter,
        total=total,
        ok=ok,
        tidak=tidak,
        belum=belum,
        online_count=online_count,
    )
