"""Demo data so a fresh install has something to click through."""

from datetime import date, datetime, time, timedelta

from .models import Agency, Artist, ArtistMember, Itinerary, LogisticsItem, Promoter, Show, User, Venue, db
from .services import create_contract, create_invoice_for_show, issue_invoice


def seed() -> None:
    if Artist.query.first() is not None:
        print("Database already has artists, skipping demo data.")
        return

    agency = Agency.get()
    agency.name = "Northern Lights Booking"
    agency.address = "Torstrasse 101\n10119 Berlin\nGermany"
    agency.email = "bookings@northernlights.example"
    agency.phone = "+49 30 1234567"
    agency.vat_number = "DE123456789"
    agency.iban = "DE89 3704 0044 0532 0130 00"
    agency.bic = "COBADEFFXXX"
    agency.default_vat_rate = 19
    agency.invoice_footer = "Thank you. Please quote the invoice number with your payment."

    user = User.query.filter_by(email="demo@tourdesk.local").first()
    if user is None:
        user = User(name="Demo Agent", email="demo@tourdesk.local", is_admin=True)
        user.set_password("demo1234")
        db.session.add(user)

    nova = Artist(
        name="Nova Lune", genre="Electronic / live", home_city="Berlin", country="Germany", default_fee=4500,
        currency="EUR", commission_rate=15, color="#5b5bd6", agent=user, email="mgmt@novalune.example",
        billing_name="Nova Lune GbR", billing_address="Weserstrasse 12\n12047 Berlin", active=True,
        tech_rider="2x CDJ-3000, 1x DJM-V10, 2 monitors at the booth, DI for live synth.",
        hospitality_rider="Vegetarian dinner for 3, still water, local beer.",
    )
    copper = Artist(
        name="The Copper Days", genre="Indie rock", home_city="Manchester", country="UK", default_fee=3000,
        currency="GBP", commission_rate=12.5, color="#d6455b", agent=user, active=True,
        billing_name="Copper Days Ltd", billing_address="12 Oldham Street\nManchester M1 1JQ",
    )
    mira = Artist(
        name="Mira Okafor", genre="Soul / R&B", home_city="Paris", country="France", default_fee=6000,
        currency="EUR", commission_rate=15, color="#1f9d74", agent=user, active=True,
    )
    db.session.add_all([nova, copper, mira])
    nova.members = [
        ArtistMember(name="Lena Vogt", role="Artist", phone="+49 151 000000"),
        ArtistMember(name="Jonas Reiter", role="Tour manager", phone="+49 151 111111"),
        ArtistMember(name="Ana Duarte", role="Lights / VJ"),
    ]
    copper.members = [
        ArtistMember(name="Sam Hughes", role="Vocals / guitar"),
        ArtistMember(name="Priya Nair", role="Bass"),
        ArtistMember(name="Tom Byrne", role="Drums"),
        ArtistMember(name="Kate Moss", role="Tour manager / FOH"),
    ]

    venues = {
        "trouw": Venue(name="De School", address="Doctor Jan van Breemenstraat 1", city="Amsterdam", country="Netherlands", capacity=900, contact_name="Production office", phone="+31 20 000 0000"),
        "nuits": Venue(name="La Gaîté Lyrique", address="3bis Rue Papin", city="Paris", country="France", capacity=750),
        "village": Venue(name="Village Underground", address="54 Holywell Lane", city="London", country="UK", capacity=700),
        "bad": Venue(name="Badehaus", address="Revaler Strasse 99", city="Berlin", country="Germany", capacity=500),
        "razz": Venue(name="Razzmatazz", address="Carrer dels Almogàvers 122", city="Barcelona", country="Spain", capacity=1500),
    }
    db.session.add_all(venues.values())

    promoters = {
        "nl": Promoter(company="Lowlands Live BV", contact_name="Eva de Wit", email="eva@lowlandslive.example", billing_address="Prinsengracht 200\n1016 HA Amsterdam\nNetherlands", vat_number="NL123456789B01", country="Netherlands"),
        "fr": Promoter(company="Soirées Collectives SAS", contact_name="Hugo Martin", email="hugo@soirees.example", billing_address="10 Rue Oberkampf\n75011 Paris\nFrance", vat_number="FR12345678901", country="France"),
        "uk": Promoter(company="Eastside Promotions Ltd", contact_name="Leah Brooks", email="leah@eastside.example", billing_address="1 Shoreditch High St\nLondon E1 6JE", country="UK"),
        "es": Promoter(company="Ciutat Sonora SL", contact_name="Marta Puig", email="marta@ciutat.example", billing_address="Carrer de Pujades 77\n08005 Barcelona", country="Spain"),
    }
    db.session.add_all(promoters.values())
    db.session.flush()

    today = date.today()
    start = today + timedelta(days=12)

    def show(artist, offset, venue, promoter, status, fee, **kw):
        s = Show(
            artist=artist, date=start + timedelta(days=offset), venue=venues[venue], promoter=promoters[promoter],
            status=status, fee=fee, currency=artist.currency, deal_type=kw.pop("deal_type", "flat"),
            deposit_percent=50, load_in="16:00", soundcheck="18:00", doors_time="20:00", set_time=kw.pop("set_time", "22:30"),
            set_length=kw.pop("set_length", 75), curfew="01:00", **kw,
        )
        db.session.add(s)
        return s

    s1 = show(nova, 0, "trouw", "nl", "confirmed", 4500, production_notes="Load in via back entrance on Jan van Breemenstraat. Parking for one van.")
    s2 = show(nova, 2, "nuits", "fr", "confirmed", 5000, deal_type="versus", percentage=70, ticket_price=24)
    s3 = show(nova, 4, "razz", "es", "pending", 5500, hospitality_buyout=150)
    show(nova, 30, "bad", "nl", "option", 4000)
    s5 = show(copper, 6, "village", "uk", "confirmed", 3200, deal_type="guarantee_plus", percentage=80, set_time="21:15", set_length=60)
    show(mira, 20, "nuits", "fr", "option", 6500)
    played = show(copper, -40, "bad", "nl", "played", 2800)
    db.session.flush()

    def at(d, h, m=0):
        return datetime.combine(d, time(h, m))

    db.session.add_all([
        LogisticsItem(artist=nova, show=s1, kind="flight", status="booked", provider="KLM", title="KL 1772", reference="X7Y8Z9",
                      start_at=at(s1.date, 9, 40), end_at=at(s1.date, 11, 5), from_place="Berlin BER", to_place="Amsterdam AMS",
                      travellers="Lena Vogt, Jonas Reiter, Ana Duarte", cost=486, currency="EUR"),
        LogisticsItem(artist=nova, show=s1, kind="ground", status="booked", provider="Promoter runner", start_at=at(s1.date, 11, 30),
                      end_at=at(s1.date, 12, 15), from_place="AMS arrivals", to_place="Hotel"),
        LogisticsItem(artist=nova, show=s1, kind="hotel", status="booked", provider="Hotel V Nesplein", address="Nes 49, Amsterdam",
                      reference="HV-22831", start_at=at(s1.date, 15), end_at=at(s1.date + timedelta(days=1), 11), travellers="3 rooms"),
        LogisticsItem(artist=nova, kind="train", status="booked", provider="Eurostar", title="Amsterdam → Paris", reference="EUR-5521",
                      start_at=at(s1.date + timedelta(days=1), 12, 16), end_at=at(s1.date + timedelta(days=1), 15, 35),
                      from_place="Amsterdam Centraal", to_place="Paris Nord", cost=387, currency="EUR"),
        LogisticsItem(artist=nova, show=s2, kind="hotel", status="to_book", provider="Hotel near venue", start_at=at(s2.date - timedelta(days=1), 16),
                      end_at=at(s2.date + timedelta(days=1), 11), address="3e arrondissement"),
        LogisticsItem(artist=nova, show=s3, kind="flight", status="to_book", start_at=at(s3.date, 10), from_place="Paris CDG", to_place="Barcelona BCN"),
    ])

    db.session.add(Itinerary(artist=nova, title="Nova Lune · Autumn run", start_date=s1.date - timedelta(days=0),
                             end_date=s3.date + timedelta(days=1), share_enabled=True,
                             notes="Passports needed for every leg. Jonas is the day of show contact."))

    # Documents: a signed contract with a paid deposit, a sent contract, and an overdue invoice on a past show.
    c1 = create_contract(s1)
    c1.status, c1.sent_at, c1.signed_at = "signed", today - timedelta(days=20), today - timedelta(days=15)
    dep = create_invoice_for_show(s1, "deposit")
    issue_invoice(dep)
    dep.issue_date, dep.due_date = today - timedelta(days=15), today + timedelta(days=5)
    dep.status, dep.paid_at = "paid", today - timedelta(days=10)
    c2 = create_contract(s2)
    c2.status, c2.sent_at = "sent", today - timedelta(days=4)
    create_contract(s5)
    create_invoice_for_show(s2, "deposit")
    old = create_invoice_for_show(played, "full")
    issue_invoice(old)
    old.issue_date = played.date
    old.due_date = played.date + timedelta(days=14)
    db.session.commit()
