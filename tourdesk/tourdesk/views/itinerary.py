from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for

from .. import flash_errors
from ..forms import ITINERARY_FIELDS, populate
from ..models import Agency, Artist, Itinerary, Show, db
from ..services import build_itinerary, itinerary_ics

bp = Blueprint("itinerary", __name__)


@bp.route("/itineraries")
def itineraries():
    items = Itinerary.query.order_by(Itinerary.start_date.desc()).all()
    return render_template("itinerary/list.html", itineraries=items)


@bp.route("/itineraries/new", methods=["GET", "POST"])
@bp.route("/itineraries/<int:itinerary_id>/edit", methods=["GET", "POST"])
def itinerary_edit(itinerary_id=None):
    itinerary = db.get_or_404(Itinerary, itinerary_id) if itinerary_id else Itinerary()
    if not itinerary_id:
        artist = db.session.get(Artist, request.args.get("artist", type=int) or 0)
        if artist:
            itinerary.artist_id = artist.id
            upcoming = [s for s in artist.shows if s.status in ("confirmed", "pending", "option")]
            if upcoming:
                itinerary.start_date = upcoming[0].date
                itinerary.end_date = upcoming[-1].date
    if request.method == "POST":
        errors = populate(itinerary, ITINERARY_FIELDS, request.form)
        if not errors and itinerary.end_date < itinerary.start_date:
            errors["To"] = "Must be on or after the start date"
        if not errors and (itinerary.end_date - itinerary.start_date).days > 366:
            errors["To"] = "Itineraries can cover at most a year"
        if errors:
            flash_errors(errors)
            if itinerary_id:
                db.session.rollback()
        else:
            db.session.add(itinerary)
            db.session.commit()
            flash("Itinerary saved.", "success")
            return redirect(url_for(".itinerary", itinerary_id=itinerary.id))
    title = f"Edit {itinerary.title}" if itinerary_id else "New itinerary"
    cancel = url_for(".itinerary", itinerary_id=itinerary_id) if itinerary_id else url_for(".itineraries")
    return render_template("form_page.html", title=title, fields=ITINERARY_FIELDS, obj=itinerary, cancel_url=cancel)


def _render(itinerary: Itinerary, shared: bool):
    days = build_itinerary(itinerary.artist_id, itinerary.start_date, itinerary.end_date)
    return render_template(
        "itinerary/view.html",
        itinerary=itinerary,
        days=days,
        shared=shared,
        agency_info=Agency.get(),
        print_mode=request.args.get("print") == "1",
    )


@bp.route("/itineraries/<int:itinerary_id>")
def itinerary(itinerary_id):
    return _render(db.get_or_404(Itinerary, itinerary_id), shared=False)


@bp.route("/itineraries/<int:itinerary_id>/delete", methods=["POST"])
def itinerary_delete(itinerary_id):
    itinerary = db.get_or_404(Itinerary, itinerary_id)
    db.session.delete(itinerary)
    db.session.commit()
    flash("Itinerary deleted.", "success")
    return redirect(url_for(".itineraries"))


@bp.route("/itineraries/<int:itinerary_id>/rotate-link", methods=["POST"])
def itinerary_rotate(itinerary_id):
    import secrets

    itinerary = db.get_or_404(Itinerary, itinerary_id)
    itinerary.share_token = secrets.token_urlsafe(24)
    db.session.commit()
    flash("New share link created. The old link no longer works.", "success")
    return redirect(url_for(".itinerary", itinerary_id=itinerary.id))


def _shared_or_404(token: str) -> Itinerary:
    itinerary = Itinerary.query.filter_by(share_token=token).first()
    if itinerary is None or not itinerary.share_enabled:
        abort(404)
    return itinerary


@bp.route("/share/<token>")
def shared(token):
    return _render(_shared_or_404(token), shared=True)


@bp.route("/share/<token>/calendar.ics")
def shared_ics(token):
    itinerary = _shared_or_404(token)
    days = build_itinerary(itinerary.artist_id, itinerary.start_date, itinerary.end_date)
    body = itinerary_ics(itinerary, days, request.host)
    return Response(
        body,
        mimetype="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="itinerary-{itinerary.id}.ics"'},
    )


@bp.route("/shows/<int:show_id>/day-sheet")
def day_sheet(show_id):
    """Single day itinerary for one show, handy for advancing."""
    show = db.get_or_404(Show, show_id)
    temp = Itinerary(
        artist_id=show.artist_id, artist=show.artist, title=f"Day sheet · {show.title}", start_date=show.date, end_date=show.date
    )
    days = build_itinerary(show.artist_id, show.date, show.date)
    return render_template(
        "itinerary/view.html", itinerary=temp, days=days, shared=False, day_sheet=True, agency_info=Agency.get(),
        print_mode=request.args.get("print") == "1",
    )
