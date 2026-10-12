"""AgriTrial MVP front end (Streamlit).

Run:  streamlit run app.py          (the API must be running: uvicorn api_engine:app)

Pages
  Everyone     : Log in / Sign up
  Small Farmer : Site & Plot -> Capture Record -> My Records & Sync
  Stakeholders : Dashboard (95% CI chart, yield, DALRRD dossier download)
"""
import os
from datetime import date, datetime

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

import api_client
import config
import database as db
import sync_worker
from validation import validate_record

st.set_page_config(page_title="AgriTrial MVP", page_icon="🌱", layout="centered")

# Large touch targets for farmers using phones in bright sun.
st.markdown("""
<style>
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
    min-height: 3.2rem; font-size: 1.1rem; font-weight: 600; width: 100%;
}
input, .stSelectbox div[data-baseweb="select"] { font-size: 1.05rem !important; }
</style>
""", unsafe_allow_html=True)

db.init_sqlite_db()


@st.cache_resource
def _start_background_sync():
    """One background sync thread per app process (skipped in automated tests)."""
    if os.getenv("AGRITRIAL_NO_BG_SYNC"):
        return None
    return sync_worker.start_background_sync(config.DB_PATH, config.API_URL)


_start_background_sync()
st.session_state.setdefault("user", None)
st.session_state.setdefault("ctx", None)       # chosen site / crop / treatment / plot
st.session_state.setdefault("form_n", 0)       # bumps after a save so the form clears


# ----------------------------------------------------------------- helpers --
def status_banner():
    """System Status: Online (Synced) / Offline (X records queued)."""
    pending = db.count_by_status()["PENDING"]
    flagged = db.count_by_status()["FLAGGED_FOR_REVIEW"]
    if sync_worker.is_online():
        if pending:
            st.info(f"System Status: Online ({pending} record(s) waiting to sync)")
        else:
            st.success("System Status: Online (Synced)")
    else:
        st.warning(f"System Status: Offline ({pending} Records Queued)")
    if flagged:
        st.error(f"{flagged} record(s) were rejected by the cloud. Open 'My Records' to see why.")


def do_login(username: str, password: str):
    """Offline-first login: saved credentials first, then the server (first time only)."""
    user = db.verify_local_user(username, password)
    if user:
        return user, None
    if not sync_worker.is_online():
        return None, ("No saved login for that user on this device. "
                      "Connect to the internet to log in the first time.")
    ok, result = api_client.login(username, password)
    if not ok:
        return None, result
    db.cache_user(result["oid"], result["username"], result["role"], result["full_name"], password)
    try:  # first login on this device: pull site / plot setup data
        sync_worker.sync_setup_data()
    except Exception:
        pass
    return result, None


# ------------------------------------------------------------------- pages --
def page_auth():
    st.title("🌱 AgriTrial")
    st.caption("Offline-first trial data capture for small farmers")
    status_banner()
    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log in"):
                user, error = do_login(username.strip(), password)
                if user:
                    st.session_state["user"] = user
                    st.rerun()
                st.error(error)

    with tab_signup:
        st.write("Create a farmer profile. This needs internet the first time; after that "
                 "you can log in offline.")
        with st.form("signup_form"):
            full_name = st.text_input("Full name")
            contact = st.text_input("Contact number or email")
            language = st.selectbox("Preferred language", config.LANGUAGES,
                                    help="Your choice is saved to your profile. Translated screens are planned for later.")
            new_user = st.text_input("Choose a username")
            new_pass = st.text_input("Choose a password (6+ characters)", type="password")
            if st.form_submit_button("Create profile"):
                if not sync_worker.is_online():
                    st.error("Sign-up needs an internet connection. Please try again when online.")
                else:
                    ok, result = api_client.signup(new_user.strip(), new_pass, full_name, contact)
                    if ok:
                        db.cache_user(result["oid"], result["username"], result["role"],
                                      result["full_name"], new_pass)
                        db.set_setting("language", language)
                        st.success(f"Profile created. Your Observer ID is {result['oid']}. "
                                   f"You can now log in.")
                    else:
                        st.error(result)


