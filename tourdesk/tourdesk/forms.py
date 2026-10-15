"""Small declarative form helper.

Each form is a list of ``Field`` objects. ``render`` support lives in
``templates/_macros.html``; ``populate`` parses submitted values onto a model
and returns a dict of errors keyed by field label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Callable

from .models import (
    CONTRACT_STATUSES,
    DEAL_TYPES,
    INVOICE_KINDS,
    LOGISTICS_KINDS,
    LOGISTICS_STATUSES,
    SHOW_STATUSES,
)

CURRENCIES = [(c, c) for c in ("EUR", "USD", "GBP", "CHF", "CAD", "AUD", "SEK", "NOK", "DKK", "PLN", "JPY")]


@dataclass
class Field:
    name: str
    label: str
    type: str = "text"  # text, textarea, email, number, money, percent, date, datetime, time, select, checkbox, color
    required: bool = False
    choices: list | Callable[[], list] | None = None
    help: str = ""
    wide: bool = False
    placeholder: str = ""
    extra: dict = field(default_factory=dict)

    def get_choices(self) -> list:
        choices = self.choices() if callable(self.choices) else (self.choices or [])
        return [(str(value), label) for value, label in choices]

    def display_value(self, obj) -> str:
        value = getattr(obj, self.name, None) if obj is not None else None
        if value is None:
            return ""
        if self.type == "date" and isinstance(value, date):
            return value.isoformat()
        if self.type == "datetime" and isinstance(value, datetime):
            return value.strftime("%Y-%m-%dT%H:%M")
        if self.type in ("money", "percent", "number") and isinstance(value, (int, float, Decimal)):
            if self.type == "money":
                return f"{Decimal(str(value)):.2f}"
            return f"{value:g}" if isinstance(value, float) else str(value)
        return str(value)


def parse_value(f: Field, raw: str | None):
    """Return ``(value, error)`` for one submitted field."""
    if f.type == "checkbox":
        return raw in ("on", "1", "true", "yes"), None
    raw = (raw or "").strip()
    if raw == "":
        if f.required:
            return None, "Required"
        if f.type in ("money", "percent"):
            return 0, None
        if f.type in ("number", "date", "datetime", "select_int"):
            return None, None
        return "", None
    try:
        if f.type == "number":
            return int(raw), None
        if f.type == "money":
            return Decimal(raw.replace(",", "")), None
        if f.type == "percent":
            value = float(raw)
            if not 0 <= value <= 100:
                return None, "Must be between 0 and 100"
            return value, None
        if f.type == "date":
            return date.fromisoformat(raw), None
        if f.type == "datetime":
            return datetime.fromisoformat(raw), None
        if f.type == "time":
            datetime.strptime(raw, "%H:%M")
            return raw, None
        if f.type == "select_int":
            if raw not in {v for v, _ in f.get_choices()}:
                return None, "Invalid choice"
            return int(raw), None
        if f.type == "select":
            if raw not in {v for v, _ in f.get_choices()}:
                return None, "Invalid choice"
            return raw, None
        if f.type == "color":
            if len(raw) != 7 or not raw.startswith("#"):
                return None, "Use a hex colour like #3366ff"
            int(raw[1:], 16)
            return raw, None
    except (ValueError, InvalidOperation):
        return None, "Invalid value"
    return raw, None


def populate(obj, fields: list[Field], form) -> dict:
    """Parse ``form`` into ``obj``. Nothing is assigned unless every field is
    valid. Returns errors keyed by field label."""
    errors = {}
    values = {}
    for f in fields:
        value, error = parse_value(f, form.get(f.name))
        if error:
            errors[f.label] = error
        else:
            values[f.name] = value
    if not errors:
        for name, value in values.items():
            setattr(obj, name, value)
    return errors


# --------------------------------------------------------------------------
# Form definitions. Choice lists that depend on the database are callables
# so they are evaluated at render time.
# --------------------------------------------------------------------------


def _artists():
    from .models import Artist

    return [(a.id, a.name) for a in Artist.query.order_by(Artist.name)]


def _venues():
    from .models import Venue

    return [("", "None")] + [(v.id, f"{v.name} ({v.city})" if v.city else v.name) for v in Venue.query.order_by(Venue.name)]


def _promoters():
    from .models import Promoter

    return [("", "None")] + [(p.id, p.company) for p in Promoter.query.order_by(Promoter.company)]


def _agents():
    from .models import User

    return [("", "Unassigned")] + [(u.id, u.name) for u in User.query.order_by(User.name)]


ARTIST_FIELDS = [
    Field("name", "Artist name", required=True),
    Field("genre", "Genre"),
    Field("home_city", "Home city"),
    Field("country", "Country"),
    Field("email", "Email", "email"),
    Field("phone", "Phone"),
    Field("website", "Website"),
    Field("agent_id", "Responsible agent", "select_int", choices=_agents),
    Field("default_fee", "Default fee", "money"),
    Field("currency", "Currency", "select", choices=CURRENCIES),
    Field("commission_rate", "Agency commission %", "percent"),
    Field("color", "Calendar colour", "color"),
    Field("billing_name", "Billing name", help="Used on commission invoices to the artist"),
    Field("vat_number", "VAT number"),
    Field("billing_address", "Billing address", "textarea", wide=True),
    Field("bio", "Bio", "textarea", wide=True),
    Field("tech_rider", "Technical rider", "textarea", wide=True),
    Field("hospitality_rider", "Hospitality rider", "textarea", wide=True),
    Field("active", "Active on roster", "checkbox"),
]

MEMBER_FIELDS = [
    Field("name", "Name", required=True),
    Field("role", "Role", placeholder="Tour manager, drums, FOH..."),
    Field("email", "Email", "email"),
    Field("phone", "Phone"),
]

VENUE_FIELDS = [
    Field("name", "Venue name", required=True),
    Field("address", "Address"),
    Field("city", "City"),
    Field("country", "Country"),
    Field("capacity", "Capacity", "number"),
    Field("website", "Website"),
    Field("contact_name", "Contact name"),
    Field("email", "Email", "email"),
    Field("phone", "Phone"),
    Field("notes", "Notes", "textarea", wide=True),
]

PROMOTER_FIELDS = [
    Field("company", "Company", required=True),
    Field("contact_name", "Contact name"),
    Field("email", "Email", "email"),
    Field("phone", "Phone"),
    Field("city", "City"),
    Field("country", "Country"),
    Field("vat_number", "VAT number"),
    Field("billing_address", "Billing address", "textarea", wide=True),
    Field("notes", "Notes", "textarea", wide=True),
]

SHOW_FIELDS = [
    Field("artist_id", "Artist", "select_int", required=True, choices=_artists),
    Field("date", "Date", "date", required=True),
    Field("status", "Status", "select", choices=SHOW_STATUSES),
    Field("event_name", "Event / festival name"),
    Field("venue_id", "Venue", "select_int", choices=_venues),
    Field("promoter_id", "Promoter", "select_int", choices=_promoters),
    Field("city", "City", help="Leave blank to use the venue's city"),
    Field("country", "Country"),
    # Deal
    Field("deal_type", "Deal type", "select", choices=DEAL_TYPES),
    Field("fee", "Guarantee / fee", "money"),
    Field("currency", "Currency", "select", choices=CURRENCIES),
    Field("percentage", "Door percentage", "percent", help="Used for versus, bonus and door split deals"),
    Field("deposit_percent", "Deposit %", "percent"),
    Field("hospitality_buyout", "Hospitality buyout", "money"),
    Field("ticket_price", "Ticket price", "money"),
    Field("capacity", "Capacity", "number"),
    # Schedule
    Field("load_in", "Load in", "time"),
    Field("soundcheck", "Soundcheck", "time"),
    Field("doors_time", "Doors", "time"),
    Field("set_time", "Set time", "time"),
    Field("set_length", "Set length (min)", "number"),
    Field("curfew", "Curfew", "time"),
    Field("production_notes", "Production / advancing notes", "textarea", wide=True),
    Field("notes", "Internal notes", "textarea", wide=True),
]

SHOW_SECTIONS = [
    ("Show", SHOW_FIELDS[:8]),
    ("Deal", SHOW_FIELDS[8:16]),
    ("Schedule", SHOW_FIELDS[16:]),
]


def _artist_shows_for(artist_id):
    def choices():
        from .models import Show

        query = Show.query.order_by(Show.date)
        if artist_id:
            query = query.filter_by(artist_id=artist_id)
        return [("", "Not tied to a show")] + [(s.id, f"{s.date:%d %b %Y} · {s.title}") for s in query]

    return choices


def logistics_fields(artist_id=None) -> list[Field]:
    return [
        Field("kind", "Type", "select", choices=LOGISTICS_KINDS),
        Field("status", "Status", "select", choices=LOGISTICS_STATUSES),
        Field("show_id", "Linked show", "select_int", choices=_artist_shows_for(artist_id)),
        Field("title", "Title", placeholder="Optional, e.g. LH 1234"),
        Field("provider", "Airline / company / hotel"),
        Field("reference", "Booking reference"),
        Field("start_at", "Departs / check in", "datetime", required=True),
        Field("end_at", "Arrives / check out", "datetime"),
        Field("from_place", "From"),
        Field("to_place", "To"),
        Field("address", "Address", help="Hotel or pickup address"),
        Field("travellers", "Travellers", placeholder="Who is on this booking"),
        Field("cost", "Cost", "money"),
        Field("currency", "Currency", "select", choices=CURRENCIES),
        Field("notes", "Notes", "textarea", wide=True),
    ]


ITINERARY_FIELDS = [
    Field("artist_id", "Artist", "select_int", required=True, choices=_artists),
    Field("title", "Title", required=True, placeholder="Spring tour 2027"),
    Field("start_date", "From", "date", required=True),
    Field("end_date", "To", "date", required=True),
    Field("share_enabled", "Enable public share link", "checkbox"),
    Field("notes", "Notes for the travel party", "textarea", wide=True),
]

CONTRACT_FIELDS = [
    Field("status", "Status", "select", choices=CONTRACT_STATUSES),
    Field("sent_at", "Sent on", "date"),
    Field("signed_at", "Signed on", "date"),
    Field("body", "Contract text", "textarea", wide=True, required=True, extra={"rows": 30}),
]

INVOICE_FIELDS = [
    Field("kind", "Type", "select", choices=INVOICE_KINDS),
    Field("currency", "Currency", "select", choices=CURRENCIES),
    Field("vat_rate", "VAT %", "percent"),
    Field("due_date", "Due date", "date"),
    Field("bill_to_name", "Bill to", required=True),
    Field("bill_to_email", "Bill to email", "email"),
    Field("bill_to_vat", "Bill to VAT number"),
    Field("bill_to_address", "Bill to address", "textarea", wide=True),
    Field("notes", "Notes on invoice", "textarea", wide=True),
]

AGENCY_FIELDS = [
    Field("name", "Agency name", required=True),
    Field("email", "Email", "email"),
    Field("phone", "Phone"),
    Field("vat_number", "VAT number"),
    Field("iban", "IBAN"),
    Field("bic", "BIC / SWIFT"),
    Field("default_currency", "Default currency", "select", choices=CURRENCIES),
    Field("default_vat_rate", "Default VAT %", "percent"),
    Field("payment_terms_days", "Payment terms (days)", "number", required=True),
    Field("invoice_prefix", "Invoice number prefix", required=True),
    Field("next_invoice_number", "Next invoice number", "number", required=True),
    Field("contract_prefix", "Contract number prefix", required=True),
    Field("next_contract_number", "Next contract number", "number", required=True),
    Field("address", "Address", "textarea", wide=True),
    Field("invoice_footer", "Invoice footer", "textarea", wide=True),
    Field(
        "contract_template",
        "Contract template",
        "textarea",
        wide=True,
        required=True,
        extra={"rows": 24},
        help="Placeholders like {{artist_name}} are filled from the show. See the list below.",
    ),
]
