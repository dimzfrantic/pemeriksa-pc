from flask import Flask
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
        }

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5080, debug=True)