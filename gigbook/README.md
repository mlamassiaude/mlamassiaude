# Gigbook

A light, single-file booking desk for music agents, inspired by ABOSS. It covers the day-to-day loop of a small agency: holding dates, confirming shows, sending day sheets and chasing invoices.

No build step, no backend, no account. Open `index.html` in a browser and it runs. Everything is saved in the browser's localStorage, and the Data page lets you back it up or restore it as JSON.

## What it does

| Area | Features |
| --- | --- |
| Dashboard | Confirmed shows in the next 90 days, open options, gross booked this year, outstanding invoices, a "needs attention" list (expiring options, overdue invoices, unsigned contracts, missing day sheets) and booked fees per month |
| Calendar | Month grid, colour per artist, status per chip (option, pending, confirmed, cancelled). Click a day to add a show on it |
| Shows | Filterable, searchable table with fee, deal type, contract state and commission |
| Show detail | Status flow, deal terms, commission and artist net, promoter contact, double booking warning, running order with templates, travel and hotel, copyable day sheet, deposit and balance invoices |
| Artists | Roster with asking fee, commission rate, next show, holds and gross for the year |
| Contacts | Promoters, venues, festivals, tour managers |
| Finance | Received, awaiting, overdue and draft totals, settlement per artist (gross, commission, artist net, received), invoice list with sent and paid toggles |
| Data | JSON backup and restore, CSV export of shows, reload demo data, start empty |

The global artist filter in the top bar narrows the dashboard, calendar, shows and finance views to one act.

## Notes

* Totals across currencies are converted to EUR with a fixed rate table (`FX` at the top of the script). They are estimates for an overview, not accounting figures.
* The demo roster, venues and contacts are fictional. Dates are generated relative to today so the demo always looks current.
* Light and dark themes follow the system setting, with a manual switch in the sidebar.

## Run it

```bash
open gigbook/index.html          # macOS
xdg-open gigbook/index.html      # Linux
```

Or serve the folder with any static server, for example `python3 -m http.server` and visit `http://localhost:8000/gigbook/`.
