# Testing documentation

## How to run

```bash
python -m pytest -v
```

Tests use temporary databases and a simulated cloud. They never touch real data or Supabase, even when a local `.env` file holds real Supabase keys (`tests/conftest.py` clears them after the imports). The package versions used for the results below are pinned in `requirements.txt`.

## What is tested

| Level | File | What it proves |
|---|---|---|
| Unit | `tests/test_validation.py` | All 11 mandatory fields required; every Section 6b range and boundary; format rules; dry ≤ fresh weight (null-safe) |
| Unit | `tests/test_analytics.py` | CI matches a hand calculation (t = 2.776 at df 4); n < 5 blocks the chart; blanks don't count; green/yellow band; yield = fresh weight ÷ area |
| Unit | `tests/test_database.py` | Records save as PENDING; DB CHECK constraints block bad data; edit resets FLAGGED → PENDING; trial week maths; offline login uses a salted hash |
| Integration | `tests/test_api_and_sync.py` | Offline record stays PENDING then syncs and gets `EP-T101`; retries never duplicate; IDs sequential; cloud rejection → FLAGGED with reason; cloud down keeps PENDING; "Server Wins" on site start date; sign-up/login; role checks (403); CI endpoint at n = 4 then n = 5; dossier ZIP contents and no personal details |
| System | `tests/test_app_smoke.py` | The Streamlit app starts and handles an unknown login without crashing |
| Unit | `tests/test_analytics_extra.py` | Edge cases: fewer than 2 values refused; blank (`""`) and NaN readings ignored; empty groups; 4 vs 5 boundary; identical values give a zero-width interval; yield ignores blank weights and zero area |
| Unit | `tests/test_dossier.py` | Personal fields (names, contacts, notes, GPS) never reach the export; OID kept; missing protocol text shows a placeholder; empty export gives a header-only CSV |
| Unit + Integration | `tests/test_report_and_seed.py` | Every treatment group is compared with the control (higher, lower, no clear difference, insufficient data); the Act 36 PDF report is valid, contains no personal data and does not crash with no data or too little control data; demo seed data loads enough records and every seeded record passes validation |
| Integration | `tests/test_api_input_checks.py` | An unknown site, treatment group or crop is rejected (400); the server builds the plot ID itself; the report endpoints reject an unknown crop; free-text notes are hidden from the trials endpoint; the yield of a plot that is not set up is not an error |

## Result (automated, final run)

**13 November 2026, 14:48. Code commit `311ad1b`. 119 passed, 16 warnings in 28.66 s** (Windows, Python 3.14.7).
Command: `python -m pytest -q --disable-warnings`. Screenshot: `docs/test_run_2026-11-13.png`.
The 16 warnings are Starlette/httpx deprecation notices from the libraries, not from our code.

| Date | Tests | Result | What changed |
|---|---|---|---|
| 15 October 2026 | 101 | Passed | First automated run. The edge-case tests exposed bug 6 |
| 5 November 2026 | 112 | Passed (34.97 s) | Report and code aligned; Act 36 PDF report added |
| 13 November 2026 (after the code review) | 112 | Passed | API input checks, seed guard, sync message, demo-data labels |
| 13 November 2026, 14:48 (final) | 119 | Passed (28.66 s) | 7 new tests in `test_api_input_checks.py`; tests hardened against real Supabase keys |

## Manual system test (13 October 2026)

Tester: Tesswill. Environment: Windows, Python 3.14.7, Firefox, local cloud simulator
(not real Supabase). Data reset with `python seed_demo.py` before the run.

