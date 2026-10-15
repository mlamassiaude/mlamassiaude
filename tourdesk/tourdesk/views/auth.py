from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..models import Agency, User, db

bp = Blueprint("auth", __name__)


def _safe_next(target: str | None) -> str:
    # Only follow relative redirects so the login page can't bounce users off-site.
    if not target or urlparse(target).netloc or not target.startswith("/") or target.startswith("//"):
        return url_for("core.dashboard")
    return target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if User.query.first() is None:
        return redirect(url_for("auth.setup"))
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if user and user.check_password(request.form.get("password", "")):
            session.clear()
            session["user_id"] = user.id
            return redirect(_safe_next(request.args.get("next")))
        flash("Wrong email or password.", "error")
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    """First run: create the agency and its first admin account."""
    if User.query.first() is not None:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        agency_name = request.form.get("agency_name", "").strip()
        if not (name and email and agency_name) or len(password) < 8:
            flash("Fill in every field. Passwords need at least 8 characters.", "error")
        else:
            agency = Agency.get()
            agency.name = agency_name
            user = User(name=name, email=email, is_admin=True)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            session.clear()
            session["user_id"] = user.id
            flash(f"Welcome to TourDesk, {name}.", "success")
            return redirect(url_for("core.dashboard"))
    return render_template("auth/setup.html")
