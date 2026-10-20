"""AgriTrial FastAPI engine.

Run:  uvicorn api_engine:app --reload
Docs: http://127.0.0.1:8000/docs   (interactive, good for the demo video)

Role-based access (prototype): the app sends the logged-in user's role in the
X-User-Role header. In production this would be a signed token (Supabase Auth).
"""
from datetime import date

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse, Response

import analytics
import config
from cloud_store import get_store
from dossier import build_dossier
from security import hash_password, verify_password
from validation import format_errors, validate_record

app = FastAPI(title="AgriTrial API Engine", version="1.0",
              description="Offline-first trial data capture and regulatory analytics (Act 36 of 1947).")


# ------------------------------------------------------------ access control --
def require_roles(*roles):
    """Dependency: allow the request only for the listed roles."""
    def check(x_user_role: str = Header(default="")):
        if x_user_role not in roles:
            raise HTTPException(status_code=403, detail="This role is not allowed to do that.")
        return x_user_role
    return check


any_user = require_roles(*config.ALL_ROLES)
stakeholder = require_roles(*config.STAKEHOLDER_ROLES)
farmer_only = require_roles(config.ROLE_FARMER)
dalrrd_only = require_roles(config.ROLE_DALRRD)


# -------------------------------------------------------------------- health --
@app.get("/health", tags=["system"])
def health():
    """The phone calls this to decide if it is online. cloud=false means Supabase is
    paused/unreachable, so records simply stay PENDING."""
    store = get_store()
    return {"api": "ok", "cloud": store.ping(), "backend": store.name}


@app.get("/api/v1/lookups", tags=["setup"])
def lookups():
    """Dropdown lists (staging values until Eduponics confirms them)."""
    return {"sites": config.SITES, "environments": config.ENVIRONMENTS, "crops": config.CROPS,
            "treatment_groups": config.TREATMENT_GROUPS, "visit_types": config.VISIT_TYPES}


# ---------------------------------------------------------------------- auth --
@app.post("/auth/signup", tags=["auth"])
def signup(body: dict = Body(...)):
    """Create a farmer account (needs internet the first time). Returns the new OID."""
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if len(username) < 3 or len(password) < 6:
        raise HTTPException(400, "Username needs 3+ characters and password 6+ characters.")
    store = get_store()
    if store.get_user(username):
        raise HTTPException(409, "That username is already taken.")
    salt, pw_hash = hash_password(password)
    # Self sign-up is always a Small Farmer. Stakeholder accounts are created by an admin.
    oid = store.create_user(username, config.ROLE_FARMER, body.get("full_name"),
                           body.get("contact"), salt, pw_hash)
    return {"oid": oid, "username": username, "role": config.ROLE_FARMER,
            "full_name": body.get("full_name")}


@app.post("/auth/login", tags=["auth"])
def login(body: dict = Body(...)):
    user = get_store().get_user(str(body.get("username", "")).strip())
    if not user or not verify_password(str(body.get("password", "")), user["salt"],
                                       user["password_hash"]):
        raise HTTPException(401, "Wrong username or password.")
    return {"oid": user["oid"], "username": user["username"], "role": user["role"],
            "full_name": user["full_name"]}


# --------------------------------------------------------- site / plot setup --
@app.get("/api/v1/sites", tags=["setup"])
def list_sites(_=Depends(any_user)):
    return get_store().list_sites()


@app.post("/api/v1/sites", tags=["setup"])
def create_site(body: dict = Body(...), _=Depends(farmer_only)):
    """Server Wins: if the site already exists, the existing start date is returned."""
    try:
        date.fromisoformat(str(body.get("start_date")))
    except ValueError:
        raise HTTPException(400, "start_date must be a valid date (YYYY-MM-DD).")
    return get_store().create_site_if_absent(body.get("site_id"), body["start_date"])


@app.get("/api/v1/plots", tags=["setup"])
def list_plots(_=Depends(any_user)):
    return get_store().list_plots()


@app.post("/api/v1/plots", tags=["setup"])
def create_plot(body: dict = Body(...), _=Depends(farmer_only)):
    """Server Wins: if the plot already exists, the existing area is returned."""
    try:
        area = float(body.get("area_m2"))
    except (TypeError, ValueError):
        area = 0
    if area <= 0:
        raise HTTPException(400, "area_m2 must be a number greater than 0.")
    plot = {k: body.get(k) for k in ("plot_id", "site_id", "crop_id", "treatment_group_id")}
    plot["area_m2"] = area
    return get_store().create_plot_if_absent(plot)


