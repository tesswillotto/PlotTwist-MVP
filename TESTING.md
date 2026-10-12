# Testing documentation

## How to run

```bash
python -m pytest -v
```

Tests use temporary databases and a simulated cloud. They never touch real data or Supabase.

## What is tested

| Level | File | What it proves |
|---|---|---|
| Unit | `tests/test_validation.py` | All 11 mandatory fields required; every Section 6b range and boundary; format rules; dry ≤ fresh weight (null-safe) |
| Unit | `tests/test_analytics.py` | CI matches a hand calculation (t = 2.776 at df 4); n < 5 blocks the chart; blanks don't count; green/yellow band; yield = fresh weight ÷ area |
| Unit | `tests/test_database.py` | Records save as PENDING; DB CHECK constraints block bad data; edit resets FLAGGED → PENDING; trial week maths; offline login uses a salted hash |
| Integration | `tests/test_api_and_sync.py` | Offline record stays PENDING then syncs and gets `EP-T101`; retries never duplicate; IDs sequential; cloud rejection → FLAGGED with reason; cloud down keeps PENDING; "Server Wins" on site start date; sign-up/login; role checks (403); CI endpoint at n = 4 then n = 5; dossier ZIP contents and no personal details |
| System | `tests/test_app_smoke.py` | The Streamlit app starts and handles an unknown login without crashing |

## Result (last run)

86 passed.

## Manual system test (done against the running API and app)

Seed → farmer logs in online → height 600 blocked → Offline mode on, valid record saved
as PENDING → Offline mode off, Sync now → SYNCED → DALRRD dashboard shows the CI chart
(week TW-6 went from "More records needed" to a chart after the sync) → dossier ZIP
downloaded with CSV + protocol.

## Bug log

| # | Found | Bug | Fix |
|---|---|---|---|
| 1 | Test run | Two of our own tests had wrong expectations (ZIP file ordering, 12 Oct is TW-6 not TW-7) | Corrected the tests; code was right |
| 2 | Review | Original SQL: a comment swallowed the `dissolved_oxygen` column | Rewritten schema |
| 3 | Review | Original schema used one `record_id` for both the local and the cloud ID | Split into `local_id` and `cloud_record_id` |

Add new bugs here as the team finds them (what, who, how fixed).

## Not yet tested

- Supabase mode against a real project (needs your project keys).
- Real phone browsers and a real network drop (the demo uses the Offline mode switch).
