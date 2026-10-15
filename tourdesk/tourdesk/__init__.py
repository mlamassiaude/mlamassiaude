from __future__ import annotations

import os
import secrets
from datetime import date
from decimal import Decimal
from functools import wraps

from flask import Flask, abort, flash, g, redirect, request, session, url_for
from markupsafe import Markup

from .icons import ICONS
from .models import Agency, Artist, User, db


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
        user = g.get("user")
        agency = Agency.get() if user else None
        rail_artists = Artist.query.filter_by(active=True).order_by(Artist.name).limit(12).all() if user else []
        return {
            "csrf_token": csrf_token,
            "current_user": user,
            "agency": agency,
            "rail_artists": rail_artists,
            "today": date.today(),
            "icon": icon,
        }

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response


def icon(name: str, size: int = 18, label: str | None = None) -> Markup:
    """Inline Lucide icon. Decorative unless a label is given."""
    a11y = f'role="img" aria-label="{Markup.escape(label)}"' if label else 'aria-hidden="true"'
    return Markup(
        f'<svg class="icon" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" {a11y}>{ICONS.get(name, "")}</svg>'
    )


INK = "#111318"


def _luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    r, g_, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g_) + 0.0722 * lin(b)


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _mix(hex_color: str, target: str, amount: float) -> str:
    a = [int(hex_color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    b = [int(target.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))


def _valid(hex_color: str | None) -> str:
    value = (hex_color or "").strip()
    if len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return value.lower()
        except ValueError:
            pass
    return "#888888"


def readable_ink(hex_color: str | None) -> str:
    """Near-black or white text on a fill in the artist's colour."""
    color = _valid(hex_color)
    return "#ffffff" if _contrast(color, "#ffffff") >= _contrast(color, INK) else INK


def readable_fill(hex_color: str | None) -> str:
    """The artist's colour, nudged darker or lighter only as far as needed for
    text on it (an avatar initial) to reach 4.5:1."""
    color = _valid(hex_color)
    ink = readable_ink(color)
    target = "#000000" if ink == "#ffffff" else "#ffffff"
    step = 0
    while _contrast(color, ink) < 4.5 and step < 20:
        step += 1
        color = _mix(_valid(hex_color), target, step * 0.04)
    return color


def _register_filters(app: Flask) -> None:
    app.add_template_filter(readable_ink, "ink")
    app.add_template_filter(readable_fill, "fill")

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
