"""Weekly NFL matchup board for a family football pool."""

from __future__ import annotations

import html
from math import nan
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlencode

import streamlit as st

from data.matchups import (
    available_weeks,
    build_week_board,
    current_week,
    format_spread,
    league_adj_epa_rows,
    league_st_rows,
    league_team_rows,
)
from data.nfelo import elo_snapshot_coverage
from data.theme import THEME_IDS, apply as apply_theme, from_query as theme_from_query
from data.personnel import injury_status_counts
from data.schedules import format_kickoff_pt
from data.teamref import display_color, division, logo_url, pair_colors, team_name
from data.wide_stats import league_nflverse_rows, league_ngs_rows

_ICON = Path(__file__).with_name("assets") / "nfl-board.png"
st.set_page_config(
    page_title="NFL Matchup Board",
    page_icon=str(_ICON) if _ICON.exists() else "🏈",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={"About": "NFL Matchup Board - weekly pool comparison. Built with Streamlit."},
)

st.markdown(
    """
    <style>
      [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none; }
      .block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1500px; }

      .masthead { display: flex; align-items: baseline; gap: 0.6rem; }
      .masthead h1 {
        font-size: 1.5rem; font-weight: 750; letter-spacing: -0.01em;
        margin: 0; padding: 0; line-height: 1.1;
        color: var(--board-text, #e6edf3);
      }
      .masthead .sub { color: var(--board-muted, #8b98a5); font-size: 0.82rem; margin: 0.15rem 0 0 0.95rem; }
      .masthead .sub a {
        color: var(--board-muted, #8b98a5); text-decoration: none;
        border-bottom: 1px dotted var(--board-dot, #39444f);
      }
      .masthead .sub a:hover { color: var(--board-text, #e6edf3); border-bottom-color: var(--board-accent, #d8a94b); }

      .chips { display: flex; flex-wrap: wrap; gap: 0.45rem; margin: 0.15rem 0 0.9rem; }
      .chip {
        display: inline-flex; align-items: baseline; gap: 0.4rem;
        padding: 0.3rem 0.7rem; border-radius: 999px;
        background: var(--board-chip, #141b23); border: 1px solid var(--board-border, #242e3a); font-size: 0.82rem;
      }
      .chip b { color: var(--board-text, #e6edf3); font-weight: 650; }
      .chip span { color: var(--board-muted, #8b98a5); }

      .panel {
        border: 1px solid var(--board-border, #242e3a); border-radius: 0.7rem;
        background: var(--board-panel, #121820); padding: 0.85rem 1rem; height: 100%;
      }
      .panel-h {
        font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.09em;
        color: var(--board-muted, #8b98a5); font-weight: 700; margin-bottom: 0.7rem;
      }
      .panel ul { margin: 0; padding-left: 1.05rem; }
      .panel li { margin-bottom: 0.3rem; font-size: 0.9rem; line-height: 1.45; }
      .panel li:last-child { margin-bottom: 0; }
      .panel .foot { color: var(--board-muted, #8b98a5); font-size: 0.78rem; margin-top: 0.7rem; line-height: 1.4; }

      .hero {
        display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 1rem;
        border: 1px solid var(--board-border, #242e3a); border-radius: 0.8rem; background: var(--board-panel, #121820);
        padding: 0.9rem 1.2rem; margin-bottom: 0.9rem;
      }
      .hero-team { display: flex; align-items: center; gap: 0.75rem; min-width: 0; }
      .hero-team.home { flex-direction: row-reverse; text-align: right; }
      .hero-team img { width: 46px; height: 46px; object-fit: contain; }
      .hero-abbr { font-size: 1.35rem; font-weight: 750; line-height: 1.1; }
      .hero-name { color: var(--board-muted, #8b98a5); font-size: 0.8rem; white-space: nowrap; }
      .hero-mid { text-align: center; }
      .hero-score { font-size: 1.5rem; font-weight: 700; font-variant-numeric: tabular-nums; }
      .hero-at { font-size: 0.78rem; letter-spacing: 0.16em; color: var(--board-hero-at, #6f7d8c); text-transform: uppercase; }
      .hero-meta { color: var(--board-muted, #8b98a5); font-size: 0.8rem; margin-top: 0.2rem; white-space: nowrap; }

      .cmp { display: flex; flex-direction: column; gap: 0.42rem; }
      .cmp-row {
        display: grid; grid-template-columns: 3.4rem 1fr 8.6rem 1fr 3.4rem;
        align-items: center; gap: 0.4rem;
      }
      .cmp-num { font-size: 0.85rem; font-variant-numeric: tabular-nums; color: var(--board-cmp-num, #93a2b1); }
      .cmp-num.l { text-align: right; }
      .cmp-num.r { text-align: left; }
      .cmp-num.best { color: var(--board-text, #e6edf3); font-weight: 700; }
      .cmp-track { height: 0.4rem; border-radius: 999px; background: var(--board-track, #1a222c); display: flex; }
      .cmp-track.l { justify-content: flex-end; }
      .cmp-fill { height: 100%; border-radius: 999px; }
      .cmp-label {
        text-align: center; font-size: 0.77rem; color: var(--board-muted, #8b98a5);
        cursor: help; border-bottom: 1px dotted var(--board-dot, #39444f); justify-self: center;
      }

      .form-line { font-size: 0.88rem; line-height: 1.6; }
      .form-line b { font-variant-numeric: tabular-nums; }
      .split { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
      .mobile-board { display: none; }
      .mobile-sources { display: none; }
      .mobile-sources summary { min-height: 44px; align-content: center; cursor: pointer; color: var(--board-muted); }
      .mobile-sources a { display: inline-flex; align-items: center; min-height: 44px; }
      .game-card {
        min-width: 0; padding: 1rem; border: 1px solid var(--board-border);
        border-radius: 0.7rem; background: var(--board-panel);
      }
      .game-card h3 { font-size: 1.2rem; margin: 0; padding: 0; }
      .game-card .kickoff { color: var(--board-muted); font-size: 0.85rem; margin: 0 0 0.5rem; }
      .game-card dl { display: grid; grid-template-columns: 1fr 1fr; gap: 0.65rem; margin: 0.8rem 0; }
      .game-card dl > div { min-width: 0; }
      .game-card dt { color: var(--board-muted); font-size: 0.8rem; }
      .game-card dd { margin: 0; font-weight: 650; overflow-wrap: anywhere; }
      .game-card .conditions { font-size: 0.85rem; overflow-wrap: anywhere; }
      .game-card > a {
        display: flex; align-items: center; justify-content: center; min-height: 44px;
        border: 1px solid var(--board-accent); border-radius: 0.4rem;
        color: var(--board-text); text-decoration: none; font-weight: 650;
      }
      .game-card > a:hover { background: var(--board-chip); }
      .game-card > a:focus-visible { outline: 3px solid var(--board-accent); outline-offset: 3px; }
      /* Detail and reference surfaces share the board's existing palette and spacing. */
      .mobile-injury-cards { display: none; }
      [class*="st-key-reference_"], .st-key-game_injury_table, .st-key-game_glossary {
        min-width: 0; max-width: 100%; overflow-x: auto;
      }
      [class*="st-key-reference_"] [data-testid="stDataFrame"],
      [class*="st-key-reference_"] [data-testid="stDataFrameResizable"],
      .st-key-game_injury_table [data-testid="stDataFrame"],
      .st-key-game_injury_table [data-testid="stDataFrameResizable"],
      .st-key-game_glossary [data-testid="stMarkdownContainer"] {
        min-width: 0; max-width: 100%; overflow-x: auto; box-sizing: border-box;
      }
      .st-key-game_glossary table { min-width: 40rem; }
      [class*="st-key-reference_chart_"] { overflow-x: auto; }
      [class*="st-key-reference_chart_"] [data-testid="stVegaLiteChart"],
      [class*="st-key-reference_chart_"] [data-testid="stArrowVegaLiteChart"] {
        min-width: 0; max-width: 100%; box-sizing: border-box;
      }
      .st-key-reference_chart_adj_epa_mobile,
      .st-key-reference_chart_team_epa_mobile { display: none; }
      .st-key-reference_chart_adj_epa_desktop,
      .st-key-reference_chart_team_epa_desktop { display: block; }
      .st-key-game_navigation button { min-height: 44px; }
      @media (max-width: 820px) {
        [data-testid="stButtonGroup"] { min-width: 0; max-width: 100%; }
        [data-testid="stButtonGroup"] > div,
        [data-testid="stButtonGroup"] [role="group"],
        [data-testid="stButtonGroup"] [role="radiogroup"],
        [data-testid="stButtonGroup"] [data-baseweb="button-group"] {
          flex-wrap: wrap; max-width: 100%;
        }
        [data-testid="stButtonGroup"] button { min-height: 44px; white-space: normal; }
        .st-key-game_metrics [data-testid="stHorizontalBlock"] {
          display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
        }
        .st-key-game_metrics [data-testid="stColumn"] {
          min-width: 0 !important; width: 100% !important;
        }
        .st-key-game_panels [data-testid="stHorizontalBlock"],
        .st-key-game_availability [data-testid="stHorizontalBlock"],
        [class*="st-key-game_comparison_"] [data-testid="stHorizontalBlock"] {
          flex-direction: column;
        }
        .st-key-game_panels [data-testid="stColumn"],
        .st-key-game_availability [data-testid="stColumn"],
        [class*="st-key-game_comparison_"] [data-testid="stColumn"] {
          min-width: 0 !important; width: 100% !important; flex: 1 1 auto !important;
        }
        .hero-name, .hero-meta { white-space: normal; overflow-wrap: anywhere; }
        .panel { min-width: 0; overflow-wrap: anywhere; }
        [class*="st-key-reference_chart_"] [data-testid="stVegaLiteChart"],
        [class*="st-key-reference_chart_"] [data-testid="stArrowVegaLiteChart"] { min-height: 20rem; }
        .st-key-league_injury_filters [data-baseweb="select"],
        .st-key-league_injury_filters [data-testid="stToggle"] label { min-height: 44px; }
      }
      @media (max-width: 480px) {
        .st-key-reference_chart_adj_epa_desktop,
        .st-key-reference_chart_team_epa_desktop { display: none; }
        .st-key-reference_chart_adj_epa_mobile,
        .st-key-reference_chart_team_epa_mobile { display: block; }
        .st-key-reference_chart_adj_epa_mobile [data-testid="stVegaLiteChart"],
        .st-key-reference_chart_adj_epa_mobile [data-testid="stArrowVegaLiteChart"],
        .st-key-reference_chart_team_epa_mobile [data-testid="stVegaLiteChart"],
        .st-key-reference_chart_team_epa_mobile [data-testid="stArrowVegaLiteChart"] { min-height: 0; }
        .st-key-game_metrics [data-testid="stHorizontalBlock"] { grid-template-columns: minmax(0, 1fr); }
        .st-key-game_navigation [data-testid="stHorizontalBlock"],
        .st-key-league_injury_filters [data-testid="stHorizontalBlock"] { flex-direction: column; }
        .st-key-game_navigation [data-testid="stColumn"],
        .st-key-league_injury_filters [data-testid="stColumn"] {
          min-width: 0 !important; width: 100% !important; flex: 1 1 auto !important;
        }
        .st-key-game_injury_table, .st-key-reference_league_injury_table { display: none; }
        .mobile-injury-cards { display: grid; gap: 0.75rem; }
        .injury-card {
          min-width: 0; padding: 1rem; border: 1px solid var(--board-border);
          border-radius: 0.7rem; background: var(--board-panel);
        }
        .injury-card h3 { margin: 0; padding: 0; font-size: 1.2rem; overflow-wrap: anywhere; }
        .injury-card dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; margin: 0.75rem 0 0; }
        .injury-card dl > div { min-width: 0; }
        .injury-card .injury-detail { grid-column: 1 / -1; }
        .injury-card dt { color: var(--board-muted); font-size: 0.8rem; }
        .injury-card dd { margin: 0; color: var(--board-text); overflow-wrap: anywhere; }
      }
      @media (max-width: 820px) {
        .mobile-board { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 0.8rem; }
        .desktop-sources { display: none; }
        .mobile-sources { display: block; font-size: 0.8rem; }
        .st-key-site_header [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: 0.5rem; }
        .st-key-site_header [data-testid="stColumn"] { flex: 1 1 0 !important; min-width: 0 !important; width: auto !important; }
        .st-key-site_header [data-testid="stColumn"]:first-child { flex: 1 1 100% !important; }
        .st-key-site_header [role="combobox"] { min-height: 44px; }
        .st-key-board_table { display: none; }
        [role="tablist"] { flex-wrap: wrap; gap: 0.25rem; height: auto; }
        [role="tab"] { min-height: 44px; padding: 0.4rem 0.65rem; }
        [role="tab"][aria-selected="true"] {
          background: var(--board-chip); border-radius: 0.35rem;
          box-shadow: inset 0 -3px var(--board-accent);
        }
        [role="tab"] > .react-aria-SelectionIndicator { display: none; }
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
        return "-"
    try:
        num = float(val)
    except (TypeError, ValueError):
        return "-"
    body = f"{num:+.{digits}f}" if signed else f"{num:.{digits}f}"
    return body + suffix


def _pct(val):
    if val is None:
        return "-"
    try:
        num = float(val)
    except (TypeError, ValueError):
        return "-"
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


def _grid_height(rows: int, cap: int = 760) -> int | str:
    """Fit the grid to its rows, scrolling internally only once it would run long."""
    return "content" if 35 * max(rows, 1) + 43 <= cap else cap


def _nan(val):
    """Numeric or NaN, so number columns render a blank instead of the word None."""
    num = _num(val)
    return nan if num is None else num


# --------------------------------------------------------------------------- data


@st.cache_data(ttl=3600, show_spinner="Loading nflverse, nfelo and weather data…")
def _cards(season: int, week: int, _ver: int = 6):
    return build_week_board(season, week)


@st.cache_data(ttl=3600)
def _weeks(season: int):
    return available_weeks(season)


@st.cache_data(ttl=3600, show_spinner="Loading team form…")
def _league_teams(season: int, week: int, _ver: int = 2):
    return league_team_rows(season, week)


@st.cache_data(ttl=3600, show_spinner="Adjusting EPA for schedule…")
def _adj_epa(season: int, week: int, _ver: int = 7):
    return league_adj_epa_rows(season, week)


@st.cache_data(ttl=3600, show_spinner="Loading special teams…")
def _st_teams(season: int, week: int, _ver: int = 3):
    return league_st_rows(season, week)


@st.cache_data(ttl=3600, show_spinner="Loading nflverse team table…")
def _nflverse_wide(season: int, week: int, _ver: int = 3):
    return league_nflverse_rows(season, week)


@st.cache_data(ttl=3600, show_spinner="Loading Next Gen Stats…")
def _ngs_wide(season: int, week: int, _ver: int = 1):
    return league_ngs_rows(season, week)


def _kickoff_label(c: dict) -> str:
    when = (c.get("kickoff_pt") or "").strip()
    return when or format_kickoff_pt(c.get("gameday"), c.get("gametime")) or "-"


def _conditions_text(c: dict) -> str:
    """Concise kickoff conditions for the board."""
    if c.get("venue") != "outdoor":
        return "Indoor"
    bits = []
    temp = c.get("wx_temp_f") if c.get("wx_temp_f") is not None else c.get("temp")
    wind = c.get("wx_wind_mph") if c.get("wx_wind_mph") is not None else c.get("wind")
    if temp is not None:
        bits.append(f"{float(temp):.0f}°F")
    if wind is not None:
        bits.append(f"{float(wind):.0f} mph wind")
    if c.get("wx_rain_in"):
        bits.append(f"{float(c['wx_rain_in']):.2f}\" rain")
    if c.get("wx_snow_in"):
        bits.append(f"{float(c['wx_snow_in']):.2f}\" snow")
    return " · ".join(bits) or "Weather unavailable"


def _status_counts(c: dict, side: str) -> tuple[int, int]:
    """(out or doubtful, questionable) for one side of a game."""
    counts = injury_status_counts(c.get(f"injuries_{side}_rows") or [])
    return counts["out"] + counts["doubtful"], counts["questionable"]


def _score_text(c: dict) -> str:
    if c.get("away_score") is None or c.get("home_score") is None:
        return ""
    return f"{int(c['away_score'])}-{int(c['home_score'])}"


# --------------------------------------------------------------------------- week board


def _board_rows(cards: list[dict], show_score: bool, adj_net: dict[str, float] | None = None) -> list[dict]:
    adj_net = adj_net or {}
    rows = []
    base = ["Kickoff", "Matchup", "Spread", "Home win%", "Total", "Conditions", "Away Adj Net", "Home Adj Net"]
    if show_score:
        base = ["Kickoff", "Matchup", "Score", "Spread", "Home win%", "Total", "Conditions", "Away Adj Net", "Home Adj Net"]
    for c in cards:
        home, away = c["home_team"], c["away_team"]
        row = {
            "Kickoff": _kickoff_label(c),
            "Matchup": f"{away} @ {home}",
            "Spread": format_spread(c.get("spread_line"), home, away),
            "Home win%": _pct_value(c.get("home_win_pct")),
            "Total": _num(c.get("total_line")),
            "Conditions": _conditions_text(c),
            "Away Adj Net": _nan(adj_net.get(away)),
            "Home Adj Net": _nan(adj_net.get(home)),
        }
        if show_score:
            row["Score"] = _score_text(c) or "-"
        rows.append({k: row[k] for k in base})
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


def _mobile_board(cards: list[dict], season: int, week: int, adj_net: dict[str, float]) -> str:
    """Semantic phone cards using the same values and deep links as the grid."""
    rendered = []
    for c in cards:
        away, home = c["away_team"], c["home_team"]
        params = {"season": season, "week": week, "game": c["game_id"]}
        theme = theme_from_query()
        if theme != "default":
            params["theme"] = theme
        href = html.escape("?" + urlencode(params), quote=True)
        matchup = html.escape(f"{away} at {home}")
        fields = [
            ("Spread", format_spread(c.get("spread_line"), home, away)),
            (f"{home} win probability", _pct(c.get("home_win_pct"))),
            ("Total points", _fmt(c.get("total_line"))),
            ("Score (away–home)", _score_text(c) or "Not available"),
            (f"{away} adjusted net", _fmt(adj_net.get(away), signed=True)),
            (f"{home} adjusted net", _fmt(adj_net.get(home), signed=True)),
        ]
        stats = "".join(
            f"<div><dt>{html.escape(label)}</dt><dd>{html.escape(str(value))}</dd></div>"
            for label, value in fields
        )
        rendered.append(
            '<article class="game-card">'
            f'<p class="kickoff">{html.escape(_kickoff_label(c))} PT</p>'
            f"<h3>{matchup}</h3><dl>{stats}</dl>"
            f'<p class="conditions">Conditions: {html.escape(_conditions_text(c))}</p>'
            f'<a href="{href}" target="_self" aria-label="View {matchup} breakdown">View breakdown →</a>'
            "</article>"
        )
    return '<div class="mobile-board">' + "".join(rendered) + "</div>"


def _render_board(cards: list[dict], season: int, week: int) -> None:
    show_score = any(c.get("home_score") is not None and c.get("away_score") is not None for c in cards)
    config = {
        "Kickoff": st.column_config.TextColumn("Kickoff", help="Kickoff in Pacific time", width=110),
        "Matchup": st.column_config.TextColumn("Matchup", help="Away team at home team", width=120),
        "Score": st.column_config.TextColumn("Score", help="Final score, away-home", width=80),
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
        "Away Adj Net": st.column_config.NumberColumn(
            "Away Adj Net",
            help="Opponent-adjusted net EPA/g for the away team (Adj Off minus Adj Def). Higher is better.",
            format="%+.1f",
            width=110,
        ),
        "Home Adj Net": st.column_config.NumberColumn(
            "Home Adj Net",
            help="Opponent-adjusted net EPA/g for the home team (Adj Off minus Adj Def). Higher is better.",
            format="%+.1f",
            width=110,
        ),
    }

    nonce = st.session_state.get("board_nonce", 0)
    adj_net = {r["team"]: r.get("adj_net_epa_pg") for r in _adj_epa(season, week)}
    st.markdown(_mobile_board(cards, season, week, adj_net), unsafe_allow_html=True)
    with st.container(key="board_table"):
        st.caption(
            "Tick the box beside a game to open its full breakdown. "
            "Click a column header to sort, and hover a header to see what the number means."
        )
        event = st.dataframe(
            _board_rows(cards, show_score, adj_net),
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
            _set_view(season, week, game_id)
            st.rerun()


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
            Metric("Pressures generated", "u_h_press_gen", "u_a_press_gen", 0, True, "Pass rush pressures the defensive front has produced (PFR)"),
            Metric("Pressures allowed", "u_h_press_all", "u_a_press_all", 0, False, "Pressures the offensive line has given up (PFR)"),
            Metric("Pressure rate allowed", "u_press_pct_home", "u_press_pct_away", 1, False, "Team pressure rate allowed, weighted by quarterback passing volume across players and weeks (PFR)", "%"),
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
            Metric("Net punt avg", "u_punt_net_home", "u_punt_net_away", 1, True, "Net yards per punt: gross distance minus return yards", " yds"),
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
    rows = "".join(
        _cmp_row(m, card, colors) for m in metrics if _has_values([m], card)
    )
    foot = f'<div class="foot">{html.escape(footer)}</div>' if footer else ""
    return f'<div class="panel"><div class="panel-h">{html.escape(title)}</div><div class="cmp">{rows}</div>{foot}</div>'

def _render_glossary() -> None:
    """Show the compact metric key used by both matchup-page branches."""
    with st.container(key="game_glossary").expander("Metric glossary", expanded=False):
        rows = [
            "| Metric | Meaning | Units | Direction | Source |",
            "| --- | --- | --- | --- | --- |",
        ]
        for group, metrics in _GROUPS:
            for metric in metrics:
                if metric.suffix:
                    units = metric.suffix.strip()
                elif "/g" in metric.label:
                    units = "per game"
                elif "rate" in metric.label.lower() or "%" in metric.label:
                    units = "rate"
                else:
                    units = "value"
                direction = (
                    "Higher is better"
                    if metric.higher_better is True
                    else "Lower is better"
                    if metric.higher_better is False
                    else "Context only"
                )
                source = (
                    "Next Gen Stats"
                    if "Next Gen Stats" in metric.help
                    else "PFR"
                    if "PFR" in metric.help
                    else "nflverse"
                )
                rows.append(
                    f"| **{html.escape(metric.label)}** ({html.escape(group)}) | "
                    f"{html.escape(metric.help)} | {html.escape(units)} | "
                    f"{direction} | {source} |"
                )
        st.markdown(
            "Sources, units, and comparison direction for every board metric. "
            "Brighter bars indicate the better number when direction is defined.\n\n"
            + "\n".join(rows)
        )




# --------------------------------------------------------------------------- game page


def _hero(c: dict) -> str:
    away, home = c["away_team"], c["home_team"]
    score = _score_text(c)
    if score:
        a_pts, h_pts = int(c["away_score"]), int(c["home_score"])
        a_style = "" if a_pts >= h_pts else "color:#8b98a5"
        h_style = "" if h_pts >= a_pts else "color:#8b98a5"
        middle = f'<div class="hero-score"><span style="{a_style}">{a_pts}</span> - <span style="{h_style}">{h_pts}</span></div>'
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
            "No large statistical gaps - this one grades out close on paper."
            if _has_unit_data(c)
            else "No prior completed games, so there is nothing to compare yet."
        )
        items = [f"<li>{fallback}</li>"]
    return f'<div class="panel"><div class="panel-h">Why this game stands out</div><ul>{"".join(items)}</ul></div>'


def _injury_panel(c: dict, side: str) -> str:
    team = c[f"{side}_team"]
    out, quest = _status_counts(c, side)
    counts = injury_status_counts(c.get(f"injuries_{side}_rows") or [])
    practice_n = counts.get("dnp", 0) + counts.get("limited", 0)
    names = c.get(f"injuries_out_{side}") or ""
    dnp_starters = [
        r["player"].split()[-1]
        for r in (c.get(f"injuries_{side}_rows") or [])
        if r.get("is_starter") and r.get("status") == "dnp"
    ]
    if names:
        detail = f"Starters out: {names}"
    elif dnp_starters:
        detail = "Starters DNP in practice: " + " · ".join(dnp_starters)
    else:
        detail = "No listed starters out. Mid-week reports use practice status until Friday designations."
    chips = (
        f"<div class='chip'><b>{out}</b><span>out or doubtful</span></div>"
        f"<div class='chip'><b>{quest}</b><span>questionable</span></div>"
        f"<div class='chip'><b>{practice_n}</b><span>DNP or limited</span></div>"
    )
    return (
        f'<div class="panel"><div class="panel-h">{html.escape(team)} availability</div>'
        f'<div class="chips" style="margin:0">{chips}</div>'
        f"<div class='foot'>{html.escape(detail)}</div></div>"
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
        '<div class="panel"><div class="panel-h">Recent form - last 3 games</div>'
        f'<div class="split">{"".join(sides)}</div></div>'
    )


def render_matchup(c: dict) -> None:
    away, home = c["away_team"], c["home_team"]
    st.markdown(_hero(c), unsafe_allow_html=True)

    m1, m2, m3, m4 = st.container(key="game_metrics").columns(4)
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

    left, right = st.container(key="game_panels").columns([1.35, 1])
    with left:
        st.markdown(_standouts_panel(c), unsafe_allow_html=True)
    with right:
        i1, i2 = st.container(key="game_matchup_availability").columns(2)
        i1.markdown(_injury_panel(c, "away"), unsafe_allow_html=True)
        i2.markdown(_injury_panel(c, "home"), unsafe_allow_html=True)

    colors = pair_colors(away, home)
    if not _has_unit_data(c):
        st.info("No prior completed games, so season statistics are not available yet; only the market line, weather and injuries are shown.")
        _render_glossary()
        return

    st.markdown(
        f'<div class="chips" style="margin-top:1rem"><div class="chip"><span>Bars compare</span>'
        f'<b style="color:{colors[0]}">{html.escape(away)}</b><span>left vs</span>'
        f'<b style="color:{colors[1]}">{html.escape(home)}</b><span>right - the brighter bar is the better number</span></div></div>',
        unsafe_allow_html=True,
    )

    rush_bits = [
        f"{team}: {c.get(key)}"
        for team, key in ((away, "u_top_rushers_away"), (home, "u_top_rushers_home"))
        if c.get(key)
    ]
    panels = []
    for title, metrics in _GROUPS:
        footer = f"Top pressure producers - {' · '.join(rush_bits)}" if title == "Trenches" and rush_bits else ""
        panels.append(_cmp_panel(title, metrics, c, colors, footer))
    panels.append(_form_panel(c))
    panels = [p for p in panels if p]

    for index in range(0, len(panels), 2):
        cols = st.container(key=f"game_comparison_{index}").columns(2)
        cols[0].markdown(panels[index], unsafe_allow_html=True)
        if index + 1 < len(panels):
            cols[1].markdown(panels[index + 1], unsafe_allow_html=True)
        st.write("")

    _render_glossary()


_STATUS_LABEL = {
    "out": "OUT",
    "doubtful": "Doubtful",
    "dnp": "DNP",
    "limited": "Limited",
    "questionable": "Questionable",
}
_ROSTER_LABEL = {
    "ir": "IR",
    "pup": "PUP",
    "nfi": "NFI",
    "suspended": "Suspended",
}
_STATUS_RANK = {
    "out": 0,
    "doubtful": 1,
    "dnp": 2,
    "limited": 3,
    "questionable": 4,
    "ir": 5,
    "pup": 6,
    "nfi": 7,
    "suspended": 8,
}


def _injury_source_note(rows: list[dict], week: int) -> str | None:
    source_weeks = sorted(
        {
            int(row["last_reported_week"])
            for row in rows
            if row.get("status") and row.get("last_reported_week") is not None
        }
    )
    if not source_weeks:
        return (
            "No weekly game/practice report is available yet. "
            "Roster-list players come from the latest weekly roster snapshot."
        )
    latest = source_weeks[-1]
    if latest < week:
        return (
            f"Week {week} reports are not posted yet. Showing each team's latest available "
            f"game/practice report (latest source: Week {latest})."
        )
    if source_weeks[0] < week:
        return (
            f"Week {week} reports are still arriving. Teams without a Week {week} filing "
            "use their latest available game/practice report."
        )
    return None


def _injury_table(rows: list[dict], with_game: str | None = None) -> list[dict]:
    table = []
    for r in rows:
        first_week = r.get("first_reported_week")
        last_week = r.get("last_reported_week")
        entry = {
            "Team": r.get("team"),
            "Player": r.get("player"),
            "Pos": r.get("position") or "",
            "Status": _STATUS_LABEL.get(r.get("status"), r.get("status") or ""),
            "Roster": _ROSTER_LABEL.get(r.get("roster_status"), r.get("roster_status") or ""),
            "Starter": bool(r.get("is_starter")),
            "Injury": r.get("injury") or "",
            "Practice": r.get("practice") or "",
            "Since": f"Wk {first_week}" if first_week is not None else "",
            "Last report": (
                f"Wk {last_week} · carried"
                if last_week is not None and r.get("is_carried")
                else f"Wk {last_week}" if last_week is not None else ""
            ),
        }
        if with_game:
            entry["Game"] = with_game
        table.append(entry)
    return table


def _mobile_injury_cards(rows: list[dict] | None, with_game: bool = False) -> str:
    """Render the full injury report as compact, phone-only semantic cards."""
    if not rows:
        return ""
    cards = []
    for row in rows:
        entry = _injury_table([row])[0]
        if with_game:
            entry["Game"] = row.get("game") or ""
        fields = []
        for label, value in entry.items():
            if label == "Starter":
                value = "Yes" if value else "No"
            detail = ' class="injury-detail"' if label in ("Player", "Injury", "Practice", "Game") else ""
            fields.append(
                f"<div{detail}><dt>{label}</dt>"
                f"<dd>{html.escape(str(value)) if value is not None and value != '' else '—'}</dd></div>"
            )
        cards.append(
            '<article class="injury-card" aria-label="Player injury report">'
            f'<h3>{html.escape(str(entry["Player"] or "Player not listed"))}</h3>'
            f'<dl>{"".join(fields)}</dl></article>'
        )
    return '<div class="mobile-injury-cards">' + "".join(cards) + "</div>"


_INJURY_CONFIG = {
    "Team": st.column_config.TextColumn("Team", width=70),
    "Player": st.column_config.TextColumn("Player", width="medium"),
    "Pos": st.column_config.TextColumn("Pos", help="Listed position", width=60),
    "Status": st.column_config.TextColumn("Status", help="Official game status, or DNP / limited from practice when game designations are not posted yet", width=120),
    "Roster": st.column_config.TextColumn("Roster", help="Weekly roster designation: IR, PUP, NFI, or suspended", width=90),
    "Starter": st.column_config.CheckboxColumn("Starter", help="Rank-one on the depth chart or a heavy snap player last week", width=80),
    "Injury": st.column_config.TextColumn("Injury", width="small"),
    "Practice": st.column_config.TextColumn("Practice", help="Most recent practice participation", width="medium"),
    "Since": st.column_config.TextColumn("Since", help="First week of the current reported status", width=75),
    "Last report": st.column_config.TextColumn("Last report", help="Latest source week; persistent IR/PUP/NFI/suspension states may be carried forward", width=125),
}


def render_injuries(c: dict) -> None:
    st.markdown(_hero(c), unsafe_allow_html=True)
    i1, i2 = st.container(key="game_availability").columns(2)
    i1.markdown(_injury_panel(c, "away"), unsafe_allow_html=True)
    i2.markdown(_injury_panel(c, "home"), unsafe_allow_html=True)
    st.write("")

    rows = list(c.get("injuries_away_rows") or []) + list(c.get("injuries_home_rows") or [])
    if not rows:
        st.info("No injury or practice-report listings for this game yet.")
        return
    source_note = _injury_source_note(rows, int(c.get("week") or 0))
    if source_note:
        st.info(source_note)
    rows.sort(
        key=lambda r: (
            _STATUS_RANK.get(r.get("status") or r.get("roster_status"), 9),
            not r.get("is_starter"),
            r.get("team") or "",
        )
    )
    st.markdown(_mobile_injury_cards(rows), unsafe_allow_html=True)
    st.container(key="game_injury_table").dataframe(
        _injury_table(rows),
        hide_index=True,
        width="stretch",
        height=_grid_height(len(rows)),
        column_config=_INJURY_CONFIG,
    )
    st.caption(
        "Weekly game and practice designations come from nflverse injury reports. "
        "IR / PUP / NFI / suspension come from the selected week's nflverse roster snapshot."
    )


# --------------------------------------------------------------------------- league pages


_CONFERENCES = ["All teams", "AFC", "NFC"]


def _league_table(season: int, week: int, scope: str) -> list[dict]:
    """One row per team carrying every league-level number the tabs can show."""
    table = []
    for rank, r in enumerate(_league_teams(season, week), start=1):
        team = r["Team"]
        if scope != "All teams" and not division(team).startswith(scope):
            continue
        off, allowed = _num(r.get("Off EPA/g")), _num(r.get("Def EPA/g"))
        table.append(
            {
                "Rk": rank,
                "Team": team,
                "Club": team_name(team),
                "Division": division(team),
                "nfelo": _nan(r.get("nfelo")),
                "Pts vs avg": _nan(r.get("Pts vs avg")),
                "Off EPA/g": _nan(off),
                "Def EPA/g": _nan(allowed),
                "Net EPA/g": nan if off is None or allowed is None else off - allowed,
                "PF/g": _nan(r.get("PF/g")),
                "PA/g": _nan(r.get("PA/g")),
                "TO": _nan(r.get("TO")),
                "CPOE": _nan(r.get("CPOE")),
                "G": _nan(r.get("Games")),
            }
        )
    return table


def _team_config(elos: list[float]) -> dict:
    lo, hi = (min(elos), max(elos)) if elos else (1300.0, 1700.0)
    return {
        "Rk": st.column_config.NumberColumn("Rk", help="League rank by nfelo rating", format="%.0f", width=50),
        "Team": st.column_config.TextColumn("Team", width=70),
        "Club": st.column_config.TextColumn("Club", width="medium"),
        "Division": st.column_config.TextColumn("Division", width=110),
        "nfelo": st.column_config.ProgressColumn(
            "nfelo", help="Elo-style power rating; about 1500 is league average.",
            format="%.0f", min_value=lo - 15, max_value=hi + 5, width=140,
        ),
        "Pts vs avg": st.column_config.NumberColumn(
            "Pts vs avg",
            help="Points nfelo expects this team to beat an average opponent by on a neutral field.",
            format="%+.1f", width=105,
        ),
        "Off EPA/g": st.column_config.NumberColumn("Off EPA/g", help="Offensive expected points added per game - higher is better.", format="%.1f", width=100),
        "Def EPA/g": st.column_config.NumberColumn("Def EPA/g", help="Expected points allowed per game - lower is better.", format="%.1f", width=100),
        "Net EPA/g": st.column_config.NumberColumn("Net EPA/g", help="Offensive EPA per game minus defensive EPA allowed per game - overall efficiency.", format="%+.1f", width=100),
        "PF/g": st.column_config.NumberColumn("PF/g", help="Points scored per game", format="%.1f", width=75),
        "PA/g": st.column_config.NumberColumn("PA/g", help="Points allowed per game", format="%.1f", width=75),
        "TO": st.column_config.NumberColumn("TO", help="Season turnover margin: takeaways minus giveaways", format="%+.0f", width=70),
        "CPOE": st.column_config.NumberColumn("CPOE", help="Completion percentage over expected", format="%.1f", width=80),
        "G": st.column_config.NumberColumn("G", help="Games played", format="%.0f", width=55),
    }


def _render_team_grid(
    season: int, week: int, *, columns: list[str], key: str, sort_by: str | None,
    caption: str, show_epa_chart: bool = False,
) -> None:
    if not _league_teams(season, week):
        st.info("No prior completed games for this season yet.")
        return
    st.markdown(f"#### Season to date, through week {max(week - 1, 0)}")
    scope = st.segmented_control(
        "Conference", _CONFERENCES, default="All teams", label_visibility="collapsed", key=key
    ) or "All teams"
    table = _league_table(season, week, scope)
    if not table:
        st.info("No teams match that filter.")
        return
    if sort_by:
        table.sort(key=lambda r: -r[sort_by] if r[sort_by] == r[sort_by] else float("inf"))
    config = _team_config([t["nfelo"] for t in table if t["nfelo"] == t["nfelo"]])
    if show_epa_chart:
        _render_regular_epa_chart(table)
    st.container(key=f"reference_{key}_table").dataframe(
        [{c: t[c] for c in columns} for t in table],
        hide_index=True,
        width="stretch",
        height=_grid_height(len(table), cap=1240),
        column_config={c: config[c] for c in columns},
    )
    st.caption(caption)


def _render_power_ratings(season: int, week: int) -> None:
    source_min, source_max = elo_snapshot_coverage(season)
    if source_min is None:
        coverage = "no published source weeks"
    elif source_min == source_max:
        coverage = f"published source week {source_min}"
    else:
        coverage = f"published source weeks {source_min}–{source_max}"
    _render_team_grid(
        season,
        week,
        columns=["Rk", "Team", "Club", "Division", "nfelo", "Pts vs avg", "PF/g", "PA/g", "TO", "G"],
        key="scope_power",
        sort_by=None,
        caption=(
            f"Latest published nfelo current snapshot ({coverage}); not a strict historical or "
            "pregame rating. Strongest first; click any column header to re-sort."
        ),
    )


def _render_team_stats(season: int, week: int) -> None:
    _render_team_grid(
        season,
        week,
        columns=["Team", "Club", "Division", "Off EPA/g", "Def EPA/g", "Net EPA/g", "PF/g", "PA/g", "CPOE", "TO", "G"],
        key="scope_stats",
        sort_by="Net EPA/g",
        show_epa_chart=True,
        caption="nflverse play-by-play efficiency, best net EPA first. Click any column header to re-sort.",
    )



def _logo_plot(rows: list[dict], x: str, y: str, extras: list[str] | None = None) -> list[dict]:
    extras = extras or []
    plot = []
    for r in rows:
        team = r.get("Team") or r.get("team")
        if not team:
            continue
        item = {
            "Team": team,
            "Club": team_name(team),
            "Logo": logo_url(team),
            x: r.get(x),
            y: r.get(y),
        }
        for key in extras:
            item[key] = r.get(key)
        plot.append(item)
    return plot


def _render_regular_epa_chart(rows: list[dict]) -> None:
    from data.adj_epa_viz import logo_scatter

    plot = _logo_plot(rows, "Off EPA/g", "Def EPA/g", ["Net EPA/g"])
    st.markdown("##### Regular EPA: offense vs defense")
    st.caption("nflverse play-by-play, unadjusted EPA per game")
    for key, height in (("reference_chart_team_epa_desktop", 660), ("reference_chart_team_epa_mobile", 300)):
        spec = logo_scatter(
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
        st.container(key=key).vega_lite_chart(spec, width="stretch", theme=None)


def _wide_table(rows: list[dict], columns: list[tuple[str, str]]) -> tuple[list[dict], dict]:
    """Source-stat catalog. A-Z by team. Click a column header in the table to sort."""
    table = []
    for r in rows:
        team = r.get("team")
        row = {"Team": team, "Club": team_name(team)}
        for label, key in columns:
            val = r.get(key)
            row[label] = _nan(val) if not isinstance(val, str) else val
        table.append(row)
    table.sort(key=lambda row: (row.get("Team") or ""))
    config = {
        "Team": st.column_config.TextColumn("Team", width=70),
        "Club": st.column_config.TextColumn("Club", width="medium"),
    }
    for label, _key in columns:
        config[label] = st.column_config.NumberColumn(label, format="%.1f", width=90)
    return table, config

def _render_special_teams(season: int, week: int) -> None:
    from data.adj_epa_viz import logo_scatter

    rows = _st_teams(season, week)
    if not rows:
        st.info("Need completed games before special teams totals can be shown.")
        return
    st.markdown(f"#### Special teams, through week {max(week - 1, 0)}")
    st.caption(
        "The scatter is kickoff yards vs punt yards: return average minus coverage average on each unit. "
        "Rank is ST EPA/g, which also folds in field goals, extra points, and turnovers."
    )
    table = []
    for rank, r in enumerate(rows, start=1):
        team = r["team"]
        table.append(
            {
                "Rk": rank,
                "Team": team,
                "Club": team_name(team),
                "Division": division(team),
                "ST EPA/g": _nan(r.get("st_epa_pg")),
                "KO yds": _nan(r.get("ko_yards_pk")),
                "Punt yds": _nan(r.get("punt_yards_pp")),
                "KR avg": _nan(r.get("kr_avg")),
                "KR all avg": _nan(r.get("kr_allowed_avg")),
                "PR avg": _nan(r.get("pr_avg")),
                "PR all avg": _nan(r.get("pr_allowed_avg")),
                "Net punt": _nan(r.get("punt_net_avg")),
                "ST TO": _nan(r.get("st_to_diff")),
                "Give": _nan(r.get("st_to_given")),
                "Take": _nan(r.get("st_to_taken")),
                "ST TDs": _nan(r.get("special_teams_tds")),
                "FG%": None if r.get("fg_pct") is None else 100.0 * r["fg_pct"],
                "FG": (
                    f"{int(r['fg_made'])}/{int(r['fg_att'])}"
                    if r.get("fg_made") is not None and r.get("fg_att") is not None
                    else "-"
                ),
                "G": _nan(r.get("games")),
            }
        )
    has_yards = any(r.get("KO yds") == r.get("KO yds") for r in table)
    if has_yards:
        plot_src = [
            {
                "Team": r["Team"],
                "Club": r["Club"],
                "Logo": logo_url(r["Team"]),
                "KO yds": r["KO yds"],
                "Punt yds": r["Punt yds"],
                "ST EPA/g": r["ST EPA/g"],
                "ST TO": r["ST TO"],
                "ST TDs": r["ST TDs"],
                "FG%": r["FG%"],
            }
            for r in table
        ]
        st.container(key="reference_chart_special_teams").vega_lite_chart(
            logo_scatter(
                plot_src,
                "KO yds",
                "Punt yds",
                x_title="Kickoff yards (KR avg minus coverage avg)   --> better",
                y_title="Punt yards (PR avg minus coverage avg)   --> better",
                origin="zero",
                extra_tips=["ST EPA/g", "ST TO", "ST TDs", "FG%"],
            ),
            width="stretch",
            theme=None,
        )
    else:
        plot_src = [
            {
                "Team": r["Team"],
                "Club": r["Club"],
                "Logo": logo_url(r["Team"]),
                "FG%": r["FG%"],
                "Net punt": r["Net punt"],
                "ST TDs": r["ST TDs"],
            }
            for r in table
        ]
        st.container(key="reference_chart_special_teams").vega_lite_chart(
            logo_scatter(
                plot_src,
                "FG%",
                "Net punt",
                x_title="FG%   --> better",
                y_title="Net punt yards   --> better",
                extra_tips=["ST TDs"],
            ),
            width="stretch",
            theme=None,
        )
    st.container(key="reference_special_teams_table").dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=_grid_height(len(table), cap=1240),
        column_config={
            "Rk": st.column_config.NumberColumn("Rk", help="Rank by special-teams EPA per game", format="%.0f", width=50),
            "Team": st.column_config.TextColumn("Team", width=70),
            "Club": st.column_config.TextColumn("Club", width="medium"),
            "Division": st.column_config.TextColumn("Division", width=110),
            "ST EPA/g": st.column_config.NumberColumn(
                "ST EPA/g",
                help="Expected points added on kickoffs, punts, field goals, and extra points, per game. Includes ST turnovers.",
                format="%+.2f",
                width=95,
            ),
            "KO yds": st.column_config.NumberColumn(
                "KO yds",
                help="Average kickoff return minus average return allowed on your kickoffs. Per kickoff, so scoring a lot does not look like bad coverage.",
                format="%+.1f",
                width=85,
            ),
            "Punt yds": st.column_config.NumberColumn(
                "Punt yds",
                help="Average punt return minus average return allowed on your punts. Per punt, same idea as kickoff yards.",
                format="%+.1f",
                width=90,
            ),
            "KR avg": st.column_config.NumberColumn("KR avg", help="Yards per kickoff return", format="%.1f", width=80),
            "KR all avg": st.column_config.NumberColumn("KR all avg", help="Yards per kickoff return allowed on your kickoffs", format="%.1f", width=95),
            "PR avg": st.column_config.NumberColumn("PR avg", help="Yards per punt return", format="%.1f", width=80),
            "PR all avg": st.column_config.NumberColumn("PR all avg", help="Yards per punt return allowed on your punts", format="%.1f", width=95),
            "Net punt": st.column_config.NumberColumn("Net punt", help="Net yards per punt: gross minus return yards", format="%.1f", width=90),
            "ST TO": st.column_config.NumberColumn(
                "ST TO",
                help="Special-teams turnover margin: muffs, lost fumbles, and blocked punts. Blocked field goals count in ST EPA and FG%, not here.",
                format="%+.0f",
                width=75,
            ),
            "Give": st.column_config.NumberColumn("Give", help="ST giveaways: muffs, lost fumbles, blocked punts", format="%.0f", width=70),
            "Take": st.column_config.NumberColumn("Take", help="ST takeaways: recovered muffs/fumbles and blocked punts", format="%.0f", width=70),
            "ST TDs": st.column_config.NumberColumn("ST TDs", help="Special teams touchdowns this season", format="%.0f", width=75),
            "FG%": st.column_config.NumberColumn("FG%", help="Field goals made / attempted this season", format="%.1f", width=70),
            "FG": st.column_config.TextColumn("FG", help="Field goals made / attempted", width=70),
            "G": st.column_config.NumberColumn("G", help="Games played", format="%.0f", width=55),
        },
    )
    st.caption(
        "Play-by-play kickoffs, punts, field goals, and extra points. "
        "Kickoff yards and punt yards are return average minus coverage average, so volume from scoring does not dominate. "
        "ST turnovers are muffs, lost fumbles, and blocked punts. "
        "ST EPA is the one number that also includes kicking. FG% is made over attempted for the season."
    )


def _render_league_injuries(cards: list[dict], season: int, week: int) -> None:
    st.markdown(f"#### Week {week} injury report")
    rows = []
    for c in cards:
        game = f"{c['away_team']} @ {c['home_team']}"
        for r in list(c.get("injuries_away_rows") or []) + list(c.get("injuries_home_rows") or []):
            rows.append({**r, "game": game})
    if not rows:
        st.info("No current injury-report or reserve-roster states through this week.")
        return
    source_note = _injury_source_note(rows, week)
    if source_note:
        st.info(source_note)

    statuses = list(_STATUS_LABEL.values())
    roster_counts = {
        label: sum(1 for row in rows if row.get("roster_status") == code)
        for code, label in _ROSTER_LABEL.items()
    }
    roster_option_status = {
        f"{label} ({roster_counts[label]})": code
        for code, label in _ROSTER_LABEL.items()
    }
    roster_options = list(roster_option_status)
    f1, f2, f3, f4 = st.container(key="league_injury_filters").columns(
        [2.2, 2.0, 2.8, 1.6],
        vertical_alignment="bottom",
    )
    with f1:
        picked_status = st.multiselect(
            "Game/practice status", statuses, default=statuses, placeholder="No weekly statuses",
            key="inj_status"
        )
    with f2:
        picked_roster = st.multiselect(
            "Roster lists", roster_options, default=roster_options, placeholder="No roster lists",
            key="inj_roster"
        )
    with f3:
        teams = sorted({r.get("team") for r in rows if r.get("team")})
        picked_teams = st.multiselect(
            "Teams", teams, placeholder="All teams", key="inj_teams"
        )
    with f4:
        starters_only = st.toggle("Starters only", key="inj_starters")

    picked_roster_statuses = {
        roster_option_status[option]
        for option in picked_roster
    }
    filtered = [
        r
        for r in rows
        if (
            _STATUS_LABEL.get(r.get("status"), "") in picked_status
            or r.get("roster_status") in picked_roster_statuses
        )
        and (not picked_teams or r.get("team") in picked_teams)
        and (not starters_only or r.get("is_starter"))
    ]
    out_n = sum(1 for r in filtered if r.get("status") == "out")
    reserve_n = sum(1 for r in filtered if r.get("roster_status"))
    start_n = sum(1 for r in filtered if r.get("is_starter"))
    st.markdown(
        '<div class="chips">'
        f"<div class='chip'><b>{len(filtered)}</b><span>listed</span></div>"
        f"<div class='chip'><b>{out_n}</b><span>ruled out</span></div>"
        f"<div class='chip'><b>{reserve_n}</b><span>roster list</span></div>"
        f"<div class='chip'><b>{start_n}</b><span>starters</span></div>"
        "</div>",
        unsafe_allow_html=True,
    )
    if not filtered:
        st.info("No players match those filters.")
        return

    filtered.sort(
        key=lambda r: (
            _STATUS_RANK.get(r.get("status") or r.get("roster_status"), 9),
            not r.get("is_starter"),
            r.get("team") or "",
        )
    )
    table = []
    for r in filtered:
        entry = _injury_table([r], with_game=r.get("game"))[0]
        table.append(entry)
    st.markdown(_mobile_injury_cards(filtered, with_game=True), unsafe_allow_html=True)
    st.container(key="reference_league_injury_table").dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=_grid_height(len(table)),
        column_config={**_INJURY_CONFIG, "Game": st.column_config.TextColumn("Game", width=110)},
    )
    st.caption(
        "Source: nflverse weekly injury reports and weekly roster snapshots. Game/practice statuses "
        "clear when absent from a later report. IR, PUP, NFI, and suspension reflect the roster state "
        "through the selected week. Since and Last report retain source-week context. "
        "Starters come from depth charts and last week's snap counts."
    )




_NFLVERSE_SECTIONS: dict[str, list[tuple[str, str]]] = {
    "Passing": [
        ("Cmp", "completions"),
        ("Att", "attempts"),
        ("Cmp%", "cmp_pct"),
        ("Pass yds", "passing_yards"),
        ("Pass TD", "passing_tds"),
        ("INT", "passing_interceptions"),
        ("Sacks", "sacks_suffered"),
        ("Sack yds", "sack_yards_lost"),
        ("Air yds", "passing_air_yards"),
        ("YAC", "passing_yards_after_catch"),
        ("1st", "passing_first_downs"),
        ("EPA", "passing_epa"),
        ("CPOE", "passing_cpoe"),
        ("10+", "passing_10"),
        ("20+", "passing_20"),
        ("40+", "passing_40"),
    ],
    "Rushing": [
        ("Carries", "carries"),
        ("Rush yds", "rushing_yards"),
        ("YPC", "ypc"),
        ("Rush TD", "rushing_tds"),
        ("Fum", "rushing_fumbles"),
        ("Fum lost", "rushing_fumbles_lost"),
        ("1st", "rushing_first_downs"),
        ("EPA", "rushing_epa"),
        ("10+", "rushing_10"),
        ("20+", "rushing_20"),
        ("40+", "rushing_40"),
    ],
    "Receiving": [
        ("Rec", "receptions"),
        ("Tgt", "targets"),
        ("Catch%", "catch_pct"),
        ("Rec yds", "receiving_yards"),
        ("Rec TD", "receiving_tds"),
        ("Air yds", "receiving_air_yards"),
        ("YAC", "receiving_yards_after_catch"),
        ("1st", "receiving_first_downs"),
        ("EPA", "receiving_epa"),
        ("10+", "receiving_10"),
        ("20+", "receiving_20"),
        ("40+", "receiving_40"),
    ],
    "Defense": [
        ("Solo", "def_tackles_solo"),
        ("Ast", "def_tackle_assists"),
        ("TFL", "def_tackles_for_loss"),
        ("Sacks", "def_sacks"),
        ("Sack yds", "def_sack_yards"),
        ("QB hits", "def_qb_hits"),
        ("INT", "def_interceptions"),
        ("PD", "def_pass_defended"),
        ("Def TD", "def_tds"),
        ("FF", "def_fumbles_forced"),
        ("Safeties", "def_safeties"),
        ("Punt blk", "def_punt_blocks"),
        ("FG blk", "def_fg_blocks"),
        ("PAT blk", "def_pat_blocks"),
    ],
    "Special teams": [
        ("FG%", "fg_pct"),
        ("PAT%", "pat_pct"),
        ("Punt att", "pt_att"),
        ("Net punt", "punt_net_avg"),
        ("In 20", "inside_20_pct"),
        ("PR yds", "punt_return_yards"),
        ("KR yds", "kickoff_return_yards"),
        ("ST TDs", "special_teams_tds"),
        ("FG long", "fg_long"),
    ],
    "Ball / flags": [
        ("Pen", "penalties"),
        ("Pen yds", "penalty_yards"),
        ("Fum lost", "fumbles_lost_total"),
        ("Fum rec", "fumble_recovery_opp"),
        ("Own rec", "fumble_recovery_own"),
        ("G", "games"),
    ],
}

_NGS_SECTIONS = {
    "Passing": {
        "columns": [
            ("Att", "attempts"),
            ("Cmp", "completions"),
            ("Pass yds", "pass_yards"),
            ("TD", "pass_tds"),
            ("INT", "interceptions"),
            ("Rating", "passer_rating"),
            ("TTT", "avg_time_to_throw"),
            ("CPOE", "completion_percentage_above_expectation"),
            ("xComp%", "expected_completion_percentage"),
            ("Int air", "avg_intended_air_yards"),
            ("Comp air", "avg_completed_air_yards"),
            ("Air diff", "avg_air_yards_differential"),
            ("Agg%", "aggressiveness"),
            ("Air to sticks", "avg_air_yards_to_sticks"),
            ("Max air", "max_completed_air"),
        ],
        "x": "CPOE",
        "y": "TTT",
        "x_key": "completion_percentage_above_expectation",
        "y_key": "avg_time_to_throw",
        "x_title": "CPOE   --> better",
        "y_title": "Time to throw (seconds)",
        "sort": "CPOE",
        "key": "passing",
    },
    "Rushing": {
        "columns": [
            ("Att", "rush_att"),
            ("Yds", "rush_yards"),
            ("YPC", "ypc"),
            ("TD", "rush_tds"),
            ("RYOE", "ryoe"),
            ("RYOE/att", "ryoe_per_att"),
            ("Eff", "efficiency"),
            ("8+ box%", "percent_attempts_gte_eight_defenders"),
            ("Time to LOS", "avg_time_to_los"),
            ("% over exp", "rush_pct_over_expected"),
        ],
        "x": "RYOE/att",
        "y": "8+ box%",
        "x_key": "ryoe_per_att",
        "y_key": "percent_attempts_gte_eight_defenders",
        "x_title": "RYOE per attempt   --> better",
        "y_title": "Share of rushes vs 8+ in the box",
        "sort": "RYOE/att",
        "key": "rushing",
    },
    "Receiving": {
        "columns": [
            ("Tgt", "targets"),
            ("Rec", "receptions"),
            ("Catch%", "catch_pct"),
            ("Yds", "rec_yards"),
            ("TD", "rec_tds"),
            ("Cushion", "avg_cushion"),
            ("Sep", "avg_separation"),
            ("Int air", "avg_intended_air_yards"),
            ("YAC", "avg_yac"),
            ("xYAC", "avg_expected_yac"),
            ("YAC OE", "avg_yac_above_expectation"),
        ],
        "x": "Sep",
        "y": "YAC OE",
        "x_key": "avg_separation",
        "y_key": "avg_yac_above_expectation",
        "x_title": "Avg separation (yards)   --> more space",
        "y_title": "YAC over expected   --> better",
        "sort": "YAC OE",
        "key": "receiving",
    },
}


def _render_nflverse_page(season: int, week: int) -> None:
    rows = _nflverse_wide(season, week)
    if not rows:
        st.info("Need completed games before the nflverse table can be shown.")
        return
    st.markdown(f"#### nflverse team stats, through week {max(week - 1, 0)}")
    st.caption(
        "Season totals from the nflverse team-week file, A-Z by team. Click a column header to sort. "
        "This is a source catalog, not a ranking. Lists of individual kicks are left out."
    )
    section = st.segmented_control(
        "Unit",
        list(_NFLVERSE_SECTIONS),
        default="Passing",
        label_visibility="collapsed",
        key="nflverse_unit",
    ) or "Passing"
    cols = _NFLVERSE_SECTIONS[section]
    table, config = _wide_table(rows, cols)
    st.container(key="reference_nflverse_table").dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=_grid_height(len(table), cap=1240),
        column_config=config,
    )


def _render_ngs_page(season: int, week: int) -> None:
    from data.adj_epa_viz import logo_scatter

    bundle = _ngs_wide(season, week)
    st.markdown(f"#### Next Gen Stats, through week {max(week - 1, 0)}")
    st.caption(
        "NFL Next Gen Stats player-week files, rolled up to the team (weighted by attempts, rushes, or targets), A-Z. "
        "Click a column header to sort. This is a source catalog, not a ranking. Separate from nflverse play-by-play."
    )
    section = st.segmented_control(
        "Unit",
        list(_NGS_SECTIONS),
        default="Passing",
        label_visibility="collapsed",
        key="ngs_unit",
    ) or "Passing"
    spec = _NGS_SECTIONS[section]
    rows = bundle.get(spec["key"]) or []
    if not rows:
        st.info("No Next Gen rows for that unit yet.")
        return
    table, config = _wide_table(rows, spec["columns"])
    plot = _logo_plot(table, spec["x"], spec["y"])
    st.container(key="reference_chart_ngs").vega_lite_chart(
        logo_scatter(
            plot,
            spec["x"],
            spec["y"],
            x_title=spec["x_title"],
            y_title=spec["y_title"],
        ),
        width="stretch",
        theme=None,
    )
    st.container(key="reference_ngs_table").dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=_grid_height(len(table), cap=1240),
        column_config=config,
    )


def _render_adj_epa(season: int, week: int) -> None:
    from data.adj_epa_viz import adj_epa_scatter

    view = st.segmented_control(
        "Unit",
        ["Adjusted EPA", "Special teams"],
        default="Adjusted EPA",
        label_visibility="collapsed",
        key="adj_unit",
    ) or "Adjusted EPA"
    if view == "Special teams":
        _render_special_teams(season, week)
        return

    rows = _adj_epa(season, week)
    if not rows:
        st.info("Need completed games before opponent-adjusted EPA can be computed.")
        return

    through = max(week - 1, 0)
    st.markdown(f"#### Opponent-adjusted EPA, through week {through}")
    st.caption("nflverse play-by-play, opponent-adjusted EPA/g")
    with st.expander("How Adjusted EPA is calculated"):
        st.markdown(
            """
**Adj Off EPA = Off EPA - (Opp Def EPA - League Off EPA)**  
**Adj Def EPA = Def EPA allowed - (Opp Off EPA - League Off EPA)**  
**Adj Net = Adj Off - Adj Def**

A team's own games all count. Opp Def / Opp Off use that opponent's *other* games. Opponent ratings are shrunk toward league average: weight = n / (n + 4).
            """
        )
    plot = [
        {
            "Team": r["team"],
            "Club": team_name(r["team"]),
            "Adj Off": r.get("adj_off_epa_pg"),
            "Adj Def": r.get("adj_def_epa_pg"),
            "Adj Net": r.get("adj_net_epa_pg"),
            "Color": display_color(r["team"]),
            "Logo": logo_url(r["team"]),
        }
        for r in rows
    ]
    st.container(key="reference_chart_adj_epa_desktop").vega_lite_chart(
        adj_epa_scatter(plot, height=660), width="stretch", theme=None
    )
    st.container(key="reference_chart_adj_epa_mobile").vega_lite_chart(
        adj_epa_scatter(plot, height=300), width="stretch", theme=None
    )

    table = []
    for rank, r in enumerate(rows, start=1):
        team = r["team"]
        table.append(
            {
                "Rk": rank,
                "Team": team,
                "Club": team_name(team),
                "Adj Off": _nan(r.get("adj_off_epa_pg")),
                "Adj Def": _nan(r.get("adj_def_epa_pg")),
                "Adj Net": _nan(r.get("adj_net_epa_pg")),
                "Raw Off": _nan(r.get("off_epa_pg")),
                "Raw Def": _nan(r.get("def_epa_pg")),
                "Adj Pass": _nan(r.get("adj_pass_epa_pg")),
                "Adj Rush": _nan(r.get("adj_rush_epa_pg")),
                "Opp Def": _nan(r.get("sos_off")),
                "Opp Off": _nan(r.get("sos_def")),
                "G": _nan(r.get("games")),
            }
        )
    st.container(key="reference_adj_epa_table").dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=_grid_height(len(table), cap=1240),
        column_config={
            "Rk": st.column_config.NumberColumn("Rk", help="Rank by adjusted net EPA/g", format="%.0f", width=50),
            "Team": st.column_config.TextColumn("Team", width=70),
            "Club": st.column_config.TextColumn("Club", width="medium"),
            "Adj Off": st.column_config.NumberColumn("Adj Off", help="Offensive EPA/g after opponent adjustment - higher is better", format="%+.1f", width=90),
            "Adj Def": st.column_config.NumberColumn("Adj Def", help="Defensive EPA allowed/g after opponent adjustment - lower is better", format="%+.1f", width=90),
            "Adj Net": st.column_config.NumberColumn("Adj Net", help="Adj Off minus Adj Def - overall unit quality after schedule", format="%+.1f", width=90),
            "Raw Off": st.column_config.NumberColumn("Raw Off", help="Unadjusted offensive EPA/g", format="%+.1f", width=90),
            "Raw Def": st.column_config.NumberColumn("Raw Def", help="Unadjusted defensive EPA allowed/g", format="%+.1f", width=90),
            "Adj Pass": st.column_config.NumberColumn("Adj Pass", help="Opponent-adjusted passing EPA/g", format="%+.1f", width=90),
            "Adj Rush": st.column_config.NumberColumn("Adj Rush", help="Opponent-adjusted rushing EPA/g", format="%+.1f", width=90),
            "Opp Def": st.column_config.NumberColumn("Opp Def", help="Average EPA the defenses faced usually allow (higher = easier offensive schedule)", format="%+.1f", width=90),
            "Opp Off": st.column_config.NumberColumn("Opp Off", help="Average EPA the offenses faced usually produce (higher = tougher defensive schedule)", format="%+.1f", width=90),
            "G": st.column_config.NumberColumn("G", help="Games played", format="%.0f", width=55),
        },
    )
    st.caption(
        "Every game is in a team's own EPA. Leave-one-out only applies to opponent strength so this week's result is not counted twice. Shrunk with n/(n+4)."
    )


# --------------------------------------------------------------------------- routing


def _set_view(season: int, week: int, game: str | None = None, view: str | None = None, theme: str | None = None) -> None:
    params = {"season": str(season), "week": str(week)}
    if game:
        params["game"] = game
    if view:
        params["view"] = view
    chosen = theme or theme_from_query()
    if chosen and chosen != "default":
        params["theme"] = chosen
    st.query_params.clear()
    st.query_params.update(params)


def _back_to_board(season: int, week: int) -> None:
    st.session_state["board_nonce"] = st.session_state.get("board_nonce", 0) + 1
    _set_view(season, week)
    st.rerun()


def _render_hub(cards: list[dict], season: int, week: int) -> None:
    """The week's games and the league-wide reference tables, all on one page."""
    if cards:
        st.markdown(_board_summary(cards), unsafe_allow_html=True)
    board, power, stats, adj, nflv, ngs, injuries = st.tabs(
        ["Matchups", "Power ratings", "Team stats", "Adjusted EPA", "nflverse", "Next Gen", "Injury report"]
    )
    with board:
        if cards:
            _render_board(cards, season, week)
        else:
            st.warning("No games scheduled for that week.")
    with power:
        _render_power_ratings(season, week)
    with stats:
        _render_team_stats(season, week)
    with adj:
        _render_adj_epa(season, week)
    with nflv:
        _render_nflverse_page(season, week)
    with ngs:
        _render_ngs_page(season, week)
    with injuries:
        _render_league_injuries(cards, season, week)


def _render_game(c: dict, season: int, week: int) -> None:
    back_col, tab_col = st.container(key="game_navigation").columns([1.1, 5], vertical_alignment="center")
    if back_col.button("← Back to board", width="stretch"):
        _back_to_board(season, week)
    with tab_col:
        section = st.segmented_control(
            "Section",
            ["Matchup", "Injuries"],
            default="Injuries" if st.query_params.get("view") == "injuries" else "Matchup",
            label_visibility="collapsed",
        ) or "Matchup"
    if section == "Injuries":
        render_injuries(c)
    else:
        render_matchup(c)


def main() -> None:
    qp = st.query_params
    seasons = [2026, 2025, 2024]
    try:
        qp_season = int(qp.get("season", 2026))
    except (TypeError, ValueError):
        qp_season = 2026
    if qp_season not in seasons:
        qp_season = 2026

    theme = theme_from_query()
    apply_theme(theme)

    title_col, theme_col, season_col, week_col = st.container(key="site_header").columns([5.2, 1.6, 1.1, 1.1], vertical_alignment="bottom")
    with title_col:
        sources = (
            '<a href="https://nflverse.nflverse.com/" title="https://nflverse.nflverse.com/" target="_blank" rel="noopener noreferrer">nflverse</a> | '
            '<a href="https://nextgenstats.nfl.com/" title="https://nextgenstats.nfl.com/" target="_blank" rel="noopener noreferrer">Next Gen Stats</a> | '
            '<a href="https://www.pro-football-reference.com/" title="https://www.pro-football-reference.com/" target="_blank" rel="noopener noreferrer">PFR</a> | '
            '<a href="https://www.nfeloapp.com/" title="https://www.nfeloapp.com/" target="_blank" rel="noopener noreferrer">nfelo</a> | '
            '<a href="https://open-meteo.com/" title="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Open-Meteo</a>'
        )
        st.markdown(
            '<div class="masthead"><h1>NFL Matchup Board</h1></div>'
            f'<div class="sub desktop-sources">Sources: {sources}</div>'
            f'<details class="mobile-sources"><summary>Sources</summary>{sources}</details>',
            unsafe_allow_html=True,
        )
    with theme_col:
        theme_label = st.selectbox("Theme", list(THEME_IDS), index=list(THEME_IDS.values()).index(theme))
        theme = THEME_IDS[theme_label]
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

    if str(season) != str(qp.get("season", "")) or str(week) != str(qp.get("week", "")) or theme != theme_from_query():
        _set_view(season, week, theme=theme)
        st.rerun()

    try:
        cards = _cards(season, week)
    except Exception as exc:
        st.error("Could not build this week's board. The upstream data source may be down.")
        st.exception(exc)
        return

    selected = {c.get("game_id"): c for c in cards}.get(qp.get("game"))
    if selected:
        _render_game(selected, season, week)
    else:
        _render_hub(cards, season, week)


if __name__ == "__main__":
    main()