| # | Test | Expected | Result |
|---|---|---|---|
| 1 | Log in as `farmer102` | Login works, farmer menu shown | Pass |
| 2 | Select TGID-1 on Site & Plot | Plot accepted | Pass |
| 3 | Height 600, leaf count empty, submit | Blocked; `plant_height_cm` and `leaf_count` named | Pass |
| 4 | Dry weight 50 with fresh weight 20 | Blocked: "Dry weight cannot be more than fresh weight" | Pass |
| 5 | Offline mode on | Banner shows Offline | Pass |
| 6 | Save valid record offline (height 45, leaves 15, nitrate 141) | Saved locally as PENDING, "1 Records Queued" | Pass |
| 7 | Offline mode off | "Online (1 record(s) waiting to sync)", record has no cloud ID | Pass |
| 8 | Sync | Record gets cloud ID `EP-T130`, banner "Online (Synced)" | Pass |
| 9 | Dashboard TW-5 as `dalrrd01` | CI chart; control n=5 mean 108.4 (105.0–111.8), TGID-1 n=5 mean 135 (129.1–140.9) | Pass (matches hand calculation) |
| 10 | Dashboard TW-6 and TW-7 | "More records needed" (control 6 / variant 4; control 0 / variant 1) | Pass |
| 11 | Yield | Control 420 g/m², TGID-1 510 g/m² (hand check: 4200 ÷ 10, 5100 ÷ 10) | Pass |
| 12 | Generate Act 36 Dossier, download ZIP | ZIP with CSV and protocol Markdown | Pass |
| 13 | Inspect `trial_observation_data.csv` | 27 rows; no names, emails, contacts or GPS; observer shown as OID only; nitrate column `nitrate_mg_l` | Pass |
| 14 | Inspect protocol Markdown | Control and variant sections with crop, site, plot size, monitoring | Pass |
| 15 | Log in as `uwc01` | Dashboard only; no dossier button | Pass |
| 16 | Wrong password for `farmer102` | "Wrong username or password." | Pass |

## Manual system test against real Supabase (13 November 2026)

Tester: Tesswill. Environment: Windows, Python 3.14.7, Firefox, a Supabase free-tier project with the schema in `sql/schema_supabase.sql` (row-level security on), the server-side secret key in a local `.env` (never committed).

| # | Test | Expected | Result |
|---|---|---|---|
| 1 | `python seed_demo.py --yes` | "Seeded 214 trial records into the 'supabase' cloud store"; rows visible in the Table Editor | Pass |
| 2 | Start the API and open `/health` | `{"api":"ok","cloud":true,"backend":"supabase"}` | Pass |
| 3 | Dashboard as `dalrrd01`, week TW-5 | Chart, table and yield from Supabase; control 108.4 (105.0–111.8), TGID-1 135 (129.1–140.9); yields 420, 510, 470, 440, 540, 425; "Demo data" notice shown | Pass |
| 4 | Generate Act 36 PDF report | PDF downloads | Pass |
| 5 | Log in as `sam`, height 600 | Blocked | Pass |
| 6 | Save a valid record (height 45, leaves 15, nitrate 141) and sync | SYNCED with cloud ID `EP-T315`; Sync now says "Nothing to sync: every record is already synced." | Pass |
| 7 | Supabase Table Editor, `trial_measurements` | 215 records; the new row has the same ID | Pass |
| 8 | Run the automated tests with the real keys still in `.env` | 119 passed; Supabase still shows 215 records | Pass |

Not run manually (covered by the automated tests): syncing the same record twice, and height 0 and -5.

## Bug log

