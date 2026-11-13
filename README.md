# PlotTwist MVP (IFS140 Group 1)

Offline-first trial data capture for small farmers, with 95% confidence-interval
analytics and a DALRRD Act 36 dossier export. (The project was first called the AgriTrial MVP.)

**How it works:** the farmer's app saves every record on the phone first (SQLite,
status `PENDING`). When online, the sync worker sends records through the FastAPI
engine, which validates them and writes them to Supabase. Records come back
`SYNCED` (with a cloud ID like `EP-T101`) or `FLAGGED_FOR_REVIEW` (with a reason).
Stakeholders open a dashboard that shows nitrate mean ± 95% CI (Student's t) for
control vs a treatment variant, but only when both groups have at least 5 readings.

```
Streamlit app ──► SQLite (phone) ──► sync_worker.py ──► FastAPI (api_engine.py) ──► Supabase
 (app.py)         PENDING queue        oldest first        validates, assigns IDs     (or local simulator)
                                                                  │
                                       Dashboard ◄── analytics.py ┘──► dossier.py (ZIP)
```

**About the demo data:** `seed_demo.py` loads **synthetic** records and placeholder protocol text so
the dashboard and reports can be shown. They are not real trial results, and the dashboard and the PDF
report say so. The demo logins below are for the demo only.

## 1. Setup (once)

Developed and tested on Python 3.14.7 (Windows). Package versions are pinned in `requirements.txt`.

```bash
git clone https://github.com/tesswillotto/PlotTwist-MVP.git
cd PlotTwist-MVP
python -m venv venv

# Windows:
venv\Scripts\activate
# Mac / Linux:
source venv/bin/activate

pip install -r requirements.txt
```

## 2. Run the demo (two terminals, both with the venv activated)

First load the demo data (do this once, and again before every demo or video take):

```bash
python seed_demo.py
```

It resets the cloud store and **deletes the local phone database** (add `--keep-local` to keep it),
then loads about 214 demo records. The site start date is set 35 days before the day you run it,
so the demo works on the day you seed (and for the 6 days after). Seed again if the demo is older.

Then start the API and the app, each in its own terminal:

```bash
python -m uvicorn api_engine:app --reload    # terminal 1: API  (docs at http://127.0.0.1:8000/docs)
python -m streamlit run app.py               # terminal 2: app  (opens in the browser)
```

With no Supabase keys set, the API uses a built-in **local cloud simulator**
(`cloud_mock.db`), so everything works straight away.

| Login | Password | Role |
|---|---|---|
| sam | sampw | Small Farmer, shown as "Sam" (OID-102) |
| dalrrd01 | dalrrd01pw | DALRRD Regulatory Official |
| uwc01 | uwc01pw | UWC Researcher (dashboard only) |

## 3. Use the real Supabase (optional)

1. Create a project at supabase.com. In the dashboard open **SQL Editor → New query**, paste
   `sql/schema_supabase.sql` and **Run**. It creates five tables and turns on row-level security,
   so only the server-side key can read or write them.
2. Copy `.env.example` to `.env` (`copy .env.example .env` on Windows, `cp .env.example .env` on Mac or Linux)
   and fill in two lines. `.env` is git-ignored: never commit it.
   - `SUPABASE_URL`: `https://<your-project-ref>.supabase.co` (nothing after `.co`). The project
     reference is the code in the dashboard address bar after `/project/`.
   - `SUPABASE_SERVICE_KEY`: the **secret key** (starts with `sb_secret_`). In the dashboard open
     **Project Settings → API Keys → Publishable and secret API keys** and create one with
     **New secret key**. Older projects may still show the legacy `service_role` key; it works for now,
     but Supabase is retiring it. Never use the publishable key, and never put the secret key in the app.
3. Check the connection:
   `python -c "import cloud_store; s = cloud_store.get_store(); print(s.name, s.ping())"`
   should print `supabase True`.
4. Run `python seed_demo.py --yes`. **Warning: this deletes every row in the connected Supabase
   project before loading the demo data**, so the script refuses to run without `--yes`.
5. Start the API again. `http://127.0.0.1:8000/health` now reports `"backend": "supabase"`.
   Check the rows in the Supabase Table Editor.

Free-tier projects pause after 7 days of inactivity: use the project regularly. If it is
paused, `/health` reports `cloud: false` and the phone simply keeps records `PENDING`.
The automated tests never touch Supabase, even when `.env` holds real keys.

## 4. Tests

```bash
python -m pytest -v
```

Covers: the 11 mandatory fields and every Section 6b range (unit), the CI maths and
yield (unit), local SQLite behaviour (unit), the anonymised export (unit), the PDF report and demo
data (unit and integration), API input checks (integration), and the full offline → sync → cloud →
CI chart → dossier path through the real sync worker and API (integration), plus a
Streamlit smoke test. 119 tests in total. See `TESTING.md` for the procedures, the latest results,
the manual tests (including one against a real Supabase project) and the bug log.

## 5. Demo script (the path to show on video)

1. Log in as `sam` → **Site & Plot** → TGID-1 → *Use this plot*.
2. **Capture Record**: Height `600` → blocked with a clear message.
3. Turn on **Offline mode** (sidebar). Enter height `45`, leaves `15`, nitrate `141` → saved `PENDING` ("1 Records Queued").
4. Turn Offline mode off → **My Records & Sync → Sync now** → `SYNCED` with `EP-T###`. (The app may
   already have synced it in the background; the message then says "Nothing to sync".)
5. Log out, log in as `dalrrd01` → **Dashboard**, week TW-6: the chart compares the control
   with every treatment group. TGID-1 showed "More records needed" before your sync (it had 4
   readings) and now joins the chart. Other weeks (TW-1 to TW-5) show every group. A blue notice
   reminds the viewer that the records are synthetic demo data.
6. **Generate Act 36 PDF report** → download the PDF: summary, CI chart, week-by-week means,
   growth, yield, protocols and method notes. (The anonymised CSV + protocol ZIP is under
   "Raw data package".)

## 6. Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit front end: sign-up, login, site/plot, capture form, records, dashboard |
| `validation.py` | Section 6b rules + 11 mandatory fields (used by phone AND API) |
| `database.py` | Local SQLite: records, setup data, offline login, settings |
| `sync_worker.py` | Connectivity check, PENDING queue, retries, "Server Wins" setup sync |
| `api_engine.py` | FastAPI endpoints (see below) |
| `api_client.py` | Small wrapper the app uses to call the API |
| `cloud_store.py` | Supabase store + local simulator behind one interface |
| `analytics.py` | Mean ± 95% CI (Student's t), plot yield |
| `dossier.py` | Anonymised CSV + protocol Markdown → ZIP |
| `report_pdf.py` | The Act 36 PDF report: every treatment group compared with the control |
| `charts.py` | Dashboard charts (Plotly): all-groups CI chart and yield chart |
| `security.py` | Salted password hashing (PBKDF2-SHA256) |
| `config.py` | Paths, roles, dropdown lists and settings read from `.env` |
| `seed_demo.py` | Resets and loads the synthetic demo data |
| `sql/` | `schema_sqlite.sql` (phone), `schema_supabase.sql` (cloud) |
| `tests/` | pytest suite |
| `docs/` | Test evidence (screenshots) |
| `TESTING.md` | Test procedures, results, manual tests and bug log |
| `.env.example` | Template for the local `.env` (never commit `.env`) |

## 7. API

| Endpoint | Who | What |
|---|---|---|
| `GET /health` | anyone | API + cloud status (phone uses this to decide "online") |
| `POST /auth/signup`, `POST /auth/login` | anyone | Farmer sign-up, login |
| `GET /api/v1/lookups` | anyone | Dropdown lists |
| `GET/POST /api/v1/sites`, `/api/v1/plots` | all / farmer | Setup data ("Server Wins"). The site, crop and group must come from the dropdown lists, and the server builds the plot ID |
| `POST /api/v1/trials` | farmer | Sync upsert: 200 SUCCESS, 422 REJECTED |
| `GET /api/v1/trials` | stakeholders | Filter by site, crop, group, week, visit type. Free-text notes are left out |
| `GET /api/v1/analytics/nitrate-ci` | stakeholders | Mean ± 95% CI, only when n ≥ 5 per group |
| `GET /api/v1/analytics/plot-yield` | stakeholders | Yield g/m² ("Plot not set up" if the plot does not exist yet) |
| `GET /api/v1/dossier` | DALRRD | Data package ZIP (anonymised CSV + protocols) |
| `GET /api/v1/dossier-pdf` | DALRRD | Act 36 PDF report (all groups vs control) |

Roles are sent in an `X-User-Role` header (prototype, not authenticated). Production would use signed tokens.

## 8. Known limitations (MVP scope)

- The "phone" app is a responsive web app (Streamlit), not a native Android/iOS app. Capture, validation
  and local saving work without a connection, and the prototype demonstrates this with the Offline mode
  switch; testing on real phones with a real network drop is still to be done. A production version would
  be packaged as an installable app (PWA or native) so the form loads without signal.
- On-device database encryption is designed (Milestone 1, Section 9) but **not built**.
- The language choice is saved on the device; translated screens (Afrikaans, isiXhosa) are not built yet.
- A flagged record shows its rejection reason in My Records, but there is no on-screen edit page yet
  (post-MVP). The database layer already resets an edited record to `PENDING`.
- The weather alert, voice notes and the chatbot are not built (post-MVP).
- The role header is not authenticated, and login has no limit on repeated attempts.
- Record timestamps are saved as local time without a timezone, and the cloud reads them as UTC
  (two hours off for South Africa).
- Green and yellow bands are a simple visual rule (non-overlapping 95% intervals), not a significance test.
- The Observer ID is kept in exports for audit traceability, so exports are PII-stripped (pseudonymised),
  not fully anonymous. GPS is not collected, so there is nothing to blur or strip.
- Supabase returns at most 1,000 rows per request by default; the dashboard queries by site and crop.
- The demo data, and the protocol text loaded with it, are placeholders until the Eduponics research team
  confirms them. Entry speed (under 30 seconds) and farmer usability have not been tested yet.

## 9. Troubleshooting

- **`uvicorn` or `streamlit` "cannot find the file specified":** the virtual environment was created in a
  folder with a different name. Start them as shown above (`python -m uvicorn ...`, `python -m streamlit ...`),
  or delete `venv` and create it again (Section 1).
- **`/health` says `local-simulator` although you set Supabase keys:** `.env` is not being read. It must be
  named exactly `.env`, sit in the project folder, and have both lines filled in with no quotes or spaces.
- **The dashboard is empty:** run `python seed_demo.py` (and restart the API).
