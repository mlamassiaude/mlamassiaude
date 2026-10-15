"""Business logic shared by the views: contracts, invoices, itineraries."""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from .models import (
    Agency,
    Contract,
    Invoice,
    InvoiceLine,
    LogisticsItem,
    Show,
    db,
    to_money,
)

# --------------------------------------------------------------------------
# Contracts
# --------------------------------------------------------------------------

PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")

CONTRACT_PLACEHOLDERS = {
    "contract_number": "Contract number",
    "today": "Date the contract is generated",
    "agency_name": "Your agency name",
    "agency_address": "Your agency address",
    "artist_name": "Artist name",
    "promoter_company": "Promoter company",
    "promoter_contact": "Promoter contact person",
    "promoter_address": "Promoter billing address",
    "promoter_vat": "Promoter VAT number",
    "event_name": "Event or festival name",
    "venue_name": "Venue name",
    "venue_address": "Venue address",
    "venue_city": "City",
    "venue_country": "Country",
    "venue_capacity": "Capacity",
    "show_date": "Show date",
    "load_in": "Load in time",
    "soundcheck": "Soundcheck time",
    "doors_time": "Doors time",
    "set_time": "Set time",
    "set_length": "Set length in minutes",
    "curfew": "Curfew",
    "deal_summary": "Plain English deal description",
    "fee": "Guarantee / fee",
    "currency": "Currency",
    "deposit_percent": "Deposit percentage",
    "deposit_amount": "Deposit amount",
    "balance_amount": "Balance amount",
    "hospitality_buyout": "Hospitality buyout",
    "ticket_price": "Ticket price",
    "tech_rider": "Artist technical rider",
    "hospitality_rider": "Artist hospitality rider",
    "notes": "Show production notes",
}


def _fmt_money(value) -> str:
    return f"{to_money(value):,.2f}"


def contract_context(show: Show, number: str) -> dict:
    agency = Agency.get()
    venue = show.venue
    promoter = show.promoter
    tbc = "TBC"
    return {
        "contract_number": number,
        "today": date.today().strftime("%d %B %Y"),
        "agency_name": agency.name,
        "agency_address": agency.address or "",
        "artist_name": show.artist.name,
        "promoter_company": promoter.company if promoter else tbc,
        "promoter_contact": (promoter.contact_name or promoter.company) if promoter else tbc,
        "promoter_address": " ".join((promoter.billing_address or "").split()) if promoter else tbc,
        "promoter_vat": (promoter.vat_number or "") if promoter else "",
        "event_name": show.event_name or (venue.name if venue else tbc),
        "venue_name": venue.name if venue else tbc,
        "venue_address": (venue.address or "") if venue else "",
        "venue_city": show.display_city or tbc,
        "venue_country": show.display_country or "",
        "venue_capacity": str(show.capacity or (venue.capacity if venue else "") or tbc),
        "show_date": show.date.strftime("%A %d %B %Y"),
        "load_in": show.load_in or tbc,
        "soundcheck": show.soundcheck or tbc,
        "doors_time": show.doors_time or tbc,
        "set_time": show.set_time or tbc,
        "set_length": str(show.set_length or tbc),
        "curfew": show.curfew or tbc,
        "deal_summary": show.deal_summary,
        "fee": _fmt_money(show.fee),
        "currency": show.currency,
        "deposit_percent": f"{show.deposit_percent or 0:g}",
        "deposit_amount": _fmt_money(show.deposit_amount),
        "balance_amount": _fmt_money(show.balance_amount),
        "hospitality_buyout": _fmt_money(show.hospitality_buyout),
        "ticket_price": _fmt_money(show.ticket_price),
        "tech_rider": show.artist.tech_rider or "",
        "hospitality_rider": show.artist.hospitality_rider or "",
        "notes": show.production_notes or "None.",
    }