def page_site_plot():
    st.header("Site & Plot")
    st.caption("A plot is one site + one crop + one treatment group.")
    site_id = st.selectbox("Site", config.SITES)
    site = db.get_site(site_id)
    if site is None:
        st.info("First-time site setup: when did this trial start?")
        start = st.date_input("Site start date", value=date.today())
        if st.button("Save site setup"):
            db.upsert_site(site_id, start.isoformat())
            st.rerun()
        return
    st.write(f"**Site start date:** {site['start_date']}")

    environment = st.selectbox("Environment", config.ENVIRONMENTS)
    crop = st.selectbox("Crop", config.CROPS)
    tgid = st.selectbox("Treatment group", config.TREATMENT_GROUPS,
                        format_func=lambda g: f"{g} (Control)" if g == "TGID-0" else g)
    plot_id = db.plot_id_for(site_id, crop, tgid)
    plot = db.get_plot(plot_id)
    if plot is None:
        st.info("First-time plot setup: how big is this plot?")
        area = st.number_input("Plot surface area (m²)", value=None, step=0.5, format="%.1f")
        if st.button("Save plot setup"):
            if area is None or area <= 0:
                st.error("Setup blocked: a plot area greater than 0 m² is required.")
            else:
                db.upsert_plot(plot_id, site_id, crop, tgid, float(area))
                st.rerun()
        return
    st.write(f"**Plot area:** {plot['area_m2']} m²")
    if st.button("Use this plot ➜"):
        st.session_state["ctx"] = {"site_id": site_id, "environment_id": environment,
                                   "crop_id": crop, "treatment_group_id": tgid,
                                   "plot_id": plot_id, "start_date": site["start_date"]}
        st.success("Plot selected. Open 'Capture Record' in the menu.")


NUMBER_FIELDS = [  # (record field, label, step)
    ("fresh_weight_g", "Fresh weight (g)", 1.0), ("dry_weight_g", "Dry weight (g)", 1.0),
    ("spad_index", "Chlorophyll index (SPAD)", 0.1), ("root_length_cm", "Root length (cm)", 0.1),
    ("ph_level", "pH (0 to 14)", 0.1), ("ec_level", "EC (mS/cm)", 0.1),
    ("dissolved_oxygen", "Dissolved O₂ (mg/L)", 0.1), ("temperature_c", "Temperature (°C)", 0.1),
    ("humidity_pct", "Humidity (%)", 1.0), ("nitrate_mg_l", "Nitrate (mg/L)", 1.0),
    ("phosphate_mg_l", "Phosphate (mg/L)", 1.0),
]


