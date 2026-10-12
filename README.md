# AgriTrial MVP (IFS140 Group 1)

Offline-first trial data capture for small farmers, with 95% confidence-interval
analytics and a DALRRD Act 36 dossier export.

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

## 1. Setup (once)

Needs Python 3.11+.

```bash
git clone https://github.com/<your-username>/AgriTrial-MVP-Group1.git
cd AgriTrial-MVP-Group1
python -m venv venv

# Windows:
venv\Scripts\activate
# Mac / Linux:
source venv/bin/activate

pip install -r requirements.txt
```

## 2. Run the demo (two terminals, both with the venv activated)

```bash
python seed_demo.py                 # resets and loads demo data (run before every video take)
uvicorn api_engine:app --reload     # terminal 1: API  (docs at http://127.0.0.1:8000/docs)
streamlit run app.py                # terminal 2: app  (opens in the browser)
```

With no Supabase keys set, the API uses a built-in **local cloud simulator**
(`cloud_mock.db`) so everything works straight away.

| Login | Password | Role |
|---|---|---|
| farmer102 | farmer102pw | Small Farmer (OID-102) |
| dalrrd01 | dalrrd01pw | DALRRD Regulatory Official |
| uwc01 | uwc01pw | UWC Researcher (dashboard only) |

## 3. Use the real Supabase

1. In Supabase: **SQL Editor → New query**, paste `sql/schema_supabase.sql`, **Run**.
2. Copy `.env.example` to `.env` and fill in `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`
   (Project Settings → API → the **service_role** key). Never commit `.env`.
3. Restart the API, then run `python seed_demo.py`. The API now reports
   `"backend": "supabase"` at `/health`; check the rows in the Supabase Table Editor.

Free-tier projects pause after 7 days of inactivity: write to it regularly. If it is
paused, `/health` reports `cloud: false` and the phone simply keeps records `PENDING`.

## 4. Tests

```bash
python -m pytest -v
```

Covers: the 11 mandatory fields and every Section 6b range (unit), the CI maths and
yield (unit), local SQLite behaviour (unit), and the full offline → sync → cloud →
CI chart → dossier path through the real sync worker and API (integration), plus a
Streamlit smoke test. See `TESTING.md` for the procedures and results.

## 5. Demo script (the path to show on video)

1. Log in as `farmer102` → **Site & Plot** → TGID-1 → *Use this plot*.
2. **Capture Record**: Height `600` → blocked with a clear message.
3. Turn on **Offline mode** (sidebar). Enter height `45`, leaves `15`, nitrate `141` → saved `PENDING` ("1 Records Queued").
4. Turn Offline mode off → **My Records & Sync → Sync now** → `SYNCED` with `EP-T###`.
5. Log out, log in as `dalrrd01` → **Dashboard**: TGID-1, week TW-6 → CI chart (it showed
   "More records needed" before the sync; week TW-5 always has the chart).
6. **Generate Act 36 Dossier** → download the ZIP (anonymised CSV + Markdown protocol).

## 6. Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit front end: sign-up, login, site/plot, capture form, records, dashboard |
| `validation.py` | Section 6b rules + 11 mandatory fields (used by phone AND API) |
| `database.py` | Local SQLite: records, setup data, offline login, settings |
| `sync_worker.py` | Connectivity check, PENDING queue, retries, "Server Wins" setup sync |
| `api_engine.py` | FastAPI endpoints (see below) |
| `cloud_store.py` | Supabase store + local simulator behind one interface |
| `analytics.py` | Mean ± 95% CI (Student's t), plot yield |
| `dossier.py` | Anonymised CSV + protocol Markdown → ZIP |
| `seed_demo.py` | Resets and loads demo data |
| `sql/` | `schema_sqlite.sql` (phone), `schema_supabase.sql` (cloud) |
| `tests/` | pytest suite |

## 7. API

| Endpoint | Who | What |
|---|---|---|
| `GET /health` | anyone | API + cloud status (phone uses this to decide "online") |
| `POST /auth/signup`, `POST /auth/login` | anyone | Farmer sign-up, login |
| `GET /api/v1/lookups` | anyone | Dropdown lists |
| `GET/POST /api/v1/sites`, `/api/v1/plots` | all / farmer | Setup data ("Server Wins") |
| `POST /api/v1/trials` | farmer | Sync upsert: 200 SUCCESS, 422 REJECTED |
| `GET /api/v1/trials` | stakeholders | Filter by site, crop, group, week, visit type |
| `GET /api/v1/analytics/nitrate-ci` | stakeholders | Mean ± 95% CI, only when n ≥ 5 per group |
| `GET /api/v1/analytics/plot-yield` | stakeholders | Yield g/m² |
| `GET /api/v1/dossier` | DALRRD | Act 36 dossier ZIP |

Roles are sent in an `X-User-Role` header (prototype). Production would use signed tokens.

## 8. Known limitations (MVP scope)

- The "phone" app is a responsive web app (Streamlit), not a native Android/iOS app.
- On-device database encryption is designed (Milestone 1, Section 9) but **not built**.
- Language choice is saved in the profile; translated screens are not built yet.
- Editing a flagged record, the weather alert, voice notes and the chatbot are not built (post-MVP).
- Supabase mode needs a real project and keys; the default demo uses the local simulator.
- GPS is not collected, so there is nothing to blur or strip.
