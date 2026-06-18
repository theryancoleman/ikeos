import os
import re
import threading
from flask import Flask


def _warm_cache():
    from app.services.vault import get_projects_with_meta, read_entries, VAULT_PATH
    try:
        if not VAULT_PATH.exists():
            return
        get_projects_with_meta()
        read_entries()
    except Exception:
        pass


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.environ["FLASK_SECRET_KEY"]
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600  # 1 hour; eliminates no-cache round-trips on every page switch

    from app.routes.capture import bp as capture_bp
    from app.routes.browse import bp as browse_bp
    from app.routes.agents import bp as agents_bp
    from app.routes.housekeeping import bp as housekeeping_bp

    app.register_blueprint(capture_bp)
    app.register_blueprint(browse_bp)
    app.register_blueprint(agents_bp)
    app.register_blueprint(housekeeping_bp)

    @app.template_filter("docker_image")
    def docker_image_filter(image: str) -> str:
        """'lscr.io/linuxserver/radarr:6.2.1.10461-ls306' → 'radarr 6.2.1'"""
        name_tag = image.split("/")[-1]
        if ":" in name_tag:
            name, tag = name_tag.split(":", 1)
            tag = re.sub(r"^v", "", tag)
            m = re.match(r"^[\d.]+", tag)
            version = m.group().rstrip(".") if m else tag
            if version and version != "latest" and not re.fullmatch(r"[0-9a-f]{7,}", version):
                return f"{name} {version}"
            return name
        return name_tag

    @app.template_filter("docker_ports")
    def docker_ports_filter(ports: str) -> str:
        """'0.0.0.0:7878->7878/tcp, [::]:7878->7878/tcp' → '7878'"""
        if not ports:
            return "—"
        seen: set[str] = set()
        unique = []
        for p in re.findall(r"(?:0\.0\.0\.0|\[::\]):(\d+)->", ports):
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return ", ".join(unique) if unique else "—"

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

    threading.Thread(target=_warm_cache, daemon=True).start()

    return app