def page_capture():
    st.header("Capture Record")
    ctx = st.session_state["ctx"]
    if not ctx:
        st.info("Choose a site and plot first (menu: Site & Plot).")
        return
    user = st.session_state["user"]
    today = date.today().isoformat()
    trial_week = db.calculate_trial_week(ctx["start_date"], today)
    st.write(f"**{ctx['site_id']}** · {ctx['crop_id']} · {ctx['treatment_group_id']} · "
             f"**{trial_week or 'before site start'}** · {today} · Observer **{user['oid']}**")

    n = st.session_state["form_n"]
    visit_type = st.selectbox("Visit type", config.VISIT_TYPES, key=f"visit_{n}")
    final_harvest, confirm_missing = False, False
    if visit_type == "HARVEST_VISIT":
        final_harvest = st.checkbox("This is the FINAL harvest entry for this plot", key=f"final_{n}")
        if final_harvest:
            confirm_missing = st.checkbox("Save even if some harvest records have no fresh weight",
                                          key=f"confirm_{n}")

    with st.form(f"capture_form_{n}"):
        st.subheader("Required")
        height = st.number_input("Plant height (cm)", value=None, step=0.5, format="%.1f", key=f"h_{n}")
        leaves = st.number_input("Leaf count", value=None, step=1, format="%d", key=f"l_{n}")
        st.subheader("Optional readings")
        values = {f: st.number_input(label, value=None, step=step, key=f"{f}_{n}")
                  for f, label, step in NUMBER_FIELDS}
        notes = st.text_area("Notes (pests, maintenance...)", key=f"notes_{n}")
        submitted = st.form_submit_button("Submit Trial Record")

    if not submitted:
        return

    rec = {
        "local_id": db.new_local_id(), "created_timestamp": db.now_timestamp(),
        "entry_date": today, "site_id": ctx["site_id"], "environment_id": ctx["environment_id"],
        "crop_id": ctx["crop_id"], "treatment_group_id": ctx["treatment_group_id"],
        "plot_id": ctx["plot_id"], "trial_week": trial_week, "visit_type": visit_type,
        "observer_id": user["oid"], "plant_height_cm": height,
        "leaf_count": int(leaves) if leaves is not None else None,
        "notes": notes.strip() or None, "is_harvest_complete": False, **values,
    }

    errors = validate_record(rec)
    if errors:  # blocked: nothing is saved
        st.error("Submission blocked. Please fix:")
        for field, message in errors:
            st.write(f"• **{field}**: {message}")
        return

    if visit_type == "HARVEST_VISIT" and final_harvest:
        missing = db.count_harvest_missing_fresh(ctx["plot_id"]) + (1 if rec["fresh_weight_g"] is None else 0)
        if missing and not confirm_missing:
            st.warning(f"Warning: {missing} harvest record(s) are missing fresh weight. "
                       f"Go back and add it, or tick 'Save even if...' and submit again.")
            return
        rec["is_harvest_complete"] = True

    db.save_local_record(rec)
    st.session_state["form_n"] += 1
    if sync_worker.is_online():
        result = sync_worker.sync_pending_records()
        st.session_state["flash"] = ("success", "Record saved locally. " + result["message"])
    else:
        st.session_state["flash"] = ("warning", "Record saved locally on device (PENDING). "
                                     "It will upload automatically when you are back online.")
    st.rerun()


def page_records():
    st.header("My Records & Sync")
    user = st.session_state["user"]
    if st.button("Sync now"):
        st.info(sync_worker.sync_pending_records()["message"])
    rows = db.list_records(observer_id=user["oid"])
    if not rows:
        st.write("No records yet.")
        return
    frame = pd.DataFrame(rows)[["cloud_record_id", "entry_date", "trial_week", "treatment_group_id",
                                "visit_type", "plant_height_cm", "leaf_count", "nitrate_mg_l",
                                "sync_status", "rejection_reason"]]
    st.dataframe(frame, width="stretch", hide_index=True)


