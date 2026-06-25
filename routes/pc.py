from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from extensions import db
from models import PC

pc_bp = Blueprint("pc", __name__)


def _parse_hdd_capacities(raw):
    """Ubah input '500, 1000' -> ('500,1000', count, kapasitas_pertama).

    Mengembalikan (csv_normalisasi, jumlah, kapasitas_seragam_atau_0).
    """
    caps = []
    for x in (raw or "").replace(";", ",").split(","):
        x = x.strip()
        if x.isdigit() and int(x) > 0:
            caps.append(int(x))
    csv = ",".join(str(c) for c in caps)
    count = len(caps)
    uniform = caps[0] if (count and len(set(caps)) == 1) else 0
    return csv, count, uniform


@pc_bp.route("/")
def list():
    pcs = PC.query.order_by(PC.name.asc()).all()
    return render_template("pc/list.html", pcs=pcs)


@pc_bp.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Nama PC wajib diisi", "warning")
            return render_template("pc/form.html", pc=None)
        if PC.query.filter_by(name=name).first():
            flash(f"PC '{name}' sudah ada", "warning")
            return render_template("pc/form.html", pc=None)

        pc = PC(
            name=name,
            location=(request.form.get("location") or "").strip(),
            ram_sticks=int(request.form.get("ram_sticks") or 1),
            ram_capacity_gb=int(request.form.get("ram_capacity_gb") or 8),
            ssd_count=int(request.form.get("ssd_count") or 1),
            ssd_capacity_gb=int(request.form.get("ssd_capacity_gb") or 256),
            gpu_name=(request.form.get("gpu_name") or "").strip(),
            monitor_count=int(request.form.get("monitor_count") or 1),
            monitor_size_inch=int(request.form.get("monitor_size_inch") or 24),
            monitor_brand=(request.form.get("monitor_brand") or "").strip(),
            notes=(request.form.get("notes") or "").strip(),
        )
        hdd_csv, hdd_count, hdd_uniform = _parse_hdd_capacities(request.form.get("hdd_capacities"))
        pc.hdd_capacities = hdd_csv
        pc.hdd_count = hdd_count
        pc.hdd_capacity_gb = hdd_uniform
        db.session.add(pc)
        db.session.commit()
        flash(f"PC '{name}' ditambahkan", "success")
        return redirect(url_for("pc.detail", pc_id=pc.id))

    return render_template("pc/form.html", pc=None)


@pc_bp.route("/<int:pc_id>")
def detail(pc_id):
    pc = PC.query.get_or_404(pc_id)
    from models import PCLive
    from flask import current_app
    offline_secs = int(current_app.config.get("AGENT_OFFLINE_SECONDS", 180))
    live = PCLive.query.filter_by(pc_name=pc.name).first()
    live_info = None
    if live:
        import json as _json
        def _p(s):
            try:
                return _json.loads(s) if s else None
            except Exception:
                return None
        ram = _p(live.ram_json) or {}
        disks = _p(live.disk_json) or []
        gpus = _p(live.gpu_json) or []
        live_info = {
            "online": live.is_online(offline_secs),
            "ip": live.ip,
            "hostname": live.hostname,
            "last_seen": live.last_seen,
            "agent_version": live.agent_version,
            "ram": ram,
            "disks": disks,
            "gpus": gpus,
        }
    return render_template("pc/detail.html", pc=pc, live=live_info)


@pc_bp.route("/<int:pc_id>/edit", methods=["GET", "POST"])
def edit(pc_id):
    pc = PC.query.get_or_404(pc_id)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Nama PC wajib diisi", "warning")
            return render_template("pc/form.html", pc=pc)
        other = PC.query.filter_by(name=name).first()
        if other and other.id != pc.id:
            flash(f"Nama '{name}' dipakai PC lain", "warning")
            return render_template("pc/form.html", pc=pc)

        pc.name = name
        pc.location = (request.form.get("location") or "").strip()
        pc.ram_sticks = int(request.form.get("ram_sticks") or 1)
        pc.ram_capacity_gb = int(request.form.get("ram_capacity_gb") or 8)
        pc.ssd_count = int(request.form.get("ssd_count") or 1)
        pc.ssd_capacity_gb = int(request.form.get("ssd_capacity_gb") or 256)
        hdd_csv, hdd_count, hdd_uniform = _parse_hdd_capacities(request.form.get("hdd_capacities"))
        pc.hdd_capacities = hdd_csv
        pc.hdd_count = hdd_count
        pc.hdd_capacity_gb = hdd_uniform
        pc.gpu_name = (request.form.get("gpu_name") or "").strip()
        pc.monitor_count = int(request.form.get("monitor_count") or 1)
        pc.monitor_size_inch = int(request.form.get("monitor_size_inch") or 24)
        pc.monitor_brand = (request.form.get("monitor_brand") or "").strip()
        pc.notes = (request.form.get("notes") or "").strip()
        db.session.commit()
        flash("Perubahan disimpan", "success")
        return redirect(url_for("pc.detail", pc_id=pc.id))

    return render_template("pc/form.html", pc=pc)


@pc_bp.route("/<int:pc_id>/delete", methods=["POST"])
def delete(pc_id):
    pc = PC.query.get_or_404(pc_id)
    name = pc.name
    db.session.delete(pc)
    db.session.commit()
    flash(f"PC '{name}' dihapus", "success")
    return redirect(url_for("main.index"))