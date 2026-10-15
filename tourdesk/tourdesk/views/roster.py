from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import flash_errors
from ..forms import ARTIST_FIELDS, MEMBER_FIELDS, PROMOTER_FIELDS, VENUE_FIELDS, populate
from ..models import Agency, Artist, ArtistMember, Itinerary, LogisticsItem, Promoter, Show, Venue, db

bp = Blueprint("roster", __name__)


def _form_page(title, fields, obj, cancel_url, sections=None):
    return render_template(
        "form_page.html", title=title, fields=fields, sections=sections, obj=obj, cancel_url=cancel_url
    )


def _save(obj, fields, success_message, redirect_to):
    """Shared create/update handling for simple entities."""
    errors = populate(obj, fields, request.form)
    if errors:
        flash_errors(errors)
        db.session.rollback()
        return None
    db.session.add(obj)
    db.session.commit()
    flash(success_message, "success")
    return redirect(redirect_to(obj))


# --------------------------------------------------------------------------
# Artists
# --------------------------------------------------------------------------


@bp.route("/artists")
def artists():
    show_inactive = request.args.get("all") == "1"
    query = Artist.query.order_by(Artist.name)
    if not show_inactive:
        query = query.filter_by(active=True)
    artists = query.all()
    today = date.today()
    next_show = {}
    for artist in artists:
        next_show[artist.id] = (
            Show.query.filter(Show.artist_id == artist.id, Show.date >= today, Show.status != "cancelled")
            .order_by(Show.date)
            .first()
        )
    return render_template("artists/list.html", artists=artists, next_show=next_show, show_inactive=show_inactive)


@bp.route("/artists/new", methods=["GET", "POST"])
def artist_new():
    agency = Agency.get()
    artist = Artist(currency=agency.default_currency, commission_rate=15, color="#5b5bd6", active=True)
    if request.method == "POST":
        response = _save(artist, ARTIST_FIELDS, "Artist added to the roster.", lambda a: url_for(".artist", artist_id=a.id))
        if response:
            return response
    return _form_page("New artist", ARTIST_FIELDS, artist, url_for(".artists"))


@bp.route("/artists/<int:artist_id>")
def artist(artist_id):
    artist = db.get_or_404(Artist, artist_id)
    today = date.today()
    upcoming = [s for s in artist.shows if s.date >= today]
    past = [s for s in reversed(artist.shows) if s.date < today][:20]
    logistics = (
        LogisticsItem.query.filter(LogisticsItem.artist_id == artist.id, LogisticsItem.start_at >= datetime.combine(today, datetime.min.time()))
        .order_by(LogisticsItem.start_at)
        .all()
    )
    itineraries = Itinerary.query.filter_by(artist_id=artist.id).order_by(Itinerary.start_date.desc()).all()
    return render_template(
        "artists/detail.html",
        artist=artist,
        upcoming=upcoming,
        past=past,
        logistics=logistics,
        itineraries=itineraries,
        member_fields=MEMBER_FIELDS,
    )


@bp.route("/artists/<int:artist_id>/edit", methods=["GET", "POST"])
def artist_edit(artist_id):
    artist = db.get_or_404(Artist, artist_id)
    if request.method == "POST":
        response = _save(artist, ARTIST_FIELDS, "Artist updated.", lambda a: url_for(".artist", artist_id=a.id))
        if response:
            return response
    return _form_page(f"Edit {artist.name}", ARTIST_FIELDS, artist, url_for(".artist", artist_id=artist.id))


@bp.route("/artists/<int:artist_id>/delete", methods=["POST"])
def artist_delete(artist_id):
    artist = db.get_or_404(Artist, artist_id)
    if artist.shows:
        flash("This artist has shows. Mark them inactive instead so the history is kept.", "error")
        return redirect(url_for(".artist", artist_id=artist.id))
    LogisticsItem.query.filter_by(artist_id=artist.id).delete()
    Itinerary.query.filter_by(artist_id=artist.id).delete()
    db.session.delete(artist)
    db.session.commit()
    flash("Artist removed.", "success")
    return redirect(url_for(".artists"))


@bp.route("/artists/<int:artist_id>/members", methods=["POST"])
def member_add(artist_id):
    artist = db.get_or_404(Artist, artist_id)
    member = ArtistMember(artist_id=artist.id)
    errors = populate(member, MEMBER_FIELDS, request.form)
    if errors:
        db.session.rollback()
        flash_errors(errors)
    else:
        db.session.add(member)
        db.session.commit()
        flash(f"{member.name} added to the travel party.", "success")
    return redirect(url_for(".artist", artist_id=artist_id) + "#party")


