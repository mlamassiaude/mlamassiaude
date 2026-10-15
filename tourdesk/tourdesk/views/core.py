import calendar as cal
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import flash_errors, login_required_admin
from ..forms import AGENCY_FIELDS, populate
from ..models import Agency, Artist, Contract, Invoice, LogisticsItem, Show, User, db
from ..services import CONTRACT_PLACEHOLDERS, totals_by_currency

bp = Blueprint("core", __name__)


@bp.route("/")
def dashboard():
    today = date.today()
    upcoming = (
        Show.query.filter(Show.date >= today, Show.status.in_(["option", "pending", "confirmed"]))
        .order_by(Show.date)
        .limit(12)
        .all()
    )
    open_options = Show.query.filter(Show.date >= today, Show.status.in_(["option", "pending"])).count()
    confirmed_30 = Show.query.filter(
        Show.date >= today, Show.date <= today + timedelta(days=30), Show.status == "confirmed"
    ).count()
    awaiting_signature = Contract.query.filter_by(status="sent").order_by(Contract.sent_at).all()
    outstanding = Invoice.query.filter_by(status="sent").order_by(Invoice.due_date).all()
    overdue = [i for i in outstanding if i.is_overdue]
    to_book = (
        LogisticsItem.query.filter(
            LogisticsItem.status == "to_book",
            LogisticsItem.start_at >= datetime.combine(today, datetime.min.time()),
            LogisticsItem.start_at < datetime.combine(today + timedelta(days=45), datetime.min.time()),
        )
        .order_by(LogisticsItem.start_at)
        .all()
    )
    shows_needing_contract = [
        s for s in upcoming if s.status == "confirmed" and not any(c.status != "cancelled" for c in s.contracts)
    ]

    # Gross booked and commission per artist for the current year.
    year_start = date(today.year, 1, 1)
    year_end = date(today.year, 12, 31)
    year_shows = Show.query.filter(
        Show.date >= year_start, Show.date <= year_end, Show.status.in_(["confirmed", "played"])
    ).all()
    per_artist = defaultdict(lambda: {"shows": 0, "gross": defaultdict(Decimal), "commission": defaultdict(Decimal)})
    for s in year_shows:
        row = per_artist[s.artist]
        row["shows"] += 1
        row["gross"][s.currency] += s.fee or 0
        row["commission"][s.currency] += s.commission_amount
    per_artist = sorted(per_artist.items(), key=lambda kv: kv[0].name.lower())

    return render_template(
        "dashboard.html",
        upcoming=upcoming,
        open_options=open_options,
        confirmed_30=confirmed_30,
        awaiting_signature=awaiting_signature,
        outstanding=outstanding,
        outstanding_totals=totals_by_currency(outstanding),
        overdue=overdue,
        shows_needing_contract=shows_needing_contract,
        to_book=to_book,
        per_artist=per_artist,
        year=today.year,
    )


@bp.route("/calendar")
def calendar():
    today = date.today()
    try:
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))
        first = date(year, month, 1)
    except ValueError:
        first = date(today.year, today.month, 1)
    artist_id = request.args.get("artist", type=int)

    weeks = cal.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month)
    query = Show.query.filter(Show.date >= weeks[0][0], Show.date <= weeks[-1][-1])
    if artist_id:
        query = query.filter_by(artist_id=artist_id)
    by_day = defaultdict(list)
    for show in query.order_by(Show.date):
        by_day[show.date].append(show)

    prev_month = (first - timedelta(days=1)).replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    return render_template(
        "calendar.html",
        weeks=weeks,
        by_day=by_day,
        first=first,
        prev_month=prev_month,
        next_month=next_month,
        artists=Artist.query.filter_by(active=True).order_by(Artist.name).all(),
        artist_id=artist_id,
    )


@bp.route("/settings", methods=["GET", "POST"])
@login_required_admin
def settings():
    agency = Agency.get()
    if request.method == "POST":
        errors = populate(agency, AGENCY_FIELDS, request.form)
        if errors:
            flash_errors(errors)
            db.session.rollback()
        else:
            db.session.commit()
            flash("Settings saved.", "success")
            return redirect(url_for("core.settings"))
    return render_template(
        "settings/agency.html", fields=AGENCY_FIELDS, obj=agency, placeholders=CONTRACT_PLACEHOLDERS
    )


@bp.route("/settings/users", methods=["GET", "POST"])
@login_required_admin
def users():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 8:
            flash("Name, email and a password of at least 8 characters are required.", "error")
        elif User.query.filter_by(email=email).first():
            flash("A user with that email already exists.", "error")
        else:
            user = User(name=name, email=email, is_admin=bool(request.form.get("is_admin")))
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(f"Added {name}.", "success")
        return redirect(url_for("core.users"))
    return render_template("settings/users.html", users=User.query.order_by(User.name).all())


@bp.route("/settings/users/<int:user_id>/delete", methods=["POST"])
@login_required_admin
def delete_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == g.user.id:
        flash("You can't remove your own account.", "error")
    else:
        Artist.query.filter_by(agent_id=user.id).update({"agent_id": None})
        db.session.delete(user)
        db.session.commit()
        flash(f"Removed {user.name}.", "success")
    return redirect(url_for("core.users"))
