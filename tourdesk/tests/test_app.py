import re
from datetime import date, timedelta
from decimal import Decimal

import pytest

from tourdesk import create_app
from tourdesk.demo import seed
from tourdesk.models import Agency, Artist, Contract, Invoice, Itinerary, LogisticsItem, Show, User, db
from tourdesk.services import build_itinerary, render_template_text


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}"})
    with app.app_context():
        seed()
    return app


@pytest.fixture
def client(app):
    client = app.test_client()
    login(client, "demo@tourdesk.local", "demo1234")
    return client


def token(client):
    page = client.get("/login").get_data(as_text=True)
    match = re.search(r'name="csrf_token" value="([^"]+)"', page)
    assert match, "page has no CSRF token"
    return match.group(1)


def post(client, url, data=None, **kw):
    data = dict(data or {})
    data["csrf_token"] = token(client)
    return client.post(url, data=data, **kw)


def login(client, email, password):
    return post(client, "/login", {"email": email, "password": password})


# --------------------------------------------------------------------------
# Auth and security
# --------------------------------------------------------------------------


def test_requires_login(app):
    client = app.test_client()
    response = client.get("/shows")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_wrong_password(app):
    client = app.test_client()
    response = login(client, "demo@tourdesk.local", "nope")
    assert response.status_code == 200
    assert "Wrong email or password" in response.get_data(as_text=True)


def test_post_without_csrf_is_rejected(client, app):
    with app.app_context():
        show_id = Show.query.first().id
    response = client.post(f"/shows/{show_id}/status", data={"status": "cancelled"})
    assert response.status_code == 400


def test_login_does_not_redirect_off_site(app):
    client = app.test_client()
    data = {"email": "demo@tourdesk.local", "password": "demo1234", "csrf_token": token(client)}
    response = client.post("/login?next=https://evil.example/", data=data)
    assert response.headers["Location"] == "/"


def test_first_run_setup(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'fresh.db'}"})
    client = app.test_client()
    assert client.get("/").headers["Location"].endswith("/setup")
    page = client.get("/setup").get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    response = client.post(
        "/setup",
        data={"agency_name": "Acme Booking", "name": "Ada", "email": "ada@acme.test", "password": "longpassword", "csrf_token": csrf},
    )
    assert response.status_code == 302
    with app.app_context():
        assert Agency.get().name == "Acme Booking"
        assert User.query.one().is_admin


# --------------------------------------------------------------------------
# Every page renders
# --------------------------------------------------------------------------


def test_all_pages_render(client, app):
    with app.app_context():
        artist = Artist.query.first()
        show = Show.query.first()
        contract = Contract.query.first()
        invoice = Invoice.query.first()
        itinerary = Itinerary.query.first()
        item = LogisticsItem.query.first()
        venue_id, promoter_id = show.venue_id, show.promoter_id
        urls = [
            "/", "/calendar", "/calendar?year=2027&month=2", "/artists", "/artists?all=1", "/artists/new",
            f"/artists/{artist.id}", f"/artists/{artist.id}/edit", "/shows", "/shows?when=past", "/shows/new",
            f"/shows/new?artist={artist.id}&date=2027-01-05", f"/shows/{show.id}", f"/shows/{show.id}/edit",
            f"/shows/{show.id}/day-sheet", "/venues", "/venues?q=paris", "/venues/new", f"/venues/{venue_id}",
            "/promoters", "/promoters/new", f"/promoters/{promoter_id}", "/contracts", f"/contracts/{contract.id}",
            f"/contracts/{contract.id}/edit", "/invoices", "/invoices?status=overdue", "/invoices/new",
            f"/invoices/{invoice.id}", "/itineraries", "/itineraries/new", f"/itineraries/{itinerary.id}",
            f"/itineraries/{itinerary.id}/edit", f"/logistics/new?show={show.id}&kind=hotel",
            f"/logistics/new?artist={artist.id}", f"/logistics/{item.id}/edit", "/settings", "/settings/users",
        ]
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url


# --------------------------------------------------------------------------
# Roster and shows
# --------------------------------------------------------------------------


