"""Weekly NFL matchup board for a family football pool."""

from __future__ import annotations

import html
from math import nan
from pathlib import Path
from typing import NamedTuple

import streamlit as st

from data.matchups import available_weeks, build_week_board, current_week, format_spread, league_team_rows
from data.personnel import injury_status_counts
from data.schedules import format_kickoff_pt
from data.teamref import division, logo_url, pair_colors, team_name

_ICON = Path(__file__).with_name("assets") / "nfl-board.png"
st.set_page_config(
    page_title="NFL Matchup Board",
    page_icon=str(_ICON) if _ICON.exists() else "🏈",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={"About": "NFL Matchup Board — weekly pool comparison. Built with Streamlit."},
)

st.markdown(
    """
    <style>
      [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none; }
      .block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1500px; }

      .masthead { display: flex; align-items: baseline; gap: 0.6rem; }
      .masthead .rule { width: 4px; height: 1.55rem; background: #d8a94b; border-radius: 2px; }
      .masthead h1 {
        font-size: 1.5rem; font-weight: 750; letter-spacing: -0.01em;
        margin: 0; padding: 0; line-height: 1.1;
      }
      .masthead .sub { color: #8b98a5; font-size: 0.82rem; margin: 0.15rem 0 0 0.95rem; }

      .chips { display: flex; flex-wrap: wrap; gap: 0.45rem; margin: 0.15rem 0 0.9rem; }
      .chip {
        display: inline-flex; align-items: baseline; gap: 0.4rem;
        padding: 0.3rem 0.7rem; border-radius: 999px;
        background: #141b23; border: 1px solid #242e3a; font-size: 0.82rem;
      }
      .chip b { color: #e6edf3; font-weight: 650; }
      .chip span { color: #8b98a5; }

      .panel {
        border: 1px solid #242e3a; border-radius: 0.7rem;
        background: #121820; padding: 0.85rem 1rem; height: 100%;
      }
      .panel-h {
        font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.09em;
        color: #8b98a5; font-weight: 700; margin-bottom: 0.7rem;
      }
      .panel ul { margin: 0; padding-left: 1.05rem; }
      .panel li { margin-bottom: 0.3rem; font-size: 0.9rem; line-height: 1.45; }
      .panel li:last-child { margin-bottom: 0; }
      .panel .foot { color: #8b98a5; font-size: 0.78rem; margin-top: 0.7rem; line-height: 1.4; }

      .hero {
        display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 1rem;
        border: 1px solid #242e3a; border-radius: 0.8rem; background: #121820;
        padding: 0.9rem 1.2rem; margin-bottom: 0.9rem;
      }
      .hero-team { display: flex; align-items: center; gap: 0.75rem; min-width: 0; }
      .hero-team.home { flex-direction: row-reverse; text-align: right; }
      .hero-team img { width: 46px; height: 46px; object-fit: contain; }
      .hero-abbr { font-size: 1.35rem; font-weight: 750; line-height: 1.1; }
      .hero-name { color: #8b98a5; font-size: 0.8rem; white-space: nowrap; }
      .hero-mid { text-align: center; }
      .hero-score { font-size: 1.5rem; font-weight: 700; font-variant-numeric: tabular-nums; }
      .hero-at { font-size: 0.78rem; letter-spacing: 0.16em; color: #6f7d8c; text-transform: uppercase; }
      .hero-meta { color: #8b98a5; font-size: 0.8rem; margin-top: 0.2rem; white-space: nowrap; }

      .cmp { display: flex; flex-direction: column; gap: 0.42rem; }
      .cmp-row {
        display: grid; grid-template-columns: 3.4rem 1fr 8.6rem 1fr 3.4rem;
        align-items: center; gap: 0.4rem;
      }
      .cmp-num { font-size: 0.85rem; font-variant-numeric: tabular-nums; color: #93a2b1; }
      .cmp-num.l { text-align: right; }
      .cmp-num.r { text-align: left; }
      .cmp-num.best { color: #e6edf3; font-weight: 700; }
      .cmp-track { height: 0.4rem; border-radius: 999px; background: #1a222c; display: flex; }
      .cmp-track.l { justify-content: flex-end; }
      .cmp-fill { height: 100%; border-radius: 999px; }
      .cmp-label {
        text-align: center; font-size: 0.77rem; color: #8b98a5;
        cursor: help; border-bottom: 1px dotted #39444f; justify-self: center;
      }

      .form-line { font-size: 0.88rem; line-height: 1.6; }
      .form-line b { font-variant-numeric: tabular-nums; }
      .split { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
      .glossary { display: grid; grid-template-columns: repeat(auto-fit, minmax(310px, 1fr)); gap: 0.5rem 1.6rem; }
      .glossary div { font-size: 0.86rem; line-height: 1.45; }
      .glossary b { color: #d8a94b; }

      @media (max-width: 820px) {
        .hero { grid-template-columns: 1fr; gap: 0.5rem; }
        .hero-team.home { flex-direction: row; text-align: left; }
        .cmp-row { grid-template-columns: 2.9rem 1fr 6.6rem 1fr 2.9rem; }
        .cmp-label { font-size: 0.72rem; }
        .split { grid-template-columns: 1fr; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- format


def _fmt(val, digits=1, signed=False, suffix=""):
    if val is None:
        return "—"
    try:
        num = float(val)
    except (TypeError, ValueError):
        return "—"
    body = f"{num:+.{digits}f}" if signed else f"{num:.{digits}f}"
    return body + suffix


def _pct(val):
    if val is None:
        return "—"
    try:
        num = float(val)
    except (TypeError, ValueError):
        return "—"
    return f"{100.0 * num:.0f}%"


def _pct_value(val):
    """Fraction (0-1) to a 0-100 float for progress columns."""
    if val is None:
        return None
    try:
        return round(100.0 * float(val), 1)
    except (TypeError, ValueError):
        return None


def _num(val):
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _grid_height(rows: int, cap: int = 760) -> int:
    """Size the grid to its rows so it never opens as a short scroll window."""
    return min(cap, 35 * max(rows, 1) + 42)


def _nan(val):
    """Numeric or NaN, so number columns render a blank instead of the word None."""
    num = _num(val)
    return nan if num is None else num


# --------------------------------------------------------------------------- data


@st.cache_data(ttl=3600, show_spinner="Loading nflverse, nfelo and weather data…")
def _cards(season: int, week: int, _ver: int = 4):
    return build_week_board(season, week)


@st.cache_data(ttl=3600)
def _weeks(season: int):
    return available_weeks(season)


@st.cache_data(ttl=3600, show_spinner="Loading team form…")
def _league_teams(season: int, week: int, _ver: int = 2):
    return league_team_rows(season, week)


GLOSSARY = [
    ("EPA", "Expected points added — how much a play moved the team's expected points. Offenses want it high, defenses want it low."),
    ("EPA/g", "EPA totalled per game played, so teams with a bye still compare fairly."),
    ("CPOE", "Completion percentage over expected — accuracy measured against the difficulty of the throws."),
    ("RYOE", "Rush yards over expected — Next Gen Stats, season total above what the blocking and box counts predicted."),
    ("Time to throw", "Average seconds from snap to release. Low is quick game, high means holding the ball."),
    ("Pressure %", "Share of dropbacks where the offensive line let a rusher get home (PFF)."),
    ("TO margin", "Turnover margin: takeaways minus giveaways."),
    ("nfelo", "Public Elo-style power rating. About 1500 is league average, 1650 is a contender."),
    ("Win%", "Home win probability from the nfelo model, or the betting moneyline when nfelo has no number."),
    ("Spread / Total", "Market line. The favorite carries the negative number; the total is the combined over/under."),
]


def _render_glossary() -> None:
    with st.expander("What the numbers mean"):
        items = "".join(
            f"<div><b>{html.escape(term)}</b> — {html.escape(text)}</div>"
            for term, text in GLOSSARY
        )
        st.markdown(f'<div class="glossary">{items}</div>', unsafe_allow_html=True)
        st.caption(
            "Sources: nflverse play-by-play, injuries and depth charts · PFF pressure data · "
            "Next Gen Stats · nfelo ratings · Open-Meteo forecasts. Data is cached for an hour."
        )


# --------------------------------------------------------------------------- shared bits


def _kickoff_label(c: dict) -> str:
    when = (c.get("kickoff_pt") or "").strip()
    return when or format_kickoff_pt(c.get("gameday"), c.get("gametime")) or "—"


def _conditions_text(c: dict) -> str:
    """One-line game conditions for the board."""
    if c.get("venue") != "outdoor":
        return "Indoor"
    bits = []
    temp = c.get("wx_temp_f") if c.get("wx_temp_f") is not None else c.get("temp")
    wind = c.get("wx_wind_mph") if c.get("wx_wind_mph") is not None else c.get("wind")
    if temp is not None:
        bits.append(f"{float(temp):.0f}°F")
    if wind is not None:
        bits.append(f"{float(wind):.0f} mph")
    if c.get("wx_precip_in"):
        bits.append(f"{float(c['wx_precip_in']):.2f}\" rain")
    return " · ".join(bits) or (c.get("weather_note") or "Outdoor")


def _status_counts(c: dict, side: str) -> tuple[int, int]:
    """(out or doubtful, questionable) for one side of a game."""
    counts = injury_status_counts(c.get(f"injuries_{side}_rows") or [])
    return counts["out"] + counts["doubtful"], counts["questionable"]


def _score_text(c: dict) -> str:
    if c.get("away_score") is None or c.get("home_score") is None:
        return ""
    return f"{int(c['away_score'])}–{int(c['home_score'])}"


# --------------------------------------------------------------------------- week board


def _board_rows(cards: list[dict], show_score: bool) -> list[dict]:
    rows = []
    for c in cards:
        home, away = c["home_team"], c["away_team"]
        out_a, q_a = _status_counts(c, "away")
        out_h, q_h = _status_counts(c, "home")
        row = {
            "Kickoff": _kickoff_label(c),
            "Matchup": f"{away} @ {home}",
            "Spread": format_spread(c.get("spread_line"), home, away),
            "Home win%": _pct_value(c.get("home_win_pct")),
            "Total": _num(c.get("total_line")),
            "Conditions": _conditions_text(c),
            "Out": f"{out_a} / {out_h}",
            "Quest.": f"{q_a} / {q_h}",
            "Key edge": c.get("standout_short") or "—",
        }
        if show_score:
            row = {**row, "Score": _score_text(c) or "—"}
            row = {k: row[k] for k in ["Kickoff", "Matchup", "Score", "Spread", "Home win%", "Total", "Conditions", "Out", "Quest.", "Key edge"]}
        rows.append(row)
    return rows


def _board_summary(cards: list[dict]) -> str:
    tossups = sum(1 for c in cards if c.get("spread_line") is not None and abs(float(c["spread_line"])) <= 3)
    outdoor = sum(1 for c in cards if c.get("venue") == "outdoor")
    out_players = sum(
        len([r for r in (c.get("injuries_away_rows") or []) + (c.get("injuries_home_rows") or []) if r.get("status") == "out"])
        for c in cards
    )
    chips = [
        ("Games", len(cards)),
        ("One-score spreads", tossups),
        ("Outdoor", outdoor),
        ("Players out", out_players),
    ]
    return '<div class="chips">' + "".join(
        f"<div class='chip'><b>{value}</b><span>{html.escape(label)}</span></div>" for label, value in chips
    ) + "</div>"


def _render_board(cards: list[dict], season: int, week: int) -> None:
    show_score = any(c.get("home_score") is not None and c.get("away_score") is not None for c in cards)
    st.markdown(_board_summary(cards), unsafe_allow_html=True)

    config = {
        "Kickoff": st.column_config.TextColumn("Kickoff", help="Kickoff in Pacific time", width=110),
        "Matchup": st.column_config.TextColumn("Matchup", help="Away team at home team", width=120),
        "Score": st.column_config.TextColumn("Score", help="Final score, away–home", width=80),
        "Spread": st.column_config.TextColumn("Spread", help="Market spread. The favorite carries the negative number.", width=100),
        "Home win%": st.column_config.ProgressColumn(
            "Home win%",
            help="Win probability for the home team (second team listed) from nfelo, or the moneyline when nfelo has no line.",
            format="%.0f%%",
            min_value=0,
            max_value=100,
            width=150,
        ),
        "Total": st.column_config.NumberColumn("Total", help="Market over/under for combined points", format="%.1f", width=75),
        "Conditions": st.column_config.TextColumn("Conditions", help="Kickoff forecast for outdoor stadiums (Open-Meteo)", width=160),
        "Out": st.column_config.TextColumn("Out", help="Players ruled out or doubtful — away / home", width=70),
        "Quest.": st.column_config.TextColumn("Quest.", help="Players listed questionable — away / home", width=75),
        "Key edge": st.column_config.TextColumn("Key edge", help="Largest statistical mismatch in the game", width="medium"),
    }

    st.caption(
        "Tick the box beside a game to open its full breakdown. "
        "Click a column header to sort, and hover a header to see what the number means."
    )
    nonce = st.session_state.get("board_nonce", 0)
    event = st.dataframe(
        _board_rows(cards, show_score),
        hide_index=True,
        width="stretch",
        height=_grid_height(len(cards)),
        column_config=config,
        key=f"board_{season}_{week}_{nonce}",
        on_select="rerun",
        selection_mode="single-row",
    )

    picked = list(event.selection.rows) if event and event.selection else []
    if picked:
        game_id = cards[picked[0]].get("game_id")
        if game_id:
            _set_view(season, week, game_id, page="week")
            st.rerun()

    _render_glossary()


# --------------------------------------------------------------------------- comparison bars


class Metric(NamedTuple):
    label: str
    home_key: str
    away_key: str
    digits: int
    higher_better: bool | None
    help: str
    suffix: str = ""
    scale: float = 1.0


_GROUPS: list[tuple[str, list[Metric]]] = [
    (
        "Passing",
        [
            Metric("Pass EPA/g", "u_h_pass", "u_a_pass", 1, True, "Expected points added per game on the offense's pass plays"),
            Metric("Pass EPA allowed/g", "u_h_pass_d", "u_a_pass_d", 1, False, "Expected points the defense gives up per game against the pass"),
            Metric("CPOE", "u_cpoe_home", "u_cpoe_away", 1, True, "Completion percentage over expected", "%"),
            Metric("Time to throw", "u_ttt_home", "u_ttt_away", 2, None, "Average seconds from snap to release (Next Gen Stats)", "s"),
        ],
    ),
    (
        "Rushing",
        [
            Metric("Run EPA/g", "u_h_rush", "u_a_rush", 1, True, "Expected points added per game on run plays"),
            Metric("Run EPA allowed/g", "u_h_rush_d", "u_a_rush_d", 1, False, "Expected points the defense gives up per game against the run"),
            Metric("RYOE", "u_ryoe_home", "u_ryoe_away", 0, True, "Rush yards over expected this season (Next Gen Stats)"),
        ],
    ),
    (
        "Trenches",
        [
            Metric("Pressures generated", "u_h_press_gen", "u_a_press_gen", 0, True, "Pass rush pressures the defensive front has produced (PFF)"),
            Metric("Pressures allowed", "u_h_press_all", "u_a_press_all", 0, False, "Pressures the offensive line has given up (PFF)"),
            Metric("Pressure % allowed", "u_press_pct_home", "u_press_pct_away", 1, False, "Share of dropbacks where the line allowed pressure (PFF)", "%"),
        ],
    ),
    (
        "Scoring and overall",
        [
            Metric("Points for/g", "u_h_pf", "u_a_pf", 1, True, "Points scored per game"),
            Metric("Points allowed/g", "u_h_pa", "u_a_pa", 1, False, "Points allowed per game"),
            Metric("Off EPA/g", "u_off_epa_pg_home", "u_off_epa_pg_away", 1, True, "Total offensive expected points added per game"),
            Metric("Def EPA/g allowed", "u_def_epa_pg_home", "u_def_epa_pg_away", 1, False, "Total expected points the defense allows per game"),
            Metric("TO margin/g", "u_to_home", "u_to_away", 2, True, "Turnover margin per game: takeaways minus giveaways"),
        ],
    ),
    (
        "Special teams",
        [
            Metric("FG%", "u_fg_home", "u_fg_away", 1, True, "Field goal percentage", "%", 100.0),
            Metric("Punt net yds/g", "u_punt_net_home", "u_punt_net_away", 0, True, "Net punting yards per game"),
            Metric("ST TDs", "u_st_tds_home", "u_st_tds_away", 0, True, "Special teams touchdowns this season"),
        ],
    ),
]


def _bar(width_pct: float, color: str, dim: bool) -> str:
    fill = f"{color}59" if dim else color
    return f'<span class="cmp-fill" style="width:{width_pct:.0f}%;background:{fill}"></span>'


def _cmp_row(metric: Metric, card: dict, colors: tuple[str, str]) -> str:
    a_val = _num(card.get(metric.away_key))
    h_val = _num(card.get(metric.home_key))
    if a_val is not None:
        a_val *= metric.scale
    if h_val is not None:
        h_val *= metric.scale

    a_best = h_best = False
    if metric.higher_better is not None and a_val is not None and h_val is not None and a_val != h_val:
        if metric.higher_better:
            a_best, h_best = a_val > h_val, h_val > a_val
        else:
            a_best, h_best = a_val < h_val, h_val < a_val

    span = max(abs(a_val or 0.0), abs(h_val or 0.0)) or 1.0
    a_width = 100.0 * abs(a_val) / span if a_val is not None else 0.0
    h_width = 100.0 * abs(h_val) / span if h_val is not None else 0.0

    return (
        '<div class="cmp-row">'
        f'<div class="cmp-num l{" best" if a_best else ""}">{_fmt(a_val, metric.digits, suffix=metric.suffix)}</div>'
        f'<div class="cmp-track l">{_bar(a_width, colors[0], not a_best)}</div>'
        f'<div class="cmp-label" title="{html.escape(metric.help)}">{html.escape(metric.label)}</div>'
        f'<div class="cmp-track r">{_bar(h_width, colors[1], not h_best)}</div>'
        f'<div class="cmp-num r{" best" if h_best else ""}">{_fmt(h_val, metric.digits, suffix=metric.suffix)}</div>'
        "</div>"
    )


def _has_values(metrics: list[Metric], card: dict) -> bool:
    return any(card.get(m.home_key) is not None or card.get(m.away_key) is not None for m in metrics)


def _has_unit_data(card: dict) -> bool:
    """False before any games are played, when every season stat is still empty."""
    return any(_has_values(metrics, card) for _title, metrics in _GROUPS)


def _cmp_panel(title: str, metrics: list[Metric], card: dict, colors: tuple[str, str], footer: str = "") -> str:
    if not _has_values(metrics, card):
        return ""
    rows = "".join(_cmp_row(m, card, colors) for m in metrics)
    foot = f'<div class="foot">{html.escape(footer)}</div>' if footer else ""
    return f'<div class="panel"><div class="panel-h">{html.escape(title)}</div><div class="cmp">{rows}</div>{foot}</div>'


# --------------------------------------------------------------------------- game page


def _hero(c: dict) -> str:
    away, home = c["away_team"], c["home_team"]
    score = _score_text(c)
    if score:
        a_pts, h_pts = int(c["away_score"]), int(c["home_score"])
        a_style = "" if a_pts >= h_pts else "color:#8b98a5"
        h_style = "" if h_pts >= a_pts else "color:#8b98a5"
        middle = f'<div class="hero-score"><span style="{a_style}">{a_pts}</span> – <span style="{h_style}">{h_pts}</span></div>'
    else:
        middle = '<div class="hero-at">at</div>'
    meta = " · ".join(x for x in [_kickoff_label(c), c.get("stadium") or "", _conditions_text(c)] if x)

    colors = pair_colors(away, home)

    def side(abbr: str, css: str, color: str) -> str:
        logo = logo_url(abbr)
        img = f'<img src="{logo}" alt="">' if logo else ""
        return (
            f'<div class="hero-team {css}">{img}<div>'
            f'<div class="hero-abbr" style="color:{color}">{html.escape(abbr)}</div>'
            f'<div class="hero-name">{html.escape(team_name(abbr))} · {html.escape(division(abbr))}</div>'
            "</div></div>"
        )

    return (
        '<div class="hero">'
        + side(away, "away", colors[0])
        + f'<div class="hero-mid">{middle}<div class="hero-meta">{html.escape(meta)}</div></div>'
        + side(home, "home", colors[1])
        + "</div>"
    )


def _standouts_panel(c: dict) -> str:
    items = []
    for item in c.get("standouts") or []:
        text = item.get("detail") or item.get("label") or "" if isinstance(item, dict) else str(item)
        if text:
            items.append(f"<li>{html.escape(text)}</li>")
    if not items:
        fallback = (
            "No large statistical gaps — this one grades out close on paper."
            if _has_unit_data(c)
            else "Season stats begin after week 1, so there is nothing to compare yet."
        )
        items = [f"<li>{fallback}</li>"]
    return f'<div class="panel"><div class="panel-h">Why this game stands out</div><ul>{"".join(items)}</ul></div>'


def _injury_panel(c: dict, side: str) -> str:
    team = c[f"{side}_team"]
    out, quest = _status_counts(c, side)
    names = c.get(f"injuries_out_{side}") or ""
    detail = f"Starters out: {names}" if names else "No listed starters out."
    return (
        f'<div class="panel"><div class="panel-h">{html.escape(team)} availability</div>'
        f'<div class="chips" style="margin:0">'
        f"<div class='chip'><b>{out}</b><span>out or doubtful</span></div>"
        f"<div class='chip'><b>{quest}</b><span>questionable</span></div>"
        f"</div><div class='foot'>{html.escape(detail)}</div></div>"
    )


def _form_panel(c: dict) -> str:
    """Recent form for both clubs in one panel."""
    keys = [f"rec_{stat}_{side}" for stat in ("off_epa_pg", "def_epa_pg", "to_diff") for side in ("away", "home")]
    if all(c.get(k) is None for k in keys):
        return ""
    sides = []
    colors = pair_colors(c["away_team"], c["home_team"])
    for side, color in zip(("away", "home"), colors):
        team = c[f"{side}_team"]
        sides.append(
            f'<div><div style="color:{color};font-weight:650;margin-bottom:0.2rem">{html.escape(team)}</div>'
            f'<div class="form-line">Offense <b>{_fmt(c.get(f"rec_off_epa_pg_{side}"))}</b> EPA per game<br>'
            f'Defense <b>{_fmt(c.get(f"rec_def_epa_pg_{side}"))}</b> EPA allowed per game<br>'
            f'Turnover margin <b>{_fmt(c.get(f"rec_to_diff_{side}"), 1, signed=True)}</b></div></div>'
        )
    return (
        '<div class="panel"><div class="panel-h">Recent form — last 3 games</div>'
        f'<div class="split">{"".join(sides)}</div></div>'
    )


def render_matchup(c: dict) -> None:
    away, home = c["away_team"], c["home_team"]
    st.markdown(_hero(c), unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(
        f"{home} win probability",
        _pct(c.get("home_win_pct")),
        border=True,
        help="Chance the home team wins, from the nfelo model or the betting moneyline when nfelo has no line.",
    )
    m2.metric(
        "Spread",
        format_spread(c.get("spread_line"), home, away),
        border=True,
        help="Market spread. The favorite carries the negative number.",
    )
    m3.metric(
        "Total",
        _fmt(c.get("total_line"), 1),
        border=True,
        help="Market over/under for combined points.",
    )
    gap = None
    if c.get("nfelo_home") is not None and c.get("nfelo_away") is not None:
        gap = c["nfelo_home"] - c["nfelo_away"]
    m4.metric(
        f"nfelo · {away} / {home}",
        f"{_fmt(c.get('nfelo_away'), 0)} · {_fmt(c.get('nfelo_home'), 0)}",
        border=True,
        help="Elo-style power ratings. About 1500 is league average.",
    )

    notes = [f"Win probability from {c.get('win_pct_source') or 'unknown source'}"]
    nfelo_line = c.get("nfelo_home_line")
    if nfelo_line is not None:
        notes.append(f"nfelo's own line is {home} {nfelo_line:+.1f}")
    if gap is not None:
        notes.append(f"{home if gap >= 0 else away} rates {abs(gap):.0f} points of Elo higher")
    st.caption(" · ".join(notes))

    left, right = st.columns([1.35, 1])
    with left:
        st.markdown(_standouts_panel(c), unsafe_allow_html=True)
    with right:
        i1, i2 = st.columns(2)
        i1.markdown(_injury_panel(c, "away"), unsafe_allow_html=True)
        i2.markdown(_injury_panel(c, "home"), unsafe_allow_html=True)

    colors = pair_colors(away, home)
    if not _has_unit_data(c):
        st.info("Season statistics start once teams have played, so only the market line, weather and injuries are available this week.")
        _render_glossary()
        return

    st.markdown(
        f'<div class="chips" style="margin-top:1rem"><div class="chip"><span>Bars compare</span>'
        f'<b style="color:{colors[0]}">{html.escape(away)}</b><span>left vs</span>'
        f'<b style="color:{colors[1]}">{html.escape(home)}</b><span>right — the brighter bar is the better number</span></div></div>',
        unsafe_allow_html=True,
    )

    rush_bits = [
        f"{team}: {c.get(key)}"
        for team, key in ((away, "u_top_rushers_away"), (home, "u_top_rushers_home"))
        if c.get(key)
    ]
    panels = []
    for title, metrics in _GROUPS:
        footer = f"Top pressure producers — {' · '.join(rush_bits)}" if title == "Trenches" and rush_bits else ""
        panels.append(_cmp_panel(title, metrics, c, colors, footer))
    panels.append(_form_panel(c))
    panels = [p for p in panels if p]

    for index in range(0, len(panels), 2):
        cols = st.columns(2)
        cols[0].markdown(panels[index], unsafe_allow_html=True)
        if index + 1 < len(panels):
            cols[1].markdown(panels[index + 1], unsafe_allow_html=True)
        st.write("")

    _render_glossary()


_STATUS_LABEL = {"out": "OUT", "doubtful": "Doubtful", "questionable": "Questionable"}
_STATUS_RANK = {"out": 0, "doubtful": 1, "questionable": 2}


def _injury_table(rows: list[dict], with_game: str | None = None) -> list[dict]:
    table = []
    for r in rows:
        entry = {
            "Team": r.get("team"),
            "Player": r.get("player"),
            "Pos": r.get("position") or "",
            "Status": _STATUS_LABEL.get(r.get("status"), r.get("status") or ""),
            "Starter": bool(r.get("is_starter")),
            "Injury": r.get("injury") or "",
            "Practice": r.get("practice") or "",
        }
        if with_game:
            entry["Game"] = with_game
        table.append(entry)
    return table


_INJURY_CONFIG = {
    "Team": st.column_config.TextColumn("Team", width=70),
    "Player": st.column_config.TextColumn("Player", width="medium"),
    "Pos": st.column_config.TextColumn("Pos", help="Listed position", width=60),
    "Status": st.column_config.TextColumn("Status", help="Official game status on the nflverse report", width=120),
    "Starter": st.column_config.CheckboxColumn("Starter", help="Rank-one on the depth chart or a heavy snap player last week", width=80),
    "Injury": st.column_config.TextColumn("Injury", width="small"),
    "Practice": st.column_config.TextColumn("Practice", help="Most recent practice participation", width="medium"),
}


def render_injuries(c: dict) -> None:
    st.markdown(_hero(c), unsafe_allow_html=True)
    i1, i2 = st.columns(2)
    i1.markdown(_injury_panel(c, "away"), unsafe_allow_html=True)
    i2.markdown(_injury_panel(c, "home"), unsafe_allow_html=True)
    st.write("")

    rows = list(c.get("injuries_away_rows") or []) + list(c.get("injuries_home_rows") or [])
    if not rows:
        st.info("No players listed out, doubtful or questionable for this game.")
        return
    rows.sort(key=lambda r: (_STATUS_RANK.get(r.get("status"), 9), not r.get("is_starter"), r.get("team") or ""))
    st.dataframe(
        _injury_table(rows),
        hide_index=True,
        width="stretch",
        height=_grid_height(len(rows)),
        column_config=_INJURY_CONFIG,
    )
    st.caption("Full nflverse report: out, doubtful and questionable, starters first.")


# --------------------------------------------------------------------------- league pages


def _render_teams_page(season: int, week: int) -> None:
    rows = _league_teams(season, week)
    if not rows:
        st.info("No team-week stats published for this season yet.")
        return

    st.markdown(f"#### Team form through week {max(week - 1, 0)}")
    groups = ["All teams", "AFC", "NFC"]
    scope = st.segmented_control("Conference", groups, default="All teams", label_visibility="collapsed") or "All teams"

    ranks = {r["Team"]: i for i, r in enumerate(rows, start=1)}
    table = []
    for r in rows:
        team = r["Team"]
        if scope != "All teams" and not division(team).startswith(scope):
            continue
        fg = _num(r.get("FG%"))
        table.append(
            {
                "Rk": ranks[team],
                "Team": team,
                "Club": team_name(team),
                "Division": division(team),
                "nfelo": _nan(r.get("nfelo")),
                "Off EPA/g": _nan(r.get("Off EPA/g")),
                "Def EPA/g": _nan(r.get("Def EPA/g")),
                "PF/g": _nan(r.get("PF/g")),
                "PA/g": _nan(r.get("PA/g")),
                "TO": _nan(r.get("TO")),
                "CPOE": _nan(r.get("CPOE")),
                "FG%": nan if fg is None else fg * 100.0,
                "G": _nan(r.get("Games")),
            }
        )
    if not table:
        st.info("No teams match that filter.")
        return

    elos = [t["nfelo"] for t in table if t["nfelo"] == t["nfelo"]]
    lo, hi = (min(elos), max(elos)) if elos else (1300.0, 1700.0)
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=_grid_height(len(table), cap=1240),
        column_config={
            "Rk": st.column_config.NumberColumn("Rk", help="League rank by nfelo rating", format="%.0f", width=50),
            "Team": st.column_config.TextColumn("Team", width=70),
            "Club": st.column_config.TextColumn("Club", width="medium"),
            "Division": st.column_config.TextColumn("Division", width=110),
            "nfelo": st.column_config.ProgressColumn(
                "nfelo", help="Elo-style power rating; about 1500 is league average.",
                format="%.0f", min_value=lo - 15, max_value=hi + 5, width=140,
            ),
            "Off EPA/g": st.column_config.NumberColumn("Off EPA/g", help="Offensive expected points added per game — higher is better.", format="%.1f", width=100),
            "Def EPA/g": st.column_config.NumberColumn("Def EPA/g", help="Expected points allowed per game — lower is better.", format="%.1f", width=100),
            "PF/g": st.column_config.NumberColumn("PF/g", help="Points scored per game", format="%.1f", width=75),
            "PA/g": st.column_config.NumberColumn("PA/g", help="Points allowed per game", format="%.1f", width=75),
            "TO": st.column_config.NumberColumn("TO", help="Season turnover margin: takeaways minus giveaways", format="%+.0f", width=70),
            "CPOE": st.column_config.NumberColumn("CPOE", help="Completion percentage over expected", format="%.1f", width=80),
            "FG%": st.column_config.NumberColumn("FG%", help="Field goal percentage", format="%.0f%%", width=75),
            "G": st.column_config.NumberColumn("G", help="Games played", format="%.0f", width=55),
        },
    )
    st.caption("Season to date, sorted by nfelo. Click any column header to re-sort.")
    _render_glossary()


def _render_league_injuries(cards: list[dict], season: int, week: int) -> None:
    st.markdown(f"#### Week {week} injury report")
    rows = []
    for c in cards:
        game = f"{c['away_team']} @ {c['home_team']}"
        for r in list(c.get("injuries_away_rows") or []) + list(c.get("injuries_home_rows") or []):
            rows.append({**r, "_game": game})
    if not rows:
        st.info("The nflverse injury file has no out, doubtful or questionable listings for this week yet.")
        return

    statuses = ["OUT", "Doubtful", "Questionable"]
    f1, f2, f3 = st.columns([2.2, 2.8, 1.6], vertical_alignment="bottom")
    with f1:
        picked_status = st.segmented_control(
            "Status", statuses, default=statuses, selection_mode="multi", label_visibility="collapsed"
        ) or statuses
    with f2:
        teams = sorted({r.get("team") for r in rows if r.get("team")})
        picked_teams = st.multiselect("Teams", teams, placeholder="All teams", label_visibility="collapsed")
    with f3:
        starters_only = st.toggle("Starters only")

    filtered = [
        r
        for r in rows
        if _STATUS_LABEL.get(r.get("status"), "") in picked_status
        and (not picked_teams or r.get("team") in picked_teams)
        and (not starters_only or r.get("is_starter"))
    ]
    out_n = sum(1 for r in filtered if r.get("status") == "out")
    start_n = sum(1 for r in filtered if r.get("is_starter"))
    st.markdown(
        '<div class="chips">'
        f"<div class='chip'><b>{len(filtered)}</b><span>listed</span></div>"
        f"<div class='chip'><b>{out_n}</b><span>ruled out</span></div>"
        f"<div class='chip'><b>{start_n}</b><span>starters</span></div>"
        "</div>",
        unsafe_allow_html=True,
    )
    if not filtered:
        st.info("No players match those filters.")
        return

    filtered.sort(key=lambda r: (_STATUS_RANK.get(r.get("status"), 9), not r.get("is_starter"), r.get("team") or ""))
    table = []
    for r in filtered:
        entry = _injury_table([r], with_game=r.get("_game"))[0]
        table.append(entry)
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=_grid_height(len(table)),
        column_config={**_INJURY_CONFIG, "Game": st.column_config.TextColumn("Game", width=110)},
    )
    st.caption("Source: nflverse weekly injury reports. Starters come from depth charts and last week's snap counts.")


# --------------------------------------------------------------------------- routing


def _set_view(season: int, week: int, game: str | None = None, view: str | None = None, page: str | None = None) -> None:
    params = {"season": str(season), "week": str(week), "page": page or "week"}
    if game:
        params["game"] = game
    if view:
        params["view"] = view
    st.query_params.clear()
    st.query_params.update(params)


def _back_to_board(season: int, week: int) -> None:
    st.session_state["board_nonce"] = st.session_state.get("board_nonce", 0) + 1
    _set_view(season, week, page="week")
    st.rerun()


_PAGES = {"Week board": "week", "Teams": "teams", "Injuries": "injuries"}
_PAGE_IDS = {v: k for k, v in _PAGES.items()}


def main() -> None:
    qp = st.query_params
    seasons = [2026, 2025, 2024]
    try:
        qp_season = int(qp.get("season", 2026))
    except (TypeError, ValueError):
        qp_season = 2026
    if qp_season not in seasons:
        qp_season = 2026
    qp_page = _PAGE_IDS.get(str(qp.get("page", "week")), "Week board")

    title_col, nav_col, season_col, week_col = st.columns([4.4, 3.0, 1.1, 1.1], vertical_alignment="bottom")
    with title_col:
        st.markdown(
            '<div class="masthead"><div class="rule"></div><h1>NFL Matchup Board</h1></div>'
            '<div class="sub">Context for the pool — not predicted scores.</div>',
            unsafe_allow_html=True,
        )
    with nav_col:
        page = st.segmented_control(
            "Page", list(_PAGES), default=qp_page, label_visibility="collapsed"
        ) or qp_page
    with season_col:
        season = st.selectbox("Season", seasons, index=seasons.index(qp_season))
    try:
        weeks = _weeks(season)
    except Exception as exc:
        st.error(f"Could not load the schedule: {exc}")
        return
    try:
        qp_week = int(qp.get("week", current_week(season)))
    except (TypeError, ValueError):
        qp_week = current_week(season)
    if qp_week not in weeks:
        qp_week = weeks[0] if weeks else 1
    with week_col:
        week = st.selectbox("Week", weeks, index=weeks.index(qp_week))

    page_id = _PAGES[page]
    same_scope = str(season) == str(qp.get("season", "")) and str(week) == str(qp.get("week", ""))
    if not same_scope or page_id != str(qp.get("page", "week") or "week"):
        keep = qp.get("game") if same_scope and page_id == "week" else None
        _set_view(season, week, keep, qp.get("view") if keep else None, page=page_id)
        st.rerun()

    try:
        cards = _cards(season, week)
    except Exception as exc:
        st.error("Could not build this week's board. The upstream data source may be down.")
        st.exception(exc)
        return

    if page_id == "teams":
        _render_teams_page(season, week)
        return
    if not cards:
        st.warning("No games scheduled for that week.")
        return
    if page_id == "injuries":
        _render_league_injuries(cards, season, week)
        return

    selected = {c.get("game_id"): c for c in cards}.get(qp.get("game"))
    if not selected:
        _render_board(cards, season, week)
        return

    back_col, tab_col = st.columns([1.1, 5], vertical_alignment="center")
    if back_col.button("← Week board", width="stretch"):
        _back_to_board(season, week)
    with tab_col:
        section = st.segmented_control(
            "Section",
            ["Matchup", "Injuries"],
            default="Injuries" if qp.get("view") == "injuries" else "Matchup",
            label_visibility="collapsed",
        ) or "Matchup"
    if section == "Injuries":
        render_injuries(selected)
    else:
        render_matchup(selected)


if __name__ == "__main__":
    main()
