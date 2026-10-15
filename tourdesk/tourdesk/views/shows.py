from datetime import date, datetime, time, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import flash_errors
from ..forms import SHOW_FIELDS, SHOW_SECTIONS, logistics_fields, populate
from ..models import SHOW_STATUSES, Agency, Artist, LogisticsItem, Show, db

bp = Blueprint("shows", __name__)


@bp.route("/shows")
def shows():
    artist_id = request.args.get("artist", type=int)
    status = request.args.get("status", "")
    when = request.args.get("when", "upcoming")
    today = date.today()

    query = Show.query
    if artist_id:
        query = query.filter_by(artist_id=artist_id)
    if status:
        query = query.filter_by(status=status)
    if when == "past":
        query = query.filter(Show.date < today).order_by(Show.date.desc())
    else:
        query = query.filter(Show.date >= today).order_by(Show.date)
    return render_template(
        "shows/list.html",
        shows=query.limit(500).all(),
        artists=Artist.query.order_by(Artist.name).all(),
        statuses=SHOW_STATUSES,
        artist_id=artist_id,
        status=status,
        when=when,
    )


@bp.route("/shows/new", methods=["GET", "POST"])
def show_new():
    agency = Agency.get()
    show = Show(status="option", deal_type="flat", currency=agency.default_currency, deposit_percent=50, set_length=60)
    artist = db.session.get(Artist, request.args.get("artist", type=int) or 0)
    if artist:
        show.artist_id = artist.id
        show.fee = artist.default_fee
        show.currency = artist.currency
    if request.args.get("date"):
        try:
            show.date = date.fromisoformat(request.args["date"])
        except ValueError:
            pass

    if request.method == "POST":
        errors = populate(show, SHOW_FIELDS, request.form)
        if errors:
            flash_errors(errors)
        else:
            db.session.add(show)
            db.session.commit()
            flash("Show created.", "success")
            return redirect(url_for(".show", show_id=show.id))
    return render_template(
        "form_page.html", title="New show", sections=SHOW_SECTIONS, fields=SHOW_FIELDS, obj=show, cancel_url=url_for(".shows")
    )


@bp.route("/shows/<int:show_id>")
def show(show_id):
    show = db.get_or_404(Show, show_id)
    return render_template("shows/detail.html", show=show, statuses=SHOW_STATUSES)


@bp.route("/shows/<int:show_id>/edit", methods=["GET", "POST"])
def show_edit(show_id):
    show = db.get_or_404(Show, show_id)
    if request.method == "POST":
        errors = populate(show, SHOW_FIELDS, request.form)
        if errors:
            flash_errors(errors)
        else:
            db.session.commit()
            flash("Show updated.", "success")
            return redirect(url_for(".show", show_id=show.id))
    return render_template(
        "form_page.html",
        title=f"Edit show · {show.title}",
        sections=SHOW_SECTIONS,
        fields=SHOW_FIELDS,
        obj=show,
        cancel_url=url_for(".show", show_id=show.id),
    )


@bp.route("/shows/<int:show_id>/status", methods=["POST"])
def show_status(show_id):
    show = db.get_or_404(Show, show_id)
    status = request.form.get("status")
    if status not in dict(SHOW_STATUSES):
        abort(400)
    show.status = status
    db.session.commit()
    flash(f"Show marked as {dict(SHOW_STATUSES)[status].lower()}.", "success")
    return redirect(url_for(".show", show_id=show.id))


@bp.route("/shows/<int:show_id>/delete", methods=["POST"])
def show_delete(show_id):
    show = db.get_or_404(Show, show_id)
    if any(i.number for i in show.invoices):
        flash("This show has issued invoices. Cancel the show instead so the invoices keep their link.", "error")
        return redirect(url_for(".show", show_id=show.id))
    for invoice in show.invoices:
        db.session.delete(invoice)
    for item in show.logistics:
        item.show_id = None
    artist_id = show.artist_id
    db.session.delete(show)
    db.session.commit()
    flash("Show deleted.", "success")
    return redirect(url_for("roster.artist", artist_id=artist_id))


# --------------------------------------------------------------------------
# Logistics
# --------------------------------------------------------------------------


def _back_to(item: LogisticsItem) -> str:
    if item.show_id:
        return url_for(".show", show_id=item.show_id) + "#logistics"
    return url_for("roster.artist", artist_id=item.artist_id) + "#logistics"


@bp.route("/logistics/new", methods=["GET", "POST"])
def logistics_new():
    show = db.session.get(Show, request.args.get("show", type=int) or 0)
    artist = show.artist if show else db.session.get(Artist, request.args.get("artist", type=int) or 0)
    if artist is None:
        abort(404)
    kind = request.args.get("kind", "flight")
    # Use ids rather than relationships so the unsaved item isn't cascaded
    # into the session and autoflushed while the form renders.
    item = LogisticsItem(
        artist_id=artist.id,
        show_id=show.id if show else None,
        kind=kind,
        status="to_book",
        currency=show.currency if show else artist.currency,
    )
    if show:
        if kind == "hotel":
            item.start_at = datetime.combine(show.date, time(15))
            item.end_at = datetime.combine(show.date + timedelta(days=1), time(11))
        else:
            item.start_at = datetime.combine(show.date, time(9))
        item.to_place = show.display_city
        item.travellers = ", ".join(m.name for m in artist.members)

    fields = logistics_fields(artist.id)
    if request.method == "POST":
        errors = populate(item, fields, request.form)
        if not errors and item.end_at and item.end_at < item.start_at:
            errors["Arrives / check out"] = "Must be after the start"
        if errors:
            flash_errors(errors)
        else:
            db.session.add(item)
            db.session.commit()
            flash("Logistics saved.", "success")
            return redirect(_back_to(item))
    title = f"New booking for {artist.name}"
    cancel = url_for(".show", show_id=show.id) if show else url_for("roster.artist", artist_id=artist.id)
    return render_template("form_page.html", title=title, fields=fields, obj=item, cancel_url=cancel)


@bp.route("/logistics/<int:item_id>/edit", methods=["GET", "POST"])
def logistics_edit(item_id):
    item = db.get_or_404(LogisticsItem, item_id)
    fields = logistics_fields(item.artist_id)
    if request.method == "POST":
        errors = populate(item, fields, request.form)
        if not errors and item.end_at and item.end_at < item.start_at:
            errors["Arrives / check out"] = "Must be after the start"
        if errors:
            flash_errors(errors)
            db.session.rollback()
        else:
            db.session.commit()
            flash("Logistics updated.", "success")
            return redirect(_back_to(item))
    return render_template(
        "form_page.html", title=f"Edit {item.label}", fields=fields, obj=item, cancel_url=_back_to(item)
    )


@bp.route("/logistics/<int:item_id>/delete", methods=["POST"])
def logistics_delete(item_id):
    item = db.get_or_404(LogisticsItem, item_id)
    back = _back_to(item)
    db.session.delete(item)
    db.session.commit()
    flash("Logistics item removed.", "success")
    return redirect(back)