def render_template_text(template: str, context: dict) -> str:
    """Fill ``{{placeholder}}`` tokens. Unknown tokens are left untouched so a
    typo is visible in the draft instead of silently disappearing."""

    def replace(match):
        key = match.group(1)
        return context.get(key, match.group(0))

    return PLACEHOLDER_RE.sub(replace, template)


def create_contract(show: Show) -> Contract:
    agency = Agency.get()
    number = agency.take_contract_number()
    body = render_template_text(agency.contract_template, contract_context(show, number))
    contract = Contract(show=show, number=number, body=body, status="draft")
    db.session.add(contract)
    return contract


# --------------------------------------------------------------------------
# Invoices
# --------------------------------------------------------------------------


def _show_label(show: Show) -> str:
    where = ", ".join(p for p in (show.event_name or (show.venue.name if show.venue else ""), show.display_city) if p)
    return f"{show.artist.name}, {where}, {show.date:%d %b %Y}" if where else f"{show.artist.name}, {show.date:%d %b %Y}"


def create_invoice_for_show(show: Show, kind: str) -> Invoice:
    """Build a draft invoice for a show.

    ``deposit``, ``balance`` and ``full`` bill the promoter; ``commission``
    bills the artist for the agency's share of the fee.
    """
    agency = Agency.get()
    label = _show_label(show)
    invoice = Invoice(
        show=show,
        kind=kind,
        status="draft",
        currency=show.currency,
        vat_rate=agency.default_vat_rate or 0,
    )
    db.session.add(invoice)

    if kind == "commission":
        artist = show.artist
        invoice.bill_to_name = artist.billing_name or artist.name
        invoice.bill_to_address = artist.billing_address or ""
        invoice.bill_to_vat = artist.vat_number or ""
        invoice.bill_to_email = artist.email or ""
        rate = f"{artist.commission_rate or 0:g}"
        lines = [(f"Agency commission {rate}% on {_fmt_money(show.fee)} {show.currency}: {label}", show.commission_amount)]
    else:
        promoter = show.promoter
        if promoter:
            invoice.bill_to_name = promoter.company
            invoice.bill_to_address = promoter.billing_address or ""
            invoice.bill_to_vat = promoter.vat_number or ""
            invoice.bill_to_email = promoter.email or ""
        if kind == "deposit":
            lines = [(f"Deposit {show.deposit_percent or 0:g}% of artist fee: {label}", show.deposit_amount)]
        elif kind == "balance":
            already = sum(
                (i.subtotal for i in show.invoices if i.kind == "deposit" and i.status != "cancelled"),
                Decimal("0.00"),
            )
            lines = [(f"Balance of artist fee: {label}", to_money(show.fee) - already)]
        else:
            lines = [(f"Artist fee: {label}", to_money(show.fee))]
        if kind in ("balance", "full") and show.hospitality_buyout:
            lines.append(("Hospitality buyout", to_money(show.hospitality_buyout)))

    for description, amount in lines:
        invoice.lines.append(InvoiceLine(description=description, quantity=1, unit_price=amount))
    return invoice


def issue_invoice(invoice: Invoice) -> None:
    """Give a draft its final number and dates. Numbers are only taken when an
    invoice is issued so deleted drafts never leave gaps in the sequence."""
    if invoice.status != "draft":
        return
    agency = Agency.get()
    invoice.number = agency.take_invoice_number()
    invoice.issue_date = date.today()
    if invoice.due_date is None:
        invoice.due_date = date.today() + timedelta(days=agency.payment_terms_days or 0)
    invoice.status = "sent"


def totals_by_currency(invoices) -> dict[str, Decimal]:
    totals = defaultdict(lambda: Decimal("0.00"))
    for invoice in invoices:
        totals[invoice.currency] += invoice.total
    return dict(sorted(totals.items()))


# --------------------------------------------------------------------------
# Itineraries
# --------------------------------------------------------------------------


