"""Logo scatters for Adjusted EPA and other unit boards."""

from __future__ import annotations

from statistics import mean
from typing import Any

import altair as alt


def _finite(values: list) -> list[float]:
    out: list[float] = []
    for value in values:
        if value is None:
            continue
        try:
            num = float(value)
        except (TypeError, ValueError):
            continue
        if num == num:
            out.append(num)
    return out


def _fix_padding(node: Any) -> Any:
    """Streamlit's Vega renderer crashes if padding is a number instead of an object."""
    if isinstance(node, dict):
        if "padding" in node and not isinstance(node["padding"], dict):
            node = dict(node)
            node.pop("padding", None)
        return {key: _fix_padding(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_fix_padding(value) for value in node]
    return node


def _finish(chart: alt.Chart) -> dict:
    spec = _fix_padding(chart.to_dict())
    pad = {"top": 8, "left": 8, "right": 8, "bottom": 24}
    spec["padding"] = pad
    spec.pop("autosize", None)
    cfg = spec.setdefault("config", {})
    if not isinstance(cfg, dict):
        cfg = {}
        spec["config"] = cfg
    cfg["padding"] = pad
    view = cfg.get("view")
    if isinstance(view, dict) and "padding" in view and not isinstance(view["padding"], dict):
        view.pop("padding", None)
    return spec


def logo_scatter(
    plot: list[dict],
    x: str,
    y: str,
    *,
    x_title: str,
    y_title: str,
    reverse_y: bool = False,
    origin: str = "mean",
    extra_tips: list[str] | None = None,
    height: int = 560,
) -> dict:
    xs = _finite([row.get(x) for row in plot])
    ys = _finite([row.get(y) for row in plot])
    data = alt.Data(values=plot)

    if origin == "zero":
        span = max([12.0] + [abs(v) for v in xs] + [abs(v) for v in ys])
        lim = span * 1.16
        x_domain = [-lim, lim]
        y_domain = [-lim, lim]
        x_ref, y_ref = 0.0, 0.0
        nice = False
    else:
        def _pad(vals: list[float]) -> list[float]:
            if not vals:
                return [0.0, 1.0]
            lo, hi = min(vals), max(vals)
            if lo == hi:
                pad = abs(lo) * 0.1 or 1.0
                return [lo - pad, hi + pad]
            pad = (hi - lo) * 0.16
            return [lo - pad, hi + pad]

        x_domain = _pad(xs)
        y_domain = _pad(ys)
        x_ref = mean(xs) if xs else 0.0
        y_ref = mean(ys) if ys else 0.0
        nice = True

    xenc = alt.X(
        f"{x}:Q",
        title=x_title,
        scale=alt.Scale(domain=x_domain, nice=nice, zero=origin == "zero"),
        axis=alt.Axis(tickCount=8),
    )
    yenc = alt.Y(
        f"{y}:Q",
        title=y_title,
        scale=alt.Scale(domain=y_domain, reverse=reverse_y, nice=nice, zero=origin == "zero"),
        axis=alt.Axis(tickCount=8),
    )
    tips = [
        alt.Tooltip("Team:N"),
        alt.Tooltip("Club:N"),
        alt.Tooltip(f"{x}:Q", format=".1f"),
        alt.Tooltip(f"{y}:Q", format=".1f"),
    ]
    for field in extra_tips or []:
        if field in {x, y, "Team", "Club", "Logo"}:
            continue
        tips.append(alt.Tooltip(f"{field}:Q", format=".1f"))

    layers = []
    if origin != "none":
        layers.append(
            alt.Chart(alt.Data(values=[{x: x_ref}]))
            .mark_rule(color="#d8a94b", opacity=0.8, strokeWidth=1.6)
            .encode(x=xenc)
        )
        layers.append(
            alt.Chart(alt.Data(values=[{y: y_ref}]))
            .mark_rule(color="#d8a94b", opacity=0.8, strokeWidth=1.6)
            .encode(y=yenc)
        )
    layers.extend(
        [
            alt.Chart(data)
            .mark_image(width=30, height=30)
            .encode(x=xenc, y=yenc, url="Logo:N", tooltip=tips),
            alt.Chart(data)
            .mark_text(dy=22, fontSize=11, fontWeight=700, color="#0d1117")
            .encode(x=xenc, y=yenc, text="Team:N", tooltip=tips),
            alt.Chart(data)
            .mark_text(dy=22, fontSize=11, fontWeight=700, color="#e6edf3")
            .encode(x=xenc, y=yenc, text="Team:N", tooltip=tips),
        ]
    )
    chart = layers[0]
    for layer in layers[1:]:
        chart = chart + layer
    chart = chart.properties(height=height).configure_axis(
        grid=True,
        gridColor="#2a3440",
        domainColor="#8b98a5",
        tickColor="#8b98a5",
        labelColor="#c5d0da",
        titleColor="#e6edf3",
        titleFontSize=13,
        titleFontWeight=600,
        labelFontSize=11,
        titlePadding=12,
    ).configure_view(stroke="#242e3a")
    return _finish(chart)


def adj_epa_scatter(plot: list[dict], height: int = 660) -> dict:
    return logo_scatter(
        plot,
        "Adj Off",
        "Adj Def",
        x_title="Offense (adj EPA/g)   --> better",
        y_title="Defense (adj EPA/g)   better is up",
        reverse_y=True,
        origin="zero",
        extra_tips=["Adj Net"],
        height=height,
    )


def regular_epa_scatter(plot: list[dict], height: int = 660) -> dict:
    return logo_scatter(
        plot,
        "Off EPA/g",
        "Def EPA/g",
        x_title="Offense (EPA/g)   --> better",
        y_title="Defense (EPA allowed/g)   better is up",
        reverse_y=True,
        origin="zero",
        extra_tips=["Net EPA/g"],
        height=height,
    )
