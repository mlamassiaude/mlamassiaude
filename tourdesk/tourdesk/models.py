"""Database models.

Money is stored as integer cents (see ``Money``) so SQLite never rounds an
amount, and is exposed to Python as ``Decimal``.
"""

import secrets
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.types import Integer, TypeDecorator
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

CENT = Decimal("0.01")


def to_money(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


class Money(TypeDecorator):
    impl = Integer
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return int(to_money(value) * 100)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return (Decimal(value) / 100).quantize(CENT)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


# --------------------------------------------------------------------------
# Agency and users
# --------------------------------------------------------------------------

DEFAULT_CONTRACT_TEMPLATE = """ARTIST ENGAGEMENT CONTRACT

Contract no. {{contract_number}}, issued {{today}}

This agreement is made between {{promoter_company}} ("the Promoter"), {{promoter_address}}, and {{agency_name}} acting as agent on behalf of {{artist_name}} ("the Artist").

1. ENGAGEMENT
The Promoter engages the Artist to perform at {{event_name}}, {{venue_name}}, {{venue_address}}, {{venue_city}}, {{venue_country}} on {{show_date}}.

2. SCHEDULE
Load in: {{load_in}}
Soundcheck: {{soundcheck}}
Doors: {{doors_time}}
Set time: {{set_time}} ({{set_length}} minutes)
Curfew: {{curfew}}

3. FEE
Deal: {{deal_summary}}
The Promoter shall pay a deposit of {{deposit_amount}} {{currency}} ({{deposit_percent}}%) upon signature of this contract. The balance of {{balance_amount}} {{currency}} is due no later than the day of the performance.

4. HOSPITALITY AND TECHNICAL RIDER
The Artist's technical and hospitality riders form an integral part of this agreement. Hospitality buyout: {{hospitality_buyout}} {{currency}}.

5. CANCELLATION
If the Promoter cancels the engagement less than 30 days before the show date, the full fee remains payable. Force majeure releases both parties from their obligations without liability.

6. ADDITIONAL TERMS
{{notes}}


For the Promoter                          For the Artist
{{promoter_contact}}                      {{agency_name}}, on behalf of {{artist_name}}


Signature: ____________________           Signature: ____________________
Date:      ____________________           Date:      ____________________
"""


class Agency(db.Model):
    """Single row holding the agency's own details and numbering."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, default="My Agency")
    address = db.Column(db.Text, default="")
    email = db.Column(db.String(200), default="")
    phone = db.Column(db.String(50), default="")
    vat_number = db.Column(db.String(50), default="")
    iban = db.Column(db.String(50), default="")
    bic = db.Column(db.String(20), default="")
    default_currency = db.Column(db.String(3), default="EUR", nullable=False)
    default_vat_rate = db.Column(db.Numeric(5, 2, asdecimal=False), default=0, nullable=False)
    payment_terms_days = db.Column(db.Integer, default=30, nullable=False)
    invoice_prefix = db.Column(db.String(20), default="INV-", nullable=False)
    next_invoice_number = db.Column(db.Integer, default=1, nullable=False)
    contract_prefix = db.Column(db.String(20), default="CON-", nullable=False)
    next_contract_number = db.Column(db.Integer, default=1, nullable=False)
    contract_template = db.Column(db.Text, default=DEFAULT_CONTRACT_TEMPLATE, nullable=False)
    invoice_footer = db.Column(db.Text, default="")

    @classmethod
    def get(cls) -> "Agency":
        agency = db.session.get(cls, 1)
        if agency is None:
            agency = cls(id=1)
            db.session.add(agency)
            db.session.flush()
        return agency

    def take_invoice_number(self) -> str:
        year = date.today().year
        number = f"{self.invoice_prefix}{year}-{self.next_invoice_number:04d}"
        self.next_invoice_number += 1
        return number

    def take_contract_number(self) -> str:
        year = date.today().year
        number = f"{self.contract_prefix}{year}-{self.next_contract_number:04d}"
        self.next_contract_number += 1
        return number


class User(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


# --------------------------------------------------------------------------
# Roster and contacts
# --------------------------------------------------------------------------


class Artist(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    genre = db.Column(db.String(120), default="")
    home_city = db.Column(db.String(120), default="")
    country = db.Column(db.String(120), default="")
    email = db.Column(db.String(200), default="")
    phone = db.Column(db.String(50), default="")
    website = db.Column(db.String(300), default="")
    bio = db.Column(db.Text, default="")
    default_fee = db.Column(Money, default=0)
    currency = db.Column(db.String(3), default="EUR", nullable=False)
    commission_rate = db.Column(db.Numeric(5, 2, asdecimal=False), default=15, nullable=False)
    billing_name = db.Column(db.String(200), default="")
    billing_address = db.Column(db.Text, default="")
    vat_number = db.Column(db.String(50), default="")
    tech_rider = db.Column(db.Text, default="")
    hospitality_rider = db.Column(db.Text, default="")
    color = db.Column(db.String(7), default="#5b5bd6")
    active = db.Column(db.Boolean, default=True, nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    agent = db.relationship("User")
    members = db.relationship(
        "ArtistMember", back_populates="artist", cascade="all, delete-orphan", order_by="ArtistMember.name"
    )
    shows = db.relationship("Show", back_populates="artist", order_by="Show.date")


class ArtistMember(db.Model):
    """Someone in the artist's travel party: band member, tour manager, crew."""

    id = db.Column(db.Integer, primary_key=True)
    artist_id = db.Column(db.Integer, db.ForeignKey("artist.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(120), default="")
    email = db.Column(db.String(200), default="")
    phone = db.Column(db.String(50), default="")

    artist = db.relationship("Artist", back_populates="members")


class Venue(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(300), default="")
    city = db.Column(db.String(120), default="")
    country = db.Column(db.String(120), default="")
    capacity = db.Column(db.Integer)
    contact_name = db.Column(db.String(200), default="")
    email = db.Column(db.String(200), default="")
    phone = db.Column(db.String(50), default="")
    website = db.Column(db.String(300), default="")
    notes = db.Column(db.Text, default="")

    shows = db.relationship("Show", back_populates="venue")


class Promoter(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company = db.Column(db.String(200), nullable=False)
    contact_name = db.Column(db.String(200), default="")
    email = db.Column(db.String(200), default="")
    phone = db.Column(db.String(50), default="")
    billing_address = db.Column(db.Text, default="")
    city = db.Column(db.String(120), default="")
    country = db.Column(db.String(120), default="")
    vat_number = db.Column(db.String(50), default="")
    notes = db.Column(db.Text, default="")

    shows = db.relationship("Show", back_populates="promoter")


# --------------------------------------------------------------------------
# Shows, deals and logistics
# --------------------------------------------------------------------------

SHOW_STATUSES = [
    ("option", "Option"),
    ("pending", "Pending"),
    ("confirmed", "Confirmed"),
    ("played", "Played"),
    ("cancelled", "Cancelled"),
]

DEAL_TYPES = [
    ("flat", "Flat fee"),
    ("versus", "Guarantee vs % of net door"),
    ("guarantee_plus", "Guarantee + % bonus"),
    ("door_split", "Door split"),
]


class Show(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    artist_id = db.Column(db.Integer, db.ForeignKey("artist.id"), nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("venue.id"))
    promoter_id = db.Column(db.Integer, db.ForeignKey("promoter.id"))
    date = db.Column(db.Date, nullable=False)
    event_name = db.Column(db.String(200), default="")
    city = db.Column(db.String(120), default="")
    country = db.Column(db.String(120), default="")
    status = db.Column(db.String(20), default="option", nullable=False)

    deal_type = db.Column(db.String(20), default="flat", nullable=False)
    fee = db.Column(Money, default=0)
    currency = db.Column(db.String(3), default="EUR", nullable=False)
    percentage = db.Column(db.Numeric(5, 2, asdecimal=False), default=0)
    deposit_percent = db.Column(db.Numeric(5, 2, asdecimal=False), default=50)
    hospitality_buyout = db.Column(Money, default=0)
    ticket_price = db.Column(Money, default=0)
    capacity = db.Column(db.Integer)

    load_in = db.Column(db.String(5), default="")
    soundcheck = db.Column(db.String(5), default="")
    doors_time = db.Column(db.String(5), default="")
    set_time = db.Column(db.String(5), default="")
    set_length = db.Column(db.Integer, default=60)
    curfew = db.Column(db.String(5), default="")

    production_notes = db.Column(db.Text, default="")
    notes = db.Column(db.Text, default="")

    artist = db.relationship("Artist", back_populates="shows")
    venue = db.relationship("Venue", back_populates="shows")
    promoter = db.relationship("Promoter", back_populates="shows")
    logistics = db.relationship("LogisticsItem", back_populates="show", order_by="LogisticsItem.start_at")
    contracts = db.relationship(
        "Contract", back_populates="show", cascade="all, delete-orphan", order_by="Contract.created_at"
    )
    invoices = db.relationship("Invoice", back_populates="show", order_by="Invoice.created_at")

    @property
    def display_city(self) -> str:
        return self.city or (self.venue.city if self.venue else "")

    @property
    def display_country(self) -> str:
        return self.country or (self.venue.country if self.venue else "")

    @property
    def title(self) -> str:
        where = self.event_name or (self.venue.name if self.venue else self.display_city)
        return f"{self.artist.name} @ {where}" if where else self.artist.name

    @property
    def deposit_amount(self) -> Decimal:
        return to_money((self.fee or 0) * to_money(self.deposit_percent or 0) / 100)

    @property
    def balance_amount(self) -> Decimal:
        return to_money((self.fee or 0) - self.deposit_amount)

    @property
    def commission_amount(self) -> Decimal:
        return to_money((self.fee or 0) * to_money(self.artist.commission_rate or 0) / 100)

    @property
    def deal_summary(self) -> str:
        fee = f"{to_money(self.fee):,.2f} {self.currency}"
        pct = f"{to_money(self.percentage or 0):g}%"
        if self.deal_type == "versus":
            return f"{fee} guarantee versus {pct} of net door receipts, whichever is greater"
        if self.deal_type == "guarantee_plus":
            return f"{fee} guarantee plus {pct} of net door receipts after break-even"
        if self.deal_type == "door_split":
            return f"{pct} of net door receipts"
        return f"{fee} flat fee"

    @property
    def invoiced_total(self) -> Decimal:
        return sum(
            (
                i.subtotal
                for i in self.invoices
                if i.kind in ("deposit", "balance", "full") and i.status in ("sent", "paid")
            ),
            Decimal("0.00"),
        )


LOGISTICS_KINDS = [
    ("flight", "Flight"),
    ("train", "Train"),
    ("car", "Car / van"),
    ("ground", "Ground transfer"),
    ("hotel", "Hotel"),
    ("other", "Other"),
]

LOGISTICS_STATUSES = [("to_book", "To book"), ("booked", "Booked"), ("cancelled", "Cancelled")]


class LogisticsItem(TimestampMixin, db.Model):
    """A travel leg, hotel stay or other booking for an artist.

    Items belong to an artist and can optionally be tied to a show, so travel
    days and days off still appear on the itinerary.
    """

    id = db.Column(db.Integer, primary_key=True)
    artist_id = db.Column(db.Integer, db.ForeignKey("artist.id"), nullable=False)
    show_id = db.Column(db.Integer, db.ForeignKey("show.id"))
    kind = db.Column(db.String(20), default="flight", nullable=False)
    status = db.Column(db.String(20), default="to_book", nullable=False)
    title = db.Column(db.String(200), default="")
    provider = db.Column(db.String(200), default="")
    reference = db.Column(db.String(100), default="")
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime)
    from_place = db.Column(db.String(200), default="")
    to_place = db.Column(db.String(200), default="")
    address = db.Column(db.String(300), default="")
    travellers = db.Column(db.String(300), default="")
    cost = db.Column(Money, default=0)
    currency = db.Column(db.String(3), default="EUR", nullable=False)
    notes = db.Column(db.Text, default="")

    artist = db.relationship("Artist")
    show = db.relationship("Show", back_populates="logistics")

    @property
    def label(self) -> str:
        if self.title:
            return self.title
        if self.kind == "hotel":
            return self.provider or "Hotel"
        if self.from_place or self.to_place:
            return f"{self.from_place} → {self.to_place}"
        return dict(LOGISTICS_KINDS).get(self.kind, self.kind)


class Itinerary(TimestampMixin, db.Model):
    """A date range for one artist, shareable read only via a secret link."""

    id = db.Column(db.Integer, primary_key=True)
    artist_id = db.Column(db.Integer, db.ForeignKey("artist.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text, default="")
    share_token = db.Column(db.String(64), unique=True, default=lambda: secrets.token_urlsafe(24))
    share_enabled = db.Column(db.Boolean, default=False, nullable=False)

    artist = db.relationship("Artist")


# --------------------------------------------------------------------------
# Contracts and invoices
# --------------------------------------------------------------------------

CONTRACT_STATUSES = [("draft", "Draft"), ("sent", "Sent"), ("signed", "Signed"), ("cancelled", "Cancelled")]


class Contract(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    show_id = db.Column(db.Integer, db.ForeignKey("show.id"), nullable=False)
    number = db.Column(db.String(50), unique=True, nullable=False)
    status = db.Column(db.String(20), default="draft", nullable=False)
    body = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.Date)
    signed_at = db.Column(db.Date)

    show = db.relationship("Show", back_populates="contracts")


INVOICE_STATUSES = [("draft", "Draft"), ("sent", "Sent"), ("paid", "Paid"), ("cancelled", "Cancelled")]
INVOICE_KINDS = [
    ("deposit", "Deposit"),
    ("balance", "Balance"),
    ("full", "Full fee"),
    ("commission", "Agency commission"),
    ("other", "Other"),
]


class Invoice(TimestampMixin, db.Model):
    """An invoice. Bill-to details are copied at creation so later edits to a
    promoter or artist never change an invoice that has already gone out."""

    id = db.Column(db.Integer, primary_key=True)
    show_id = db.Column(db.Integer, db.ForeignKey("show.id"))
    number = db.Column(db.String(50), unique=True)
    kind = db.Column(db.String(20), default="full", nullable=False)
    status = db.Column(db.String(20), default="draft", nullable=False)
    issue_date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    paid_at = db.Column(db.Date)
    currency = db.Column(db.String(3), default="EUR", nullable=False)
    vat_rate = db.Column(db.Numeric(5, 2, asdecimal=False), default=0, nullable=False)
    bill_to_name = db.Column(db.String(200), default="")
    bill_to_address = db.Column(db.Text, default="")
    bill_to_vat = db.Column(db.String(50), default="")
    bill_to_email = db.Column(db.String(200), default="")
    notes = db.Column(db.Text, default="")

    show = db.relationship("Show", back_populates="invoices")
    lines = db.relationship(
        "InvoiceLine", back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.id"
    )

    @property
    def subtotal(self) -> Decimal:
        return sum((line.total for line in self.lines), Decimal("0.00"))

    @property
    def vat_amount(self) -> Decimal:
        return to_money(self.subtotal * to_money(self.vat_rate or 0) / 100)

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.vat_amount

    @property
    def is_overdue(self) -> bool:
        return self.status == "sent" and self.due_date is not None and self.due_date < date.today()

    @property
    def display_status(self) -> str:
        return "overdue" if self.is_overdue else self.status

    @property
    def display_number(self) -> str:
        return self.number or f"Draft #{self.id}"


class InvoiceLine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoice.id"), nullable=False)
    description = db.Column(db.String(300), nullable=False)
    quantity = db.Column(db.Numeric(10, 2, asdecimal=False), default=1, nullable=False)
    unit_price = db.Column(Money, default=0, nullable=False)

    invoice = db.relationship("Invoice", back_populates="lines")

    @property
    def total(self) -> Decimal:
        return to_money(to_money(self.quantity) * self.unit_price)
