"""Act 36 PDF trial report: EVERY treatment group compared with the control.

build_pdf_report() reads the trial data from the cloud store and turns it into a PDF for
the regulator: summary of findings, a nitrate chart with 95% confidence intervals for all
groups, week-by-week means, growth and yield per group, the treatment protocols, and the
method and privacy notes.

Privacy: only anonymised fields are used. Observers are only COUNTED (never named), farmer
names, contact details and free-text notes are never read, and GPS is not collected at all.
"""
import io
import re
from datetime import date
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import analytics
import config

GREEN = colors.HexColor("#2e7d32")
YELLOW = colors.HexColor("#f9a825")
GREY = colors.HexColor("#5b6b7b")
DARK = colors.HexColor("#1f2933")
LIGHT = colors.HexColor("#eef2f0")
BAND = colors.HexColor("#dfe4e8")
GRID = colors.HexColor("#d5dbd8")
CELL_GREEN = colors.HexColor("#dcedc8")
CELL_YELLOW = colors.HexColor("#fff3c4")
CELL_GREY = colors.HexColor("#e3e7ea")


# ------------------------------------------------------------------ data ----
def _week_no(week: str) -> int:
    return int(week[3:])


def collect_report_data(store, site_id: str, crop_id: str, trial_week: str = None) -> dict:
    """Gather everything the report needs from the cloud store."""
    site = store.get_site(site_id)
    trials = {g: store.list_trials(site_id=site_id, crop_id=crop_id, treatment_group_id=g)
              for g in config.TREATMENT_GROUPS}
    weeks = sorted({r["trial_week"] for rows in trials.values() for r in rows}, key=_week_no)

    def nitrate(group, week):
        return [r.get("nitrate_mg_l") for r in trials[group] if r["trial_week"] == week]

    if trial_week not in weeks:        # default: the latest week where the control has enough data
        trial_week = None
        for week in reversed(weeks):
            if analytics.summarise(nitrate("TGID-0", week))["n"] >= config.MIN_N:
                trial_week = week
                break
        if trial_week is None and weeks:
            trial_week = weeks[-1]

    results = []
    if trial_week:
        results = analytics.compare_all_groups(
            nitrate("TGID-0", trial_week),
            {g: nitrate(g, trial_week) for g in config.VARIANT_GROUPS})
    control = next((r["control"] for r in results if r["sufficient"]), None)

    weekly = {g: {w: analytics.summarise(nitrate(g, w)) for w in weeks}
              for g in config.TREATMENT_GROUPS}

    growth, yields = {}, {}
    for g in config.TREATMENT_GROUPS:
        routine = [r for r in trials[g]
                   if r["trial_week"] == trial_week and r.get("visit_type") != "HARVEST_VISIT"]
        growth[g] = {"records": len(trials[g]),
                     "height": analytics.summarise([r.get("plant_height_cm") for r in routine]),
                     "leaves": analytics.summarise([r.get("leaf_count") for r in routine])}
        plot = store.get_plot(f"{site_id}-{crop_id}-{g}")
        harvest = [r for r in trials[g] if r.get("visit_type") == "HARVEST_VISIT"]
        yields[g] = analytics.plot_yield(harvest, plot["area_m2"] if plot else None)

    return {
        "site_id": site_id, "crop_id": crop_id,
        "start_date": site["start_date"] if site else None,
        "source": getattr(store, "name", "cloud database"),
        "weeks": weeks, "trial_week": trial_week,
        "total_records": sum(len(rows) for rows in trials.values()),
        "observers": len({r.get("observer_id") for rows in trials.values() for r in rows}),
        "results": results, "control": control, "weekly": weekly,
        "growth": growth, "yields": yields,
        "protocols": {g: store.get_protocol(g) for g in config.TREATMENT_GROUPS},
    }


# --------------------------------------------------------------- helpers ----
def _fmt(value, digits=1) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _pct(value) -> str:
    return "-" if value is None else f"{value:+.1f}%"