@dataclass
class ItineraryDay:
    day: date
    shows: list = field(default_factory=list)
    travel: list = field(default_factory=list)
    hotels_checkin: list = field(default_factory=list)
    hotels_staying: list = field(default_factory=list)
    other: list = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.shows or self.travel or self.hotels_checkin or self.hotels_staying or self.other)

    @property
    def kind(self) -> str:
        if self.shows:
            return "Show day"
        if self.travel:
            return "Travel day"
        return "Day off"


def build_itinerary(artist_id: int, start: date, end: date, include_cancelled=False) -> list[ItineraryDay]:
    days = {start + timedelta(days=i): ItineraryDay(start + timedelta(days=i)) for i in range((end - start).days + 1)}

    shows = Show.query.filter(Show.artist_id == artist_id, Show.date >= start, Show.date <= end).order_by(Show.date)
    for show in shows:
        if show.status == "cancelled" and not include_cancelled:
            continue
        days[show.date].shows.append(show)

    window_start = datetime.combine(start, datetime.min.time())
    window_end = datetime.combine(end + timedelta(days=1), datetime.min.time())
    items = (
        LogisticsItem.query.filter(
            LogisticsItem.artist_id == artist_id,
            LogisticsItem.status != "cancelled",
            LogisticsItem.start_at < window_end,
        )
        .order_by(LogisticsItem.start_at)
        .all()
    )
    for item in items:
        item_day = item.start_at.date()
        if item.kind == "hotel":
            checkout = item.end_at.date() if item.end_at else item_day + timedelta(days=1)
            if checkout <= start:
                continue
            if item_day in days:
                days[item_day].hotels_checkin.append(item)
            # Nights after the first: the stay continues on these days.
            d = max(item_day + timedelta(days=1), start)
            while d < checkout and d in days:
                days[d].hotels_staying.append(item)
                d += timedelta(days=1)
        elif item.start_at >= window_start:
            target = days[item_day].travel if item.kind in ("flight", "train", "car", "ground") else days[item_day].other
            target.append(item)
    return [days[d] for d in sorted(days)]


# --------------------------------------------------------------------------
# Calendar export
# --------------------------------------------------------------------------


def _ics_escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_dt(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def itinerary_ics(itinerary, days: list[ItineraryDay], host: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//TourDesk//Itinerary//EN",
        f"X-WR-CALNAME:{_ics_escape(itinerary.title)}",
    ]

    def event(uid, summary, start_line, end_line, location="", description=""):
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}@{host}",
                f"DTSTAMP:{stamp}",
                start_line,
                end_line,
                f"SUMMARY:{_ics_escape(summary)}",
            ]
        )
        if location:
            lines.append(f"LOCATION:{_ics_escape(location)}")
        if description:
            lines.append(f"DESCRIPTION:{_ics_escape(description)}")
        lines.append("END:VEVENT")

    seen = set()
    for day in days:
        for show in day.shows:
            where = ", ".join(p for p in ((show.venue.name if show.venue else ""), show.display_city) if p)
            desc = "\n".join(
                f"{label}: {value}"
                for label, value in (
                    ("Load in", show.load_in),
                    ("Soundcheck", show.soundcheck),
                    ("Doors", show.doors_time),
                    ("Set", show.set_time),
                    ("Curfew", show.curfew),
                )
                if value
            )
            event(
                f"show-{show.id}",
                show.title,
                f"DTSTART;VALUE=DATE:{show.date:%Y%m%d}",
                f"DTEND;VALUE=DATE:{show.date + timedelta(days=1):%Y%m%d}",
                where,
                desc,
            )
        for item in day.travel + day.other + day.hotels_checkin:
            if item.id in seen:
                continue
            seen.add(item.id)
            end = item.end_at or (item.start_at + timedelta(hours=1))
            location = item.address or item.from_place
            desc = " · ".join(p for p in (item.provider, f"Ref {item.reference}" if item.reference else "") if p)
            event(f"logistics-{item.id}", item.label, f"DTSTART:{_ics_dt(item.start_at)}", f"DTEND:{_ics_dt(end)}", location, desc)

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