@bp.route("/members/<int:member_id>/delete", methods=["POST"])
def member_delete(member_id):
    member = db.get_or_404(ArtistMember, member_id)
    artist_id = member.artist_id
    db.session.delete(member)
    db.session.commit()
    return redirect(url_for(".artist", artist_id=artist_id) + "#party")


# --------------------------------------------------------------------------
# Venues and promoters
# --------------------------------------------------------------------------


@bp.route("/venues")
def venues():
    q = request.args.get("q", "").strip()
    query = Venue.query.order_by(Venue.name)
    if q:
        like = f"%{q}%"
        query = query.filter(Venue.name.ilike(like) | Venue.city.ilike(like) | Venue.country.ilike(like))
    return render_template("venues/list.html", venues=query.all(), q=q)


@bp.route("/venues/new", methods=["GET", "POST"])
@bp.route("/venues/<int:venue_id>/edit", methods=["GET", "POST"])
def venue_edit(venue_id=None):
    venue = db.get_or_404(Venue, venue_id) if venue_id else Venue()
    if request.method == "POST":
        response = _save(venue, VENUE_FIELDS, "Venue saved.", lambda v: url_for(".venue", venue_id=v.id))
        if response:
            return response
    title = f"Edit {venue.name}" if venue_id else "New venue"
    cancel = url_for(".venue", venue_id=venue_id) if venue_id else url_for(".venues")
    return _form_page(title, VENUE_FIELDS, venue, cancel)


@bp.route("/venues/<int:venue_id>")
def venue(venue_id):
    venue = db.get_or_404(Venue, venue_id)
    shows = sorted(venue.shows, key=lambda s: s.date, reverse=True)
    return render_template("venues/detail.html", venue=venue, shows=shows)


@bp.route("/venues/<int:venue_id>/delete", methods=["POST"])
def venue_delete(venue_id):
    venue = db.get_or_404(Venue, venue_id)
    if venue.shows:
        flash("This venue is used by shows and can't be deleted.", "error")
        return redirect(url_for(".venue", venue_id=venue.id))
    db.session.delete(venue)
    db.session.commit()
    flash("Venue deleted.", "success")
    return redirect(url_for(".venues"))


@bp.route("/promoters")
def promoters():
    q = request.args.get("q", "").strip()
    query = Promoter.query.order_by(Promoter.company)
    if q:
        like = f"%{q}%"
        query = query.filter(Promoter.company.ilike(like) | Promoter.contact_name.ilike(like) | Promoter.city.ilike(like))
    return render_template("promoters/list.html", promoters=query.all(), q=q)


@bp.route("/promoters/new", methods=["GET", "POST"])
@bp.route("/promoters/<int:promoter_id>/edit", methods=["GET", "POST"])
def promoter_edit(promoter_id=None):
    promoter = db.get_or_404(Promoter, promoter_id) if promoter_id else Promoter()
    if request.method == "POST":
        response = _save(promoter, PROMOTER_FIELDS, "Promoter saved.", lambda p: url_for(".promoter", promoter_id=p.id))
        if response:
            return response
    title = f"Edit {promoter.company}" if promoter_id else "New promoter"
    cancel = url_for(".promoter", promoter_id=promoter_id) if promoter_id else url_for(".promoters")
    return _form_page(title, PROMOTER_FIELDS, promoter, cancel)


@bp.route("/promoters/<int:promoter_id>")
def promoter(promoter_id):
    promoter = db.get_or_404(Promoter, promoter_id)
    shows = sorted(promoter.shows, key=lambda s: s.date, reverse=True)
    return render_template("promoters/detail.html", promoter=promoter, shows=shows)


@bp.route("/promoters/<int:promoter_id>/delete", methods=["POST"])
def promoter_delete(promoter_id):
    promoter = db.get_or_404(Promoter, promoter_id)
    if promoter.shows:
        flash("This promoter is used by shows and can't be deleted.", "error")
        return redirect(url_for(".promoter", promoter_id=promoter.id))
    db.session.delete(promoter)
    db.session.commit()
    flash("Promoter deleted.", "success")
    return redirect(url_for(".promoters"))