# -------------------------------------------------------------------- trials --
@app.post("/api/v1/trials", tags=["trials"])
def upsert_trial(rec: dict = Body(...), _=Depends(farmer_only)):
    """Sync endpoint. Validates with the same rules as the phone, then saves to the cloud.

    200 {"status":"SUCCESS","cloud_record_id":"EP-T101"}  -> phone marks SYNCED
    422 {"status":"REJECTED","error":"..."}               -> phone marks FLAGGED_FOR_REVIEW
    5xx / timeout                                         -> record stays PENDING (retried)
    """
    errors = validate_record(rec)
    if errors:
        return JSONResponse(status_code=422,
                            content={"status": "REJECTED", "error": format_errors(errors)})
    try:
        record_id = get_store().upsert_trial(rec)
    except Exception as exc:  # cloud problem: not the farmer's fault, keep PENDING
        raise HTTPException(503, f"Cloud unavailable: {exc}")
    return {"status": "SUCCESS", "cloud_record_id": record_id}


@app.get("/api/v1/trials", tags=["trials"])
def get_trials(site_id: str = None, crop_id: str = None, treatment_group_id: str = None,
               trial_week: str = None, visit_type: str = None, plot_id: str = None,
               _=Depends(stakeholder)):
    """Trial data for a site / treatment group (filters are optional)."""
    return get_store().list_trials(site_id=site_id, crop_id=crop_id,
                                   treatment_group_id=treatment_group_id,
                                   trial_week=trial_week, visit_type=visit_type, plot_id=plot_id)


# ----------------------------------------------------------------- analytics --
def _check_variant(variant_group_id: str):
    if variant_group_id not in config.VARIANT_GROUPS:
        raise HTTPException(400, "variant_group_id must be TGID-1 to TGID-5.")


@app.get("/api/v1/analytics/nitrate-ci", tags=["analytics"])
def nitrate_ci(site_id: str = Query(...), crop_id: str = Query(...),
               variant_group_id: str = Query(...), trial_week: str = Query(...),
               _=Depends(stakeholder)):
    """Mean +/- 95% CI (Student's t) of nitrate for control vs variant, only when n >= 5 in both."""
    _check_variant(variant_group_id)
    store = get_store()

    def nitrate(group):
        rows = store.list_trials(site_id=site_id, crop_id=crop_id,
                                 treatment_group_id=group, trial_week=trial_week)
        return [r["nitrate_mg_l"] for r in rows]

    result = analytics.compare_nitrate(nitrate("TGID-0"), nitrate(variant_group_id))
    result.update(site_id=site_id, crop_id=crop_id, trial_week=trial_week,
                  variant_group_id=variant_group_id)
    return result


@app.get("/api/v1/analytics/plot-yield", tags=["analytics"])
def plot_yield(site_id: str = Query(...), crop_id: str = Query(...),
               treatment_group_id: str = Query(...), _=Depends(stakeholder)):
    """Yield (g/m2) for one plot. 'Harvest in progress' until a final harvest is confirmed."""
    plot_id = f"{site_id}-{crop_id}-{treatment_group_id}"
    store = get_store()
    plot = store.get_plot(plot_id)
    rows = store.list_trials(plot_id=plot_id, visit_type="HARVEST_VISIT")
    value = analytics.plot_yield(rows, plot["area_m2"] if plot else None)
    return {"plot_id": plot_id, "yield_g_m2": value,
            "status": "Harvest in progress" if value is None else "Complete"}


# ------------------------------------------------------------------- dossier --
@app.get("/api/v1/dossier", tags=["reports"])
def dossier(site_id: str = Query(...), crop_id: str = Query(...),
            variant_group_id: str = Query(...), _=Depends(dalrrd_only)):
    """DALRRD Act 36 dossier: ZIP with anonymised CSV and the combined protocol text."""
    _check_variant(variant_group_id)
    store = get_store()
    records = (store.list_trials(site_id=site_id, crop_id=crop_id, treatment_group_id="TGID-0")
               + store.list_trials(site_id=site_id, crop_id=crop_id,
                                   treatment_group_id=variant_group_id))
    data = build_dossier(records, store.get_protocol("TGID-0"),
                         store.get_protocol(variant_group_id), variant_group_id)
    filename = f"Act36_Dossier_{site_id}_{crop_id}_{variant_group_id}.zip"
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/v1/dossier-pdf", tags=["reports"])
def dossier_pdf(site_id: str = Query(...), crop_id: str = Query(...),
                trial_week: str = Query(None), _=Depends(dalrrd_only)):
    """DALRRD Act 36 PDF report: every treatment group compared with the control."""
    from report_pdf import build_pdf_report   # imported here so the rest of the API never needs it
    data = build_pdf_report(get_store(), site_id, crop_id, trial_week)
    filename = f"Act36_Report_{site_id}_{crop_id}.pdf"
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
