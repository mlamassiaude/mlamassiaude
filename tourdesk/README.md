# TourDesk

A lightweight booking agency tool, in the spirit of ABOSS but much smaller. It covers the core loop of an agency: keep a roster, book shows with their deals, organise travel and hotels, send itineraries to the travel party, and issue contracts and invoices.

Built with Python, Flask and SQLite. No build step, no JavaScript framework.

## What it does

**Roster**
Artists with default fee, currency, agency commission, responsible agent, riders, billing details and a travel party (band, tour manager, crew).

**Shows**
Every show has an artist, date, venue, promoter and a status (option, pending, confirmed, played, cancelled). Deals support flat fee, guarantee vs %, guarantee plus bonus and door split, with deposit %, hospitality buyout and ticket price. The schedule holds load in, soundcheck, doors, set time and curfew. A month calendar shows the whole roster at a glance.

**Logistics**
Flights, trains, van/car, ground transfers, hotels and anything else, with booking refs, travellers, costs and a "to book / booked" status. Items can be linked to a show or float on their own (travel days, days off).

**Itineraries**
Pick an artist and a date range and TourDesk builds a day by day plan from shows, travel and hotels. Print it to PDF, or switch on a secret share link that the travel party can open on their phone without an account. The shared page never shows fees or internal notes, and comes with an `.ics` calendar file. Each show also has a one page day sheet.

**Contracts**
Generated from an editable template in Settings using placeholders such as `{{artist_name}}`, `{{deal_summary}}` or `{{deposit_amount}}`. Review and edit the text, mark it sent, then signed. Signing a contract moves an option or pending show to confirmed.

**Invoices**
One click from a show: deposit, balance or full fee to the promoter, or commission to the artist. Drafts can be edited freely. Issuing gives the invoice its final sequential number (so deleted drafts never leave gaps) and locks it. Bill-to details are copied onto the invoice, VAT is applied, overdue invoices are flagged, and the dashboard shows outstanding receivables per currency.

**Dashboard**
Upcoming shows, open options, contracts waiting for a signature, overdue invoices, and gross fees and commission per artist for the year.

**Team**
Multiple agents can log in. Admins manage agency settings and the team.

## Run it locally

Needs Python 3.9 or newer.

```bash
cd tourdesk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

flask --app wsgi seed-demo   # optional: demo agency, log in as demo@tourdesk.local / demo1234
flask --app wsgi run
```

Open http://127.0.0.1:5000. Without demo data, the first visit asks you to create your agency and admin account.

Data lives in `instance/tourdesk.db`. Set `TOURDESK_DATABASE_URL` to use another database (any SQLAlchemy URL, e.g. Postgres) and `TOURDESK_SECRET_KEY` in production.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Project layout

```
tourdesk/
  models.py      database tables (money stored as integer cents)
  forms.py       field definitions and validation for every form
  services.py    contract rendering, invoice generation, itinerary builder, .ics export
  views/         Flask blueprints: auth, dashboard/settings, roster, shows, documents, itinerary
  templates/     Jinja templates
  static/        stylesheet (includes print styles for PDFs)
  demo.py        demo data
tests/           end to end tests through the Flask test client
```

## Ideas for next steps

- Email contracts and invoices straight from the app, and e-signature
- Settlement sheet after the show (ticket count, costs, door deal calculation)
- Artist portal with a read only login
- Holds and avails per date across the roster
- File uploads for riders, stage plots and boarding passes
- Expenses per tour and profit per show