| # | Found | Bug | Fix / status |
|---|---|---|---|
| 1 | Test run | Two of our own tests had wrong expectations (ZIP file ordering, 12 Oct is TW-6 not TW-7) | Corrected the tests; code was right |
| 2 | Review | Original SQL: a comment swallowed the `dissolved_oxygen` column | Rewritten schema |
| 3 | Review | Original schema used one `record_id` for both the local and the cloud ID | Split into `local_id` and `cloud_record_id` |
| 4 | Manual test, 13 Oct | Demo script depends on today's date. The trial week is calculated from the current date, so a record entered after 12 Oct lands in TW-7, not TW-6, and the TW-6 chart never appears | Fixed. `seed_demo.py` now sets the site start date 35 days before the run date, so the demo works on the day it is run. Seed and demo flow repeated on 13 November 2026 |
| 5 | Manual test, 13 Oct | After pressing Sync now, the message read "0 synced, 0 flagged, 0 pending" although the record had just synced. Cause: the background sync (every 15 s) or the automatic sync when Offline mode is switched off had already sent the record, so the button had nothing left to send. Data was correct; the wording was confusing | Fixed in `sync_worker.py`: the message is now "Nothing to sync: every record is already synced." Confirmed in the app on 13 November 2026 |
| 6 | Automated tests, 15 Oct | `mean_ci` gave a divide-by-zero or NaN with fewer than 2 values, and `compare_nitrate` crashed on a blank `""` reading | Fixed in `analytics.py` (guard in `mean_ci`, stricter `_clean`); 3 tests in `test_analytics_extra.py` failed before the fix and pass after |
| 7 | Code review, 13 Nov | `seed_demo.py` could delete every row of a connected Supabase project without asking | Fixed: with Supabase keys set, the script refuses to run unless `--yes` is given |
| 8 | Code review, 13 Nov | The API accepted unknown site, crop and treatment-group values, and let the client choose the plot ID (sites, plots and report endpoints) | Fixed in `api_engine.py`: values are checked against the dropdown lists and the server builds the plot ID. 7 new tests in `test_api_input_checks.py` |
| 9 | Code review, 13 Nov | `GET /api/v1/trials` returned the free-text `notes` field, which can hold personal details | Fixed: `notes` is removed from the response; test added |
| 10 | Code review, 13 Nov | A cloud error message was returned to the client in full, which could expose internal details | Fixed: the API returns a generic "Cloud unavailable" message and the record stays PENDING |
| 11 | Code review, 13 Nov | A first version of the unknown-plot fix returned HTTP 404 for the yield of a plot that is not set up. The dashboard asks for all six groups, so it would have failed to load | Fixed before release: `plot-yield` now returns "Plot not set up" with no yield; test added |
| 12 | Code review, 13 Nov | The tests could pick up real Supabase keys from a local `.env`, because `config.py` loads it | Fixed in `tests/conftest.py`: the keys are cleared after the imports. Verified on 13 November 2026 (Supabase still at 215 records after a test run) |
| 13 | Code review, 13 Nov | Synthetic demo records could be mistaken for real trial results in the PDF report and dashboard | Fixed: both show "Demo data / DEMONSTRATION DATA" when the records come from the seed script |
| 14 | Code review, 13 Nov | The sign-up help text said the language choice is saved to the profile, but it is saved on the device | Fixed: help text corrected in `app.py` |
| 15 | Code review, 13 Nov | `.env.example` contained a real project URL and no line for the server-side key | Fixed: both Supabase lines are empty, with instructions for the URL format and the key |

## Known limitations found in review (not fixed)

- Record timestamps are saved as local time without a timezone, and the cloud reads them as UTC. For a South African phone, `created_timestamp` in Supabase is two hours behind (seen on 13 November 2026: 14:37 local, `received_at` 12:38 UTC).
- A flagged record shows its rejection reason in My Records, but there is no on-screen edit page yet (post-MVP). The database layer already resets an edited record to PENDING.
- The user role is read from a request header and is not authenticated (the 403 tests prove the role logic, not the identity). Production would use signed tokens.
- Login has no limit on repeated attempts.
- Supabase returns at most 1,000 rows per request by default. The dashboard queries by site and crop, which stay well below that.
- Green and yellow bands are a simple visual rule (non-overlapping 95% intervals), not a significance test.
- If the control group has 5 or more readings but no treatment group does, the PDF report says the control has too few readings (low impact).

Note: the test record `EP-T130` entered during the October manual test, and `EP-T315` from the November test, are included in a dossier exported afterwards. Run `python seed_demo.py` again before any final dossier export or video take (add `--yes` when Supabase keys are set).

## Not yet tested

- Real phone browsers and a real network drop (the demo uses the Offline mode switch).
- Entry speed (under 30 seconds per record) and a usability test with farmers.
- The Supabase 7-day inactivity pause (free tier). The code keeps records PENDING when the cloud is unreachable, which the automated test `test_cloud_down_keeps_records_pending` simulates.
