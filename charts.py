"""Dashboard charts (Plotly). The app calls these; the maths stays in analytics.py."""
import plotly.graph_objects as go

GREEN, YELLOW, GREY, DARK = "#2e7d32", "#f9a825", "#5b6b7b", "#1f2933"


def ci_figure(control: dict, results: list):
    """Mean +/- 95% CI for the control and every treatment group that has enough data.

    control : the "control" dict of any sufficient comparison (mean, ci_lower, ci_upper, margin)
    results : the list of compare_nitrate() results, one per treatment group, each with "group"
    Green = the group's interval does not overlap the control's; yellow = it overlaps.
    """
    names = ["Control (TGID-0)"]
    means, margins, colours = [control["mean"]], [control["margin"]], [GREY]
    for r in results:
        if r["sufficient"]:
            names.append(r["group"])
            means.append(r["variant"]["mean"])
            margins.append(r["variant"]["margin"])
            colours.append(GREEN if r["band"] == "green" else YELLOW)

    fig = go.Figure()
    # the control's own 95% interval as a grey band across the whole chart
    fig.add_hrect(y0=control["ci_lower"], y1=control["ci_upper"], fillcolor=GREY,
                  opacity=0.15, line_width=0)
    fig.add_hline(y=control["mean"], line_dash="dash", line_color=GREY,
                  annotation_text="Control mean", annotation_position="top left")
    fig.add_trace(go.Scatter(
        x=names, y=means, mode="markers",
        marker=dict(size=14, color=colours, line=dict(width=1, color=DARK)),
        error_y=dict(type="data", array=margins, visible=True, thickness=2, width=10, color=DARK),
        hovertemplate="%{x}<br>mean %{y:.1f} mg/L<extra></extra>"))
    fig.update_xaxes(categoryorder="array", categoryarray=names)
    fig.update_layout(
        yaxis_title="Nitrate (mg/L), mean and 95% CI", height=400, showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
        hoverlabel=dict(bgcolor=DARK, font=dict(color="#ffffff", size=14)))
    return fig


def yield_figure(yields: dict):
    """Yield (g/m2) per treatment group. A group still being harvested shows 'in progress'."""
    groups = list(yields)
    fig = go.Figure(go.Bar(
        x=groups,
        y=[v if v is not None else 0 for v in yields.values()],
        marker_color=[GREY if g == "TGID-0" else GREEN for g in groups],
        text=["in progress" if v is None else f"{v:.0f}" for v in yields.values()],
        textposition="outside",
        hovertemplate="%{x}<br>%{y:.0f} g/m2<extra></extra>"))
    fig.update_layout(yaxis_title="Yield (g/m2)", height=320, showlegend=False,
                      margin=dict(l=10, r=10, t=20, b=10))
    return fig