def page_dashboard():
    st.header("Stakeholder Dashboard")
    role = st.session_state["user"]["role"]
    if not sync_worker.is_online():
        st.warning("The dashboard reads from the cloud. Turn Offline mode off / connect to the internet.")
        return
    try:
        site_id = st.selectbox("Site", config.SITES)
        crop = st.selectbox("Crop", config.CROPS)
        variant = st.selectbox("Biostimulant variant (compared with TGID-0 control)", config.VARIANT_GROUPS)
        trials = api_client.get_json("/api/v1/trials", role, site_id=site_id, crop_id=crop)
        weeks = sorted({t["trial_week"] for t in trials}, key=lambda w: int(w[3:]))
        if not weeks:
            st.info("No trial data for this site and crop yet.")
            return
        week = st.selectbox("Trial week", weeks, index=len(weeks) - 1)
        ci = api_client.get_json("/api/v1/analytics/nitrate-ci", role, site_id=site_id,
                                 crop_id=crop, variant_group_id=variant, trial_week=week)
        yc = api_client.get_json("/api/v1/analytics/plot-yield", role, site_id=site_id,
                                 crop_id=crop, treatment_group_id="TGID-0")
        yv = api_client.get_json("/api/v1/analytics/plot-yield", role, site_id=site_id,
                                 crop_id=crop, treatment_group_id=variant)
    except requests.RequestException as exc:
        st.error(f"Could not load data from the API: {exc}")
        return

    st.subheader(f"Nitrate: Control vs {variant} ({week})")
    if not ci["sufficient"]:
        st.warning(ci["notice"])
    else:
        c, v = ci["control"], ci["variant"]
        fig = go.Figure(go.Scatter(
            x=["Control (TGID-0)", f"Variant ({variant})"], y=[c["mean"], v["mean"]],
            mode="markers", marker=dict(size=14, color=["#5b6b7b", "#2e7d32"]),
            error_y=dict(type="data", array=[c["margin"], v["margin"]], visible=True, thickness=2, width=10),
            hovertemplate="%{x}<br>mean %{y:.1f} mg/L<extra></extra>"))
        fig.update_layout(yaxis_title="Nitrate (mg/L), mean ± 95% CI", height=380,
                          margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
        st.plotly_chart(fig, width="stretch")
        (st.success if ci["band"] == "green" else st.warning)(ci["band_text"])
        st.dataframe(pd.DataFrame([
            {"Group": "Control", "n": c["n"], "Mean": round(c["mean"], 2),
             "95% CI": f"{c['ci_lower']:.1f} to {c['ci_upper']:.1f}"},
            {"Group": variant, "n": v["n"], "Mean": round(v["mean"], 2),
             "95% CI": f"{v['ci_lower']:.1f} to {v['ci_upper']:.1f}"}]),
            hide_index=True, width="stretch")

    st.subheader("Yield (g/m²)")
    col1, col2 = st.columns(2)
    for col, label, data in ((col1, "Control", yc), (col2, variant, yv)):
        col.metric(label, "Harvest in progress" if data["yield_g_m2"] is None
                   else f"{data['yield_g_m2']:.0f} g/m²")

    if role == config.ROLE_DALRRD:
        st.subheader("Regulatory report")
        if st.button("Generate Act 36 Dossier"):
            try:
                st.session_state["dossier"] = api_client.get_bytes(
                    "/api/v1/dossier", role, site_id=site_id, crop_id=crop, variant_group_id=variant)
            except requests.RequestException as exc:
                st.error(f"Could not generate the dossier: {exc}")
        if st.session_state.get("dossier"):
            st.download_button("⬇ Download dossier (ZIP)", st.session_state["dossier"],
                               file_name=f"Act36_Dossier_{site_id}_{crop}_{variant}.zip",
                               mime="application/zip")
            st.caption("Contains the anonymised CSV data and the combined control + variant protocol (Markdown).")


# --------------------------------------------------------------------- main --
user = st.session_state["user"]
if not user:
    page_auth()
else:
    with st.sidebar:
        st.write(f"**{user.get('full_name') or user['username']}**")
        st.caption(f"{user['role']} · {user['oid']}")
        offline = st.toggle("Offline mode (demo)", value=db.is_offline_mode(),
                            help="Forces the app to behave as if there is no internet.")
        if offline != db.is_offline_mode():
            db.set_setting("offline_mode", "1" if offline else "0")
            st.rerun()
        pages = (["Site & Plot", "Capture Record", "My Records & Sync"]
                 if user["role"] == config.ROLE_FARMER else ["Dashboard"])
        choice = st.radio("Menu", pages)
        if st.button("Log out"):
            st.session_state.update(user=None, ctx=None, dossier=None)
            st.rerun()

    status_banner()
    flash = st.session_state.pop("flash", None)
    if flash:
        getattr(st, flash[0])(flash[1])
    {"Site & Plot": page_site_plot, "Capture Record": page_capture,
     "My Records & Sync": page_records, "Dashboard": page_dashboard}[choice]()