def test_create_artist_and_show(client, app):
    response = post(
        client, "/artists/new",
        {"name": "Test Band", "currency": "EUR", "default_fee": "1500", "commission_rate": "20", "color": "#123456", "active": "on"},
    )
    assert response.status_code == 302
    with app.app_context():
        artist = Artist.query.filter_by(name="Test Band").one()
        assert artist.default_fee == Decimal("1500.00")
        artist_id = artist.id

    response = post(
        client, "/shows/new",
        {"artist_id": artist_id, "date": "2027-03-01", "status": "confirmed", "deal_type": "flat", "fee": "2000.50",
         "currency": "EUR", "deposit_percent": "30", "set_length": "45", "set_time": "21:00"},
    )
    assert response.status_code == 302
    with app.app_context():
        show = Show.query.filter_by(artist_id=artist_id).one()
        assert show.fee == Decimal("2000.50")
        assert show.deposit_amount == Decimal("600.15")
        assert show.balance_amount == Decimal("1400.35")
        assert show.commission_amount == Decimal("400.10")


def test_invalid_form_keeps_input_and_saves_nothing(client, app):
    response = post(client, "/shows/new", {"artist_id": "", "date": "not-a-date", "event_name": "Keep me", "status": "option"})
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Keep me" in body
    assert "Artist: Required" in body


def test_invalid_select_choice_rejected(client, app):
    response = post(client, "/shows/new", {"artist_id": "99999", "date": "2027-01-01", "status": "option"})
    assert "Invalid choice" in response.get_data(as_text=True)


def test_signing_contract_confirms_show(client, app):
    with app.app_context():
        show = Show.query.filter_by(status="pending").first()
        show_id = show.id
    response = post(client, f"/shows/{show_id}/contracts")
    assert response.status_code == 302
    with app.app_context():
        contract = Contract.query.filter_by(show_id=show_id).one()
        assert "{{" not in contract.body
        assert contract.show.artist.name in contract.body
        contract_id = contract.id
    post(client, f"/contracts/{contract_id}/status", {"status": "signed"})
    with app.app_context():
        contract = db.session.get(Contract, contract_id)
        assert contract.status == "signed" and contract.signed_at == date.today()
        assert contract.show.status == "confirmed"


def test_contract_placeholders():
    text = render_template_text("Hi {{ artist_name }}, {{unknown}}", {"artist_name": "Nova"})
    assert text == "Hi Nova, {{unknown}}"


# --------------------------------------------------------------------------
# Invoices
# --------------------------------------------------------------------------


def test_invoice_lifecycle(client, app):
    with app.app_context():
        show = Show.query.filter(Show.status == "confirmed", Show.currency == "GBP").first()
        show_id, fee = show.id, show.fee
        agency = Agency.get()
        next_number = agency.next_invoice_number

    post(client, f"/shows/{show_id}/invoices", {"kind": "deposit"})
    with app.app_context():
        deposit = Invoice.query.filter_by(show_id=show_id, kind="deposit").one()
        assert deposit.number is None and deposit.status == "draft"
        assert deposit.subtotal == fee / 2
        assert deposit.bill_to_name == db.session.get(Show, show_id).promoter.company
        deposit_id = deposit.id

    post(client, f"/invoices/{deposit_id}/lines", {"description": "Backline hire", "quantity": "2", "unit_price": "100"})
    post(client, f"/invoices/{deposit_id}/issue")
    with app.app_context():
        deposit = db.session.get(Invoice, deposit_id)
        assert deposit.status == "sent"
        assert deposit.number.endswith(f"{next_number:04d}")
        assert deposit.subtotal == fee / 2 + 200
        assert deposit.total == deposit.subtotal + deposit.vat_amount

    # Issued invoices are locked.
    post(client, f"/invoices/{deposit_id}/lines", {"description": "Sneaky", "unit_price": "1"})
    with app.app_context():
        assert len(db.session.get(Invoice, deposit_id).lines) == 2

    # Balance subtracts the deposit fee line amount already invoiced.
    post(client, f"/shows/{show_id}/invoices", {"kind": "balance"})
    with app.app_context():
        balance = Invoice.query.filter_by(show_id=show_id, kind="balance").one()
        deposit = db.session.get(Invoice, deposit_id)
        assert balance.lines[0].unit_price == fee - deposit.subtotal

    post(client, f"/invoices/{deposit_id}/paid")
    with app.app_context():
        assert db.session.get(Invoice, deposit_id).status == "paid"


