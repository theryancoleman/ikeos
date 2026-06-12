import os
from flask import Flask


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.environ["FLASK_SECRET_KEY"]
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600  # 1 hour; eliminates no-cache round-trips on every page switch

    from app.routes.capture import bp as capture_bp
    from app.routes.browse import bp as browse_bp
    from app.routes.agents import bp as agents_bp

    app.register_blueprint(capture_bp)
    app.register_blueprint(browse_bp)
    app.register_blueprint(agents_bp)

    @app.context_processor
    def inject_config_version():
        try:
            with open("/claude-config/VERSION") as f:
                version = f.read().strip()
        except OSError:
            version = None
        return {"config_version": version}

    @app.route("/health")
    def health():
        return "ok", 200

    return app
