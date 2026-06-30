import datetime as _dt
from flask import Blueprint, render_template, request, redirect, url_for, flash
from extensions import db
from models import PC, Inspection

insp_bp = Blueprint("insp", __name__)


@insp_bp.route("/add", methods=["GET", "POST"])
def add():
    pc_id = request.args.get("pc_id", type=int)
    if request.method == "POST":
        pc_id = int(request.form.get("pc_id"))
        pc = PC.query.get_or_404(pc_id)
        status = request.form.get("status") or "OK"
        note = (request.form.get("note") or "").strip()
        ts = request.form.get("inspected_at") or None

        inp = Inspection(
            pc_id=pc.id,
            status=status,
            note=note,
            source="web",
        )
        if ts:
            try:
                inp.inspected_at = _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M")
            except ValueError:
                pass
        db.session.add(inp)
        db.session.commit()
        flash(f"Pemeriksaan PC '{pc.name}' disimpan: {status}", "success")
        return redirect(url_for("pc.detail", pc_id=pc.id))

    pc = PC.query.get(pc_id) if pc_id else None
    pcs = PC.query.order_by(PC.name.asc()).all()
    return render_template("inspection/add.html", pc=pc, pcs=pcs)


@insp_bp.route("/history")
def history():
    pc_id = request.args.get("pc_id", type=int)
    date_from = (request.args.get("date_from") or "").strip()
    date_to = (request.args.get("date_to") or "").strip()

    q = Inspection.query
    if pc_id:
        q = q.filter_by(pc_id=pc_id)

    if date_from:
        try:
            dt_from = _dt.datetime.strptime(date_from, "%Y-%m-%d")
            q = q.filter(Inspection.inspected_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = _dt.datetime.strptime(date_to, "%Y-%m-%d") + _dt.timedelta(days=1)
            q = q.filter(Inspection.inspected_at < dt_to)
        except ValueError:
            pass

    items = q.order_by(Inspection.inspected_at.desc()).limit(500).all()
    pcs = PC.query.order_by(PC.name.asc()).all()
    return render_template(
        "inspection/history.html",
        items=items,
        pc_id=pc_id,
        pcs=pcs,
        date_from=date_from,
        date_to=date_to,
    )


@insp_bp.route("/bulk-delete", methods=["POST"])
def bulk_delete():
    ids = request.form.getlist("inspection_ids")
    pc_id = request.form.get("pc_id", type=int)
    date_from = (request.form.get("date_from") or "").strip()
    date_to = (request.form.get("date_to") or "").strip()

    int_ids = []
    for x in ids:
        try:
            int_ids.append(int(x))
        except (TypeError, ValueError):
            pass

    if not int_ids:
        flash("Pilih minimal satu catatan untuk dihapus.", "warning")
        return redirect(url_for("insp.history", pc_id=pc_id, date_from=date_from, date_to=date_to))

    deleted = Inspection.query.filter(Inspection.id.in_(int_ids)).delete(synchronize_session=False)
    db.session.commit()
    flash(f"{deleted} catatan pemeriksaan dihapus.", "success")
    return redirect(url_for("insp.history", pc_id=pc_id, date_from=date_from, date_to=date_to))


@insp_bp.route("/<int:insp_id>/delete", methods=["POST"])
def delete(insp_id):
    inp = Inspection.query.get_or_404(insp_id)
    pc_id = inp.pc_id
    db.session.delete(inp)
    db.session.commit()
    flash("Catatan pemeriksaan dihapus", "success")
    return redirect(url_for("insp.history", pc_id=pc_id))