def test_commission_invoice_bills_artist(client, app):
    with app.app_context():
        show = Show.query.filter_by(status="confirmed").first()
        show_id, expected, billing = show.id, show.commission_amount, show.artist.billing_name
    post(client, f"/shows/{show_id}/invoices", {"kind": "commission"})
    with app.app_context():
        invoice = Invoice.query.filter_by(show_id=show_id, kind="commission").one()
        assert invoice.subtotal == expected
        assert invoice.bill_to_name == billing


def test_overdue_detection(app):
    with app.app_context():
        overdue = [i for i in Invoice.query.all() if i.is_overdue]
        assert len(overdue) == 1
        assert overdue[0].display_status == "overdue"


def test_numbers_only_taken_on_issue(client, app):
    with app.app_context():
        before = Agency.get().next_invoice_number
        show_id = Show.query.first().id
    post(client, f"/shows/{show_id}/invoices", {"kind": "full"})
    with app.app_context():
        assert Agency.get().next_invoice_number == before
        draft = Invoice.query.filter_by(show_id=show_id, kind="full", status="draft").one()
        draft_id = draft.id
    post(client, f"/invoices/{draft_id}/cancel")
    with app.app_context():
        assert db.session.get(Invoice, draft_id) is None


# --------------------------------------------------------------------------
# Itinerary
# --------------------------------------------------------------------------


def test_itinerary_days(app):
    with app.app_context():
        it = Itinerary.query.first()
        days = build_itinerary(it.artist_id, it.start_date, it.end_date)
        assert days[0].day == it.start_date and days[-1].day == it.end_date
        first = days[0]
        assert first.shows and first.kind == "Show day"
        assert any(i.kind == "flight" for i in first.travel)
        assert first.hotels_checkin
        travel_day = days[1]
        assert any(i.kind == "train" for i in travel_day.travel)


def test_shared_itinerary_is_public_and_hides_fees(app):
    with app.app_context():
        it = Itinerary.query.first()
        token_value, fee = it.share_token, f"{it.artist.shows[0].fee:,.2f}"
    anon = app.test_client()
    response = anon.get(f"/share/{token_value}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Nova Lune" in body and "Load in" in body
    assert fee not in body
    ics = anon.get(f"/share/{token_value}/calendar.ics")
    assert ics.status_code == 200 and ics.mimetype == "text/calendar"
    assert "BEGIN:VEVENT" in ics.get_data(as_text=True)
    assert anon.get("/share/not-a-real-token").status_code == 404


def test_disabled_share_link_404s(client, app):
    with app.app_context():
        it = Itinerary.query.first()
        it.share_enabled = False
        db.session.commit()
        token_value = it.share_token
    assert app.test_client().get(f"/share/{token_value}").status_code == 404


def test_logistics_validation(client, app):
    with app.app_context():
        show = Show.query.first()
        show_id = show.id
        count = LogisticsItem.query.count()
    response = post(
        client, f"/logistics/new?show={show_id}&kind=flight",
        {"kind": "flight", "status": "booked", "start_at": "2027-01-01T10:00", "end_at": "2027-01-01T09:00", "currency": "EUR"},
    )
    assert response.status_code == 200
    assert "Must be after the start" in response.get_data(as_text=True)
    with app.app_context():
        assert LogisticsItem.query.count() == count
    response = post(
        client, f"/logistics/new?show={show_id}&kind=flight",
        {"kind": "flight", "status": "booked", "show_id": str(show_id), "start_at": "2027-01-01T10:00", "end_at": "2027-01-01T12:00",
         "currency": "EUR", "from_place": "BER", "to_place": "LIS", "cost": "199.99"},
    )
    assert response.status_code == 302
    with app.app_context():
        assert LogisticsItem.query.count() == count + 1


def test_cannot_delete_show_with_issued_invoice(client, app):
    with app.app_context():
        show = next(s for s in Show.query.all() if any(i.number for i in s.invoices))
        show_id = show.id
    post(client, f"/shows/{show_id}/delete")
    with app.app_context():
        assert db.session.get(Show, show_id) is not None


def test_non_admin_cannot_open_settings(client, app):
    with app.app_context():
        user = User(name="Agent", email="agent@tourdesk.local", is_admin=False)
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
    other = app.test_client()
    login(other, "agent@tourdesk.local", "password123")
    assert other.get("/settings").status_code == 403
    assert other.get("/").status_code == 200
