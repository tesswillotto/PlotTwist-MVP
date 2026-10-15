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
| Unit | `tests/test_analytics_extra.py` | Edge cases: fewer than 2 values refused; blank (`""`) and NaN readings ignored; empty groups; 4 vs 5 boundary; identical values give a zero-width interval; yield ignores blank weights and zero area |
| Unit | `tests/test_dossier.py` | Personal fields (names, contacts, notes, GPS) never reach the export; OID kept; missing protocol text shows a placeholder; empty export gives a header-only CSV |

## Result (automated, last run: 15 October 2026)

101 passed, 16 warnings in 15.00 s (Windows, Python 3.14.7).
The 16 warnings are Starlette/httpx deprecation notices from the libraries, not from our code

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

Not run manually (covered by the automated tests): syncing the same record twice, height 0 and -5, and Supabase mode.

## Bug log

| # | Found | Bug | Fix / status |
|---|---|---|---|
| 1 | Test run | Two of our own tests had wrong expectations (ZIP file ordering, 12 Oct is TW-6 not TW-7) | Corrected the tests; code was right |
| 2 | Review | Original SQL: a comment swallowed the `dissolved_oxygen` column | Rewritten schema |
| 3 | Review | Original schema used one `record_id` for both the local and the cloud ID | Split into `local_id` and `cloud_record_id` |
| 4 | Manual test, 13 Oct | Demo script depends on today's date. The trial week is calculated from the current date, so a record entered after 12 Oct lands in TW-7, not TW-6, and the TW-6 chart never appears (README step 5 and the `seed_demo.py` comment no longer work) | Open. Workaround: in the video show TW-6 for "More records needed" and TW-5 for the chart. Alternative: seed TW-7 data in `seed_demo.py` |
| 5 | Manual test, 13 Oct | After pressing Sync now, the message read "0 synced, 0 flagged, 0 pending" although the record had just synced (probably it synced automatically when Offline mode was switched off, so the button had nothing left to send). Wording is confusing; data is correct | Open, low priority; cause not investigated |
| 6 | Automated tests, 15 Oct | `mean_ci` gave a divide-by-zero or NaN with fewer than 2 values, and `compare_nitrate` crashed on a blank `""` reading | Fixed in `analytics.py` (guard in `mean_ci`, stricter `_clean`); 3 tests in `test_analytics_extra.py` failed before the fix and pass after |

Note: the test record `EP-T130` entered during the manual test is included in a dossier exported
afterwards. Run `python seed_demo.py` again before any final dossier export or video take.

## Not yet tested

- Supabase mode against a real project (needs your project keys).
- Real phone browsers and a real network drop (the demo uses the Offline mode switch).
