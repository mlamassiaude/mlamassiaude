import os
import secrets
from datetime import date
from decimal import Decimal
from functools import wraps

from flask import Flask, abort, flash, g, redirect, request, session, url_for

from .models import Agency, User, db


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.update(
        SECRET_KEY=os.environ.get("TOURDESK_SECRET_KEY") or _instance_secret(app.instance_path),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "TOURDESK_DATABASE_URL", f"sqlite:///{os.path.join(app.instance_path, 'tourdesk.db')}"
        ),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if config:
        app.config.update(config)

    db.init_app(app)
    with app.app_context():
        db.create_all()
        Agency.get()
        db.session.commit()

    from .views import register_blueprints

    register_blueprints(app)
    _register_hooks(app)
    _register_filters(app)
    _register_cli(app)
    return app


def _instance_secret(instance_path: str) -> str:
    """Persist a random secret key so sessions survive restarts without the
    user having to configure anything."""
    path = os.path.join(instance_path, "secret_key")
    if not os.path.exists(path):
        with open(path, "w") as fh:
            fh.write(secrets.token_hex(32))
        os.chmod(path, 0o600)
    with open(path) as fh:
        return fh.read().strip()


# --------------------------------------------------------------------------
# Auth and CSRF
# --------------------------------------------------------------------------

PUBLIC_ENDPOINTS = {"auth.login", "auth.setup", "itinerary.shared", "itinerary.shared_ics", "static"}


def login_required_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user or not g.user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def _register_hooks(app: Flask) -> None:
    @app.before_request
    def load_user_and_guard():
        g.user = db.session.get(User, session["user_id"]) if "user_id" in session else None

        if request.method == "POST":
            sent = request.form.get("csrf_token", "")
            if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
                abort(400, "Form expired, please reload the page and try again.")

        if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
            return None
        if User.query.first() is None:
            return redirect(url_for("auth.setup"))
        if g.user is None:
            return redirect(url_for("auth.login", next=request.full_path))
        return None

    @app.context_processor
    def inject_globals():
        agency = Agency.get() if g.get("user") else None
        return {"csrf_token": csrf_token, "current_user": g.get("user"), "agency": agency, "today": date.today()}

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response


def _register_filters(app: Flask) -> None:
    @app.template_filter("money")
    def money(value, currency=None):
        if value is None:
            value = 0
        text = f"{Decimal(str(value)):,.2f}"
        return f"{text} {currency}" if currency else text

    @app.template_filter("d")
    def fmt_date(value, fmt="%d %b %Y"):
        return value.strftime(fmt) if value else ""

    @app.template_filter("safe_url")
    def safe_url(value):
        # Only link out to http(s) so a stored "javascript:" URL can't run.
        value = (value or "").strip()
        if value.lower().startswith(("http://", "https://")):
            return value
        if value and "://" not in value and ":" not in value.split("/")[0]:
            return f"https://{value}"
        return ""

    @app.template_filter("pct")
    def pct(value):
        return f"{value or 0:g}%"


def _register_cli(app: Flask) -> None:
    @app.cli.command("seed-demo")
    def seed_demo():
        """Load a demo agency with artists, shows, logistics and documents."""
        from .demo import seed

        seed()
        print("Demo data loaded. Log in with demo@tourdesk.local / demo1234")

    @app.cli.command("create-user")
    def create_user():
        """Create an agent account interactively."""
        import getpass

        name = input("Name: ").strip()
        email = input("Email: ").strip().lower()
        password = getpass.getpass("Password: ")
        user = User(name=name, email=email, is_admin=input("Admin? [y/N] ").lower().startswith("y"))
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"Created {email}")


def flash_errors(errors: dict) -> None:
    for label, message in errors.items():
        flash(f"{label}: {message}", "error")
