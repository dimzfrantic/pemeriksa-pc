from flask import Flask, redirect, render_template, request, session, url_for, flash
from config import Config
from extensions import db, csrf
from models import PC, Inspection, PCLive


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    csrf.init_app(app)

    # Routes
    from routes.main import main_bp
    from routes.pc import pc_bp
    from routes.inspection import insp_bp
    from routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(pc_bp, url_prefix="/pc")
    app.register_blueprint(insp_bp, url_prefix="/inspection")
    app.register_blueprint(api_bp, url_prefix="/api")

    # API dipanggil oleh poller Telegram (JSON, bukan form) -> bebas dari CSRF
    csrf.exempt(api_bp)

    with app.app_context():
        db.create_all()

    @app.template_filter("fmtdt")
    def fmtdt(value):
        if not value:
            return "-"
        try:
            return value.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(value)

    @app.context_processor
    def inject_branding():
        return {
            "ORG_NAME": app.config.get("ORG_NAME", "Instansi"),
            "APP_TITLE": app.config.get("APP_TITLE", "Pemantauan PC"),
            "WEB_UNLOCKED": bool(session.get("web_unlocked")),
        }

    @app.route("/unlock", methods=["GET", "POST"])
    def unlock():
        if request.method == "POST":
            code = (request.form.get("passcode") or "").strip()
            if code == app.config.get("WEB_PASSCODE", "1234"):
                session["web_unlocked"] = True
                session.pop("unlock_fail_count", None)
                flash("Passcode benar. Akses dibuka.", "success")
                next_url = request.args.get("next") or url_for("main.index")
                return redirect(next_url)
            fail_count = int(session.get("unlock_fail_count", 0)) + 1
            session["unlock_fail_count"] = fail_count
            flash("Passcode salah.", "warning")
            if fail_count >= 3:
                flash("apakah kamu tidak belajar berhitung waktu kecil?", "hint")
        return render_template("unlock.html")

    @app.route("/logout-web", methods=["POST"])
    def logout_web():
        session.pop("web_unlocked", None)
        flash("Akses web dikunci kembali.", "success")
        return redirect(url_for("unlock"))

    @app.before_request
    def require_passcode_for_web():
        endpoint = request.endpoint or ""
        # API, static, dan halaman unlock/logout tidak perlu passcode
        if endpoint.startswith("api.") or endpoint in {"static", "unlock", "logout_web"}:
            return None
        if not session.get("web_unlocked"):
            return redirect(url_for("unlock", next=request.path))
        return None

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5080, debug=True)