def _md(text: str) -> str:
    """Tiny Markdown -> reportlab markup (bold and italics only), safely escaped."""
    t = escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", t)


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=19, leading=23, alignment=0, textColor=DARK, spaceAfter=3),
        "sub": ParagraphStyle("sub", parent=base["BodyText"], fontSize=10.5, leading=14,
                              textColor=GREY, spaceAfter=8),
        "h1": ParagraphStyle("h1", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=12.5, leading=16, textColor=GREEN, spaceBefore=13,
                             spaceAfter=5),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=9.5, leading=13.5,
                               spaceAfter=4),
        "bullet": ParagraphStyle("bullet", parent=base["BodyText"], fontSize=9.5, leading=13.5,
                                 leftIndent=12, bulletIndent=2, spaceAfter=3),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontSize=8, leading=10.5,
                                textColor=GREY, spaceAfter=3),
        "cell": ParagraphStyle("cell", parent=base["BodyText"], fontSize=8.5, leading=10.5),
        "hdr": ParagraphStyle("hdr", parent=base["BodyText"], fontName="Helvetica-Bold",
                              fontSize=8.5, leading=10.5, textColor=colors.white),
    }


def _table(rows, widths, st, extra=None):
    data = [[Paragraph(escape(str(c)), st["hdr"]) for c in rows[0]]]
    for row in rows[1:]:
        data.append([c if isinstance(c, Paragraph) else Paragraph(escape(str(c)), st["cell"])
                     for c in row])
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d1cc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        *(extra or [])]))
    return table


def _group_label(group: str) -> str:
    return "Control (TGID-0)" if group == "TGID-0" else group


# ---------------------------------------------------------------- charts ----
def _text(*args, **kwargs):
    """Chart label in Helvetica (reportlab's default would be Times)."""
    kwargs.setdefault("fontName", "Helvetica")
    return String(*args, **kwargs)


def _ci_chart(control, results, width=470, height=210) -> Drawing:
    """Mean and 95% CI for the control and every group that has enough data."""
    d = Drawing(width, height)
    left, right, bottom, top = 50, 12, 36, 24
    pw, ph = width - left - right, height - bottom - top

    items = [("TGID-0", control, "control", "")]
    for r in results:
        note = "" if r["sufficient"] else f"n = {r['n_variant']} (needs {r['min_n']})"
        items.append((r["group"], r["variant"] if r["sufficient"] else None, r.get("band"), note))

    stats = [i[1] for i in items if i[1]]
    lo, hi = min(s["ci_lower"] for s in stats), max(s["ci_upper"] for s in stats)
    pad = (hi - lo) * 0.18 or 1.0
    lo, hi = lo - pad, hi + pad

    def y(v):
        return bottom + (v - lo) / (hi - lo) * ph

    for k in range(5):                                   # horizontal grid + y labels
        v = lo + (hi - lo) * k / 4
        d.add(Line(left, y(v), left + pw, y(v), strokeColor=GRID, strokeWidth=0.5))
        d.add(_text(left - 6, y(v) - 3, f"{v:.0f}", fontSize=7, textAnchor="end", fillColor=GREY))
    d.add(Line(left, bottom, left + pw, bottom, strokeColor=GREY, strokeWidth=0.8))
    d.add(Line(left, bottom, left, bottom + ph, strokeColor=GREY, strokeWidth=0.8))

    d.add(Rect(left, y(control["ci_lower"]), pw, y(control["ci_upper"]) - y(control["ci_lower"]),
               fillColor=BAND, strokeColor=None))      # the control's 95% band across the chart
    d.add(Line(left, y(control["mean"]), left + pw, y(control["mean"]),
               strokeColor=GREY, strokeWidth=1, strokeDashArray=[4, 3]))

    slot = pw / len(items)
    for i, (group, s, band, note) in enumerate(items):
        cx = left + slot * (i + 0.5)
        d.add(_text(cx, bottom - 13, group, fontSize=7.5, textAnchor="middle", fillColor=DARK))
        if s is None:
            d.add(_text(cx, bottom + ph / 2, "insufficient data", fontSize=6.5,
                         textAnchor="middle", fillColor=GREY))
            d.add(_text(cx, bottom + ph / 2 - 9, note, fontSize=6.5, textAnchor="middle",
                         fillColor=GREY))
            continue
        color = GREY if band == "control" else (GREEN if band == "green" else YELLOW)
        d.add(Line(cx, y(s["ci_lower"]), cx, y(s["ci_upper"]), strokeColor=color, strokeWidth=2.2))
        for edge in (s["ci_lower"], s["ci_upper"]):
            d.add(Line(cx - 6, y(edge), cx + 6, y(edge), strokeColor=color, strokeWidth=2.2))
        d.add(Circle(cx, y(s["mean"]), 4.5, fillColor=color, strokeColor=DARK, strokeWidth=0.8))
        d.add(_text(cx + 9, y(s["mean"]) + 3, f"{s['mean']:.1f}", fontSize=7, fillColor=DARK))
    d.add(_text(left, height - 12, "Nitrate (mg/L): mean and 95% confidence interval",
                 fontSize=8.5, fontName="Helvetica-Bold", fillColor=DARK))
    return d


def _yield_chart(yields: dict, width=470, height=190) -> Drawing:
    d = Drawing(width, height)
    left, right, bottom, top = 50, 12, 30, 24
    pw, ph = width - left - right, height - bottom - top
    top_value = max([v for v in yields.values() if v is not None] or [1]) * 1.18

    def y(v):
        return bottom + v / top_value * ph

    for k in range(5):
        v = top_value * k / 4
        d.add(Line(left, y(v), left + pw, y(v), strokeColor=GRID, strokeWidth=0.5))
        d.add(_text(left - 6, y(v) - 3, f"{v:.0f}", fontSize=7, textAnchor="end", fillColor=GREY))
    d.add(Line(left, bottom, left + pw, bottom, strokeColor=GREY, strokeWidth=0.8))

    slot = pw / len(yields)
    for i, (group, value) in enumerate(yields.items()):
        cx = left + slot * (i + 0.5)
        d.add(_text(cx, bottom - 13, group, fontSize=7.5, textAnchor="middle", fillColor=DARK))
        if value is None:
            d.add(_text(cx, bottom + 6, "in progress", fontSize=7, textAnchor="middle",
                         fillColor=GREY))
            continue
        d.add(Rect(cx - 17, bottom, 34, y(value) - bottom,
                   fillColor=GREY if group == "TGID-0" else GREEN, strokeColor=None))
        d.add(_text(cx, y(value) + 4, f"{value:.0f}", fontSize=7.5, textAnchor="middle",
                     fillColor=DARK))
    d.add(_text(left, height - 12, "Yield (g/m2) per treatment group", fontSize=8.5,
                 fontName="Helvetica-Bold", fillColor=DARK))
    return d


# -------------------------------------------------------------- narrative ----
def _findings(data: dict) -> list:
    week, results = data["trial_week"], data["results"]
    if not week:
        return ["No trial records have been captured for this site and crop yet."]
    clear = [r for r in results if r["sufficient"] and not r["overlap"]]
    unclear = [r for r in results if r["sufficient"] and r["overlap"]]
    short = [r for r in results if not r["sufficient"]]

    lines = [f"In {week}, nitrate (mg/L) in the control group (TGID-0) was compared with "
             f"{len(results)} treatment groups using 95% confidence intervals (Student's t)."]
    if clear:
        lines.append("<b>Clear difference</b> from the control (intervals do not overlap): " +
                     "; ".join(f"{r['group']} ({_pct(r['difference_pct'])}, "
                               f"{'higher' if r['difference'] > 0 else 'lower'})" for r in clear)
                     + ".")
    if unclear:
        lines.append("<b>No clear difference</b> yet (intervals overlap): " +
                     "; ".join(f"{r['group']} ({_pct(r['difference_pct'])})" for r in unclear)
                     + ".")
    if short:
        lines.append("<b>Insufficient data</b> (fewer than 5 readings in a group): " +
                     "; ".join(f"{r['group']} (n = {r['n_variant']}, control n = {r['n_control']})"
                               for r in short) + ".")

    done = {g: v for g, v in data["yields"].items() if v is not None}
    if "TGID-0" in done and len(done) > 1:
        best = max(done, key=done.get)
        if best == "TGID-0":
            lines.append(f"Yield: the control had the highest yield ({done['TGID-0']:.0f} g/m2).")
        else:
            gain = (done[best] - done["TGID-0"]) / done["TGID-0"] * 100
            lines.append(f"Yield: {best} was highest at {done[best]:.0f} g/m2 "
                         f"({gain:+.1f}% compared with the control at {done['TGID-0']:.0f} g/m2).")
    else:
        lines.append("Yield comparison: harvests are not yet complete for all groups.")
    return lines


def _protocol_blocks(protocols: dict):
    """(description per group, shared trial conditions taken from the control protocol)."""
    descriptions = {}
    for group, text in protocols.items():
        descriptions[group] = _md(text.split("\n\n")[0]) if text else \
            "<i>Protocol text not yet confirmed by the research team.</i>"
    control = protocols.get("TGID-0") or ""
    shared = []
    if "\n\n" in control:
        for line in control.split("\n\n", 1)[1].splitlines():
            if line.strip():
                shared.append(_md(line.strip().lstrip("- ").strip()))
    return descriptions, shared


def _footer(data: dict):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(GRID)
        canvas.line(doc.leftMargin, 15 * mm, doc.pagesize[0] - doc.rightMargin, 15 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawString(doc.leftMargin, 10.5 * mm,
                          f"PlotTwist | Act 36 of 1947 trial report | {data['site_id']} | "
                          f"{data['crop_id']}")
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 10.5 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return draw


# ----------------------------------------------------------------- report ----
def build_pdf_report(store, site_id: str, crop_id: str, trial_week: str = None,
                     today: date = None, compress: bool = True) -> bytes:
    """Return the PDF report as bytes. (compress=False is only used by the tests.)"""
    data = collect_report_data(store, site_id, crop_id, trial_week)
    st = _styles()
    today = today or date.today()
    week, groups = data["trial_week"], config.TREATMENT_GROUPS
    usable = A4[0] - 36 * mm

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
        bottomMargin=22 * mm, title="Act 36 of 1947 - Group 3 Biostimulant Trial Report",
        author="PlotTwist", pageCompression=1 if compress else 0)
    story = []

    # ---- title and overview
    story += [Paragraph("Act 36 of 1947: Group 3 Biostimulant Trial Report", st["title"]),
              Paragraph(escape(f"Site {site_id} | Crop {crop_id} | Comparison week "
                               f"{week or 'none yet'}"), st["sub"])]
    covered = f"{data['weeks'][0]} to {data['weeks'][-1]}" if data["weeks"] else "none"
    overview = [["Item", "Detail"],
                ["Report date", today.isoformat()],
                ["Trial start date", data["start_date"] or "not set"],
                ["Trial weeks covered", covered],
                ["Trial records included", str(data["total_records"])],
                ["Observers (anonymised IDs only)", str(data["observers"])],
                ["Groups compared", "Control (TGID-0) with TGID-1 to TGID-5"],
                ["Data source", str(data["source"])]]
    story.append(_table(overview, [150, usable - 150], st))

    # ---- 1. summary
    story.append(Paragraph("1. Summary of findings", st["h1"]))
    for line in _findings(data):
        story.append(Paragraph(line, st["bullet"], bulletText="\u2022"))

    # ---- 2. nitrate comparison
    story.append(Paragraph(f"2. Nitrate: every treatment group compared with the control "
                           f"({week or 'no data'})", st["h1"]))
    if data["control"]:
        legend = Paragraph(
            "<font color='#2e7d32'><b>Green</b></font>: the 95% interval does not overlap the "
            "control (clear difference). <font color='#b58105'><b>Yellow</b></font>: the "
            "intervals overlap (no clear difference yet). The grey band is the control's own "
            "95% interval.", st["small"])
        story.append(KeepTogether([_ci_chart(data["control"], data["results"]), legend]))
    else:
        story.append(Paragraph("The control group has fewer than 5 valid nitrate readings in "
                               "this week, so no confidence interval chart can be drawn.",
                               st["body"]))
    rows, extra = [["Group", "n", "Mean (mg/L)", "95% CI", "Difference vs control", "Result"]], []
    if data["control"]:
        c = data["control"]
        rows.append(["Control (TGID-0)", c["n"], _fmt(c["mean"]),
                     f"{c['ci_lower']:.1f} to {c['ci_upper']:.1f}", "reference", "Reference"])
    for r in data["results"]:
        i = len(rows)
        if r["sufficient"]:
            v = r["variant"]
            rows.append([r["group"], v["n"], _fmt(v["mean"]),
                         f"{v['ci_lower']:.1f} to {v['ci_upper']:.1f}",
                         f"{r['difference']:+.1f} ({_pct(r['difference_pct'])})",
                         analytics.verdict(r)])
            extra.append(("BACKGROUND", (5, i), (5, i), CELL_YELLOW if r["overlap"] else CELL_GREEN))
        else:
            rows.append([r["group"], f"{r['n_variant']} (control {r['n_control']})", "-", "-", "-",
                         analytics.verdict(r)])
            extra.append(("BACKGROUND", (5, i), (5, i), CELL_GREY))
    story.append(KeepTogether([Spacer(1, 6), _table(rows, [80, 62, 56, 82, 96, usable - 376], st, extra)]))

    # ---- 3. week by week
    story.append(Paragraph("3. Nitrate week by week (mean mg/L)", st["h1"]))
    if data["weeks"]:
        head = ["Group"] + data["weeks"]
        trend = [head]
        for g in groups:
            cells = [_group_label(g)]
            for w in data["weeks"]:
                s = data["weekly"][g][w]
                cells.append("-" if s["n"] == 0 else f"{s['mean']:.1f}" + ("*" if s["n"] < 5 else ""))
            trend.append(cells)
        first = 84
        story.append(_table(trend, [first] + [(usable - first) / len(data["weeks"])] * len(data["weeks"]), st))
        story.append(Paragraph("* fewer than 5 readings in that week (too few for a confidence "
                               "interval). '-' = no readings.", st["small"]))
    else:
        story.append(Paragraph("No weekly data yet.", st["body"]))

    # ---- 4. growth and yield
    story.append(Paragraph(f"4. Growth ({week or 'no data'}) and yield by treatment group", st["h1"]))
    control_yield = data["yields"].get("TGID-0")
    grow = [["Group", "Records", "Mean height (cm)", "Mean leaf count", "Yield (g/m2)", "Yield vs control"]]
    for g in groups:
        y_val = data["yields"][g]
        vs = "-"
        if g != "TGID-0" and y_val is not None and control_yield:
            vs = _pct((y_val - control_yield) / control_yield * 100)
        grow.append([_group_label(g), data["growth"][g]["records"],
                     _fmt(data["growth"][g]["height"]["mean"]),
                     _fmt(data["growth"][g]["leaves"]["mean"]),
                     "in progress" if y_val is None else f"{y_val:.0f}", vs])
    story += [_table(grow, [84, 56, 86, 80, 78, usable - 384], st), Spacer(1, 8),
              _yield_chart(data["yields"])]

    # ---- 5. protocols
    story.append(Paragraph("5. Treatment protocols", st["h1"]))
    descriptions, shared = _protocol_blocks(data["protocols"])
    proto = [["Group", "Description"]] + [
        [_group_label(g), Paragraph(descriptions[g], st["cell"])] for g in groups]
    story.append(_table(proto, [84, usable - 84], st))
    if shared:
        story.append(Paragraph("<b>Conditions shared by all groups</b> (from the control protocol):",
                               st["body"]))
        for line in shared:
            story.append(Paragraph(line, st["bullet"], bulletText="\u2022"))
    if any("to be supplied" in (t or "") for t in data["protocols"].values()):
        story.append(Paragraph("Product, application rate, method and frequency marked 'to be "
                               "supplied' are pending confirmation by the research team.",
                               st["small"]))

    # ---- 6. method, limits, privacy
    story.append(Paragraph("6. Method, limitations and data privacy", st["h1"]))
    notes = [
        "<b>Statistics.</b> For each group the mean and sample standard deviation are calculated. "
        "The 95% confidence interval uses Student's t-distribution (n - 1 degrees of freedom). "
        "A comparison is made only when the control and the treatment group each have at least "
        "5 valid nitrate readings.",
        "<b>Reading the result.</b> If the 95% intervals of the control and a group do not "
        "overlap, the difference is clear. If they overlap, the data do not yet show a clear "
        "difference. That is not proof that there is none.",
        "<b>Yield.</b> Total fresh weight of a plot's harvest records divided by the plot area "
        "(g/m2). It is shown only after a harvest is marked complete.",
        "<b>Limitations.</b> One site and one crop, over the weeks listed above. This report "
        "supports, but does not replace, the formal Group 3 registration process under Act 36 "
        "of 1947.",
        "<b>Data privacy (POPIA).</b> This report contains anonymised trial measurements only. "
        "Farmer names, contact details and free-text notes are not included, and no GPS "
        "coordinates are collected.",
    ]
    for note in notes:
        story.append(Paragraph(note, st["body"]))

    doc.build(story, onFirstPage=_footer(data), onLaterPages=_footer(data))
    return buf.getvalue()
