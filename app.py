"""Weekly NFL matchup board for a family football pool."""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from data.matchups import available_weeks, build_week_board, current_week, format_spread, league_team_rows
from data.schedules import format_kickoff_pt

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
      .block-container { padding-top: 1.1rem; padding-bottom: 2rem; }
      .board-wrap { overflow-x: auto; }
      table.board { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
      table.board th {
        text-align: left; color: #9aa7b4; font-weight: 600;
        padding: 0.45rem 0.7rem; border-bottom: 1px solid #2a3542; white-space: nowrap;
      }
      table.board td {
        padding: 0.55rem 0.7rem; border-bottom: 1px solid #1f2933; vertical-align: top;
      }
      table.board tr:hover td { background: #151c24; }
      .win { cursor: help; border-bottom: 1px dotted #6b7785; }
      .muted { color: #8b98a5; }
      .game-grid { display: flex; flex-wrap: wrap; gap: 0.4rem 0.5rem; margin: 0.4rem 0 0.8rem; }
      .game-grid a {
        display: inline-block; padding: 0.28rem 0.65rem; border-radius: 999px;
        background: #1a222c; color: #e8eef4; text-decoration: none; font-size: 0.85rem;
        border: 1px solid #2a3542;
      }
      .game-grid a:hover, .game-grid a.active { border-color: #c8a24a; color: #c8a24a; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _fmt(val, digits=1, signed=False, suffix=""):
    if val is None:
        return "—"
    try:
        n = float(val)
    except (TypeError, ValueError):
        return "—"
    body = f"{n:+.{digits}f}" if signed else f"{n:.{digits}f}"
    return body + suffix


def _pct(val):
    if val is None:
        return "—"
    n = float(val)
    if n > 1.5:
        return f"{n:.0f}%"
    return f"{100.0 * n:.0f}%"


@st.cache_data(ttl=3600, show_spinner="Loading nflverse / nfelo / weather…")
def _cards(season: int, week: int, _ver: int = 3):
    return build_week_board(season, week)


@st.cache_data(ttl=3600)
def _weeks(season: int):
    return available_weeks(season)


@st.cache_data(ttl=3600)
def _league_teams(season: int, week: int, _ver: int = 1):
    return league_team_rows(season, week)


def _unit_row(label, home_val, away_val, home, away, digits=1, unit_title=None):
    return {
        "Unit": label,
        "unit_title": unit_title or label,
        away: _fmt(away_val, digits),
        home: _fmt(home_val, digits),
    }


_UNIT_TITLES = {
    "CPOE": "Completion Percentage Over Expected",
    "RYOE (sum)": "Rush Yards Over Expected",
    "Time to throw": "Time to throw",
    "TO margin/g": "Turnover margin per game",
    "FG%": "Field goal percentage",
    "ST TDs": "Special teams touchdowns",
    "Pass EPA/g": "Pass Expected Points Added per game",
    "Pass EPA allowed/g": "Pass Expected Points Added allowed per game",
    "Run EPA/g": "Run Expected Points Added per game",
    "Run EPA allowed/g": "Run Expected Points Added allowed per game",
    "Off EPA/g": "Offense Expected Points Added per game",
    "Def EPA/g (allowed)": "Defense Expected Points Added allowed per game",
}


def _unit_title(label: str) -> str:
    return _UNIT_TITLES.get(label, label)


def _unit_table_html(rows: list[dict], away: str, home: str) -> str:
    thead = (
        "<thead><tr>"
        f"<th>Unit</th><th>{html.escape(away)}</th><th>{html.escape(home)}</th>"
        "</tr></thead>"
    )
    body = []
    for row in rows:
        label = row["Unit"]
        title = html.escape(row.get("unit_title") or _unit_title(label))
        unit = f'<span class="unit" title="{title}">{html.escape(label)}</span>'
        body.append(
            "<tr>"
            f"<td>{unit}</td>"
            f"<td>{html.escape(str(row[away]))}</td>"
            f"<td>{html.escape(str(row[home]))}</td>"
            "</tr>"
        )
    return (
        '<div class="board-wrap"><table class="board">'
        f"{thead}<tbody>{''.join(body)}</tbody></table></div>"
    )


def _weather_note_extra(note: str, t, w, p) -> bool:
    import re

    remainder = note
    if t is not None:
        remainder = re.sub(rf"\b{int(round(float(t)))}\s*°?\s*F\b", "", remainder, flags=re.I)
    if w is not None:
        remainder = re.sub(rf"\b{int(round(float(w)))}\s*mph\b", "", remainder, flags=re.I)
    if p:
        for pat in (rf"\b{float(p):.2f}\s*in\b", rf"\b{float(p):.1f}\s*in\b"):
            remainder = re.sub(pat, "", remainder, flags=re.I)
    remainder = re.sub(
        r"\b(wind|mph|precip(?:itation)?|temp(?:erature)?|degrees?|°f)\b",
        "",
        remainder,
        flags=re.I,
    )
    remainder = re.sub(r"[,·|/\s]+", " ", remainder).strip(" .,-")
    return len(remainder) >= 3

def _weather_banner_parts(c: dict) -> list[str]:
    t = c.get("wx_temp_f") if c.get("wx_temp_f") is not None else c.get("temp")
    w = c.get("wx_wind_mph") if c.get("wx_wind_mph") is not None else c.get("wind")
    p = c.get("wx_precip_in")
    parts = []
    if t is not None:
        parts.append(f"{float(t):.0f}°F")
    if w is not None:
        parts.append(f"{float(w):.0f} mph wind")
    if p:
        parts.append(f"{float(p):.2f} in precip")
    note = (c.get("weather_note") or "").strip()
    if note and (not parts or _weather_note_extra(note, t, w, p)):
        parts.append(note)
    return parts




def _kickoff_label(c: dict) -> str:
    when = (c.get("kickoff_pt") or "").strip()
    if when:
        return when
    return format_kickoff_pt(c.get("gameday"), c.get("gametime")) or "—"


def _inj_count_cell(c: dict) -> str:
    away, home = c["away_team"], c["home_team"]
    a = c.get("injuries_count_away") or "0 OUT · 0 Q"
    h = c.get("injuries_count_home") or "0 OUT · 0 Q"
    return f"{away} {a}\n{home} {h}"


def render_injuries(c: dict):
    away, home = c["away_team"], c["home_team"]
    rows = list(c.get("injuries_away_rows") or []) + list(c.get("injuries_home_rows") or [])
    if not rows:
        st.info("No listed injuries for this game.")
        return
    table = []
    for r in rows:
        status = {"out": "OUT", "doubtful": "Doubtful", "questionable": "Questionable"}.get(
            r.get("status"), r.get("status") or ""
        )
        table.append(
            {
                "Team": r.get("team"),
                "Player": r.get("player"),
                "Pos": r.get("position") or "",
                "Status": status,
                "Injury": r.get("injury") or "",
                "Practice": r.get("practice") or "",
                "Starter": "yes" if r.get("is_starter") else "",
            }
        )
    st.caption("Full nflverse report for this game: OUT, Doubtful, and Questionable.")
    st.dataframe(table, hide_index=True, width="stretch")
    o1, o2 = st.columns(2)
    o1.markdown(f"**{away} starters out**  \n{c.get('injuries_out_away') or 'none'}")
    o2.markdown(f"**{home} starters out**  \n{c.get('injuries_out_home') or 'none'}")


def render_card(c: dict):
    away, home = c["away_team"], c["home_team"]
    meta = " · ".join(
        x
        for x in [
            _kickoff_label(c),
            c.get("stadium") or "",
            c.get("venue") or "",
            f"QB {c.get('away_qb') or '—'} / {c.get('home_qb') or '—'}",
        ]
        if x
    )
    st.caption(meta)

    c1, c2, c3, c4 = st.columns(4)
    src = c.get("win_pct_source") or ""
    c1.metric(f"{home} win%", _pct(c.get("home_win_pct")), src)
    spread_s = format_spread(c.get("spread_line"), home, away)
    c2.metric(
        "Spread",
        spread_s,
        f"nfelo {_fmt(c.get('nfelo_home_line'), 1, True)}" if c.get("nfelo_home_line") is not None else "market",
    )
    c3.metric("Total", _fmt(c.get("total_line"), 1))
    nf_gap = None
    if c.get("nfelo_home") is not None and c.get("nfelo_away") is not None:
        nf_gap = c["nfelo_home"] - c["nfelo_away"]
    c4.metric("nfelo", f"{_fmt(c.get('nfelo_away'), 0)} / {_fmt(c.get('nfelo_home'), 0)}", _fmt(nf_gap, 0, True))

    if c.get("venue") == "outdoor":
        wx = _weather_banner_parts(c)
        st.info("Weather: " + (" · ".join(wx) if wx else "outdoor (no reading yet)"))

    if c.get("standouts"):
        st.markdown("**Why this game stands out**")
        bullets = []
        for item in c["standouts"]:
            if isinstance(item, dict):
                label = item.get("label") or ""
                detail = item.get("detail") or ""
                if label and detail:
                    bullets.append(f"- **{label}:** {detail}")
                else:
                    bullets.append(f"- {label or detail}")
            else:
                bullets.append(f"- {item}")
        st.markdown("\n".join(bullets))

    i1, i2 = st.columns(2)
    i1.markdown(f"**{away} starters out**  \n{c.get('injuries_out_away') or 'none'}")
    i2.markdown(f"**{home} starters out**  \n{c.get('injuries_out_home') or 'none'}")

    rows = [
        _unit_row("Pass EPA/g", c.get("u_h_pass"), c.get("u_a_pass"), home, away),
        _unit_row("Pass EPA allowed/g", c.get("u_h_pass_d"), c.get("u_a_pass_d"), home, away),
        _unit_row("Run EPA/g", c.get("u_h_rush"), c.get("u_a_rush"), home, away),
        _unit_row("Run EPA allowed/g", c.get("u_h_rush_d"), c.get("u_a_rush_d"), home, away),
        _unit_row("Points for/g", c.get("u_h_pf"), c.get("u_a_pf"), home, away),
        _unit_row("Points allowed/g", c.get("u_h_pa"), c.get("u_a_pa"), home, away),
        _unit_row("TO margin/g", c.get("u_to_home"), c.get("u_to_away"), home, away, digits=2),
        _unit_row("Pressures generated", c.get("u_h_press_gen"), c.get("u_a_press_gen"), home, away, digits=0),
        _unit_row("Pressures allowed", c.get("u_h_press_all"), c.get("u_a_press_all"), home, away, digits=0),
        _unit_row("Pressure % allowed", c.get("u_press_pct_home"), c.get("u_press_pct_away"), home, away, digits=1),
        _unit_row("Off EPA/g", c.get("u_off_epa_pg_home"), c.get("u_off_epa_pg_away"), home, away),
        _unit_row("Def EPA/g (allowed)", c.get("u_def_epa_pg_home"), c.get("u_def_epa_pg_away"), home, away),
        _unit_row("CPOE", c.get("u_cpoe_home"), c.get("u_cpoe_away"), home, away, digits=1),
        _unit_row("Time to throw", c.get("u_ttt_home"), c.get("u_ttt_away"), home, away, digits=2),
        _unit_row("RYOE (sum)", c.get("u_ryoe_home"), c.get("u_ryoe_away"), home, away, digits=0),
        _unit_row("ST TDs", c.get("u_st_tds_home"), c.get("u_st_tds_away"), home, away, digits=0),
        _unit_row("FG%", c.get("u_fg_home"), c.get("u_fg_away"), home, away, digits=2),
        _unit_row("Punt net yds", c.get("u_punt_net_home"), c.get("u_punt_net_away"), home, away, digits=1),
    ]
    st.markdown(_unit_table_html(rows, away, home), unsafe_allow_html=True)

    r1, r2 = st.columns(2)
    r1.markdown(
        f"**Recent form (last 3 games)** — {away}  \n"
        f"offense EPA per game {_fmt(c.get('rec_off_epa_pg_away'))} · "
        f"defense EPA allowed per game {_fmt(c.get('rec_def_epa_pg_away'))} · "
        f"turnover margin {_fmt(c.get('rec_to_diff_away'), 1, True)}"
    )
    r2.markdown(
        f"**Recent form (last 3 games)** — {home}  \n"
        f"offense EPA per game {_fmt(c.get('rec_off_epa_pg_home'))} · "
        f"defense EPA allowed per game {_fmt(c.get('rec_def_epa_pg_home'))} · "
        f"turnover margin {_fmt(c.get('rec_to_diff_home'), 1, True)}"
    )



def _render_board(cards: list[dict], season: int, week: int) -> None:
    show_score = any(c.get("home_score") is not None and c.get("away_score") is not None for c in cards)
    widths = [1.35, 1.6, 0.8, 1.1, 1.0, 1.1, 1.8] if show_score else [1.35, 1.8, 1.1, 1.0, 1.1, 2.0]
    hdr = st.columns(widths)
    hdr[0].markdown("**When**")
    hdr[1].markdown("**Matchup**")
    idx = 2
    if show_score:
        hdr[idx].markdown("**Score**")
        idx += 1
    hdr[idx].markdown("**Spread**")
    hdr[idx + 1].markdown("**Win%**")
    hdr[idx + 2].markdown("**Venue**")
    hdr[idx + 3].markdown("**Injuries**")

    for c in cards:
        home, away = c["home_team"], c["away_team"]
        gid = c.get("game_id") or ""
        cols = st.columns(widths)
        cols[0].markdown(_kickoff_label(c))
        with cols[1]:
            if st.button(f"{away} @ {home}", key=f"board_game_{season}_{week}_{gid}"):
                _set_view(season, week, gid, page="week")
                st.rerun()
        col_i = 2
        if show_score:
            score = ""
            if c.get("home_score") is not None and c.get("away_score") is not None:
                score = f"{int(c['away_score'])}–{int(c['home_score'])}"
            cols[col_i].write(score)
            col_i += 1
        cols[col_i].write(format_spread(c.get("spread_line"), home, away))
        src = c.get("win_pct_source") or "unknown"
        win = _pct(c.get("home_win_pct"))
        if c.get("home_win_pct") is not None:
            win = f"{win}&nbsp;{html.escape(home)}"
        title = html.escape(f"Win% from {src}")
        cols[col_i + 1].markdown(
            f'<span class="win" title="{title}" style="white-space:nowrap">{win}</span>',
            unsafe_allow_html=True,
        )
        cols[col_i + 2].write(_venue_text(c))
        with cols[col_i + 3]:
            if st.button(_inj_count_cell(c), key=f"board_inj_{season}_{week}_{gid}"):
                _set_view(season, week, gid, "injuries", page="week")
                st.rerun()


def _venue_text(c: dict) -> str:
    if c.get("venue") != "outdoor":
        return "indoor"
    bits = []
    t = c.get("wx_temp_f") if c.get("wx_temp_f") is not None else c.get("temp")
    w = c.get("wx_wind_mph") if c.get("wx_wind_mph") is not None else c.get("wind")
    if t is not None:
        bits.append(f"{float(t):.0f}°F")
    if w is not None:
        bits.append(f"{float(w):.0f} mph")
    if c.get("wx_precip_in"):
        bits.append(f"{float(c['wx_precip_in']):.2f} in")
    return " ".join(bits) or (c.get("weather_note") or "outdoor")


def _set_view(season: int, week: int, game: str | None = None, view: str | None = None, page: str | None = None) -> None:
    params = {"season": str(season), "week": str(week), "page": page or "week"}
    if game:
        params["game"] = game
    if view:
        params["view"] = view
    st.query_params.clear()
    st.query_params.update(params)


def _render_teams_page(season: int, week: int) -> None:
    st.subheader(f"Team form through week {max(week - 1, 0)}")
    st.caption("Season-to-date nflverse EPA and scoring. Hover CPOE on the week board for the full name; here CPOE is completion percentage over expected.")
    rows = _league_teams(season, week)
    if not rows:
        st.info("No team-week stats yet for this season.")
        return
    pretty = []
    for r in rows:
        pretty.append(
            {
                "Team": r["Team"],
                "nfelo": _fmt(r.get("nfelo"), 0),
                "Off EPA/g": _fmt(r.get("Off EPA/g")),
                "Def EPA/g": _fmt(r.get("Def EPA/g")),
                "PF/g": _fmt(r.get("PF/g")),
                "PA/g": _fmt(r.get("PA/g")),
                "TO": _fmt(r.get("TO"), 1, True),
                "CPOE": _fmt(r.get("CPOE"), 1),
                "FG%": _fmt(r.get("FG%"), 2),
                "Games": _fmt(r.get("Games"), 0),
            }
        )
    st.dataframe(pretty, hide_index=True, width="stretch")


def _render_league_injuries(cards: list[dict], season: int, week: int) -> None:
    st.subheader(f"Week {week} injury report")
    st.caption("Every listed OUT / Doubtful / Questionable. Click a row’s team matchup on the week board for the game page.")
    rows = []
    for c in cards:
        for r in list(c.get("injuries_away_rows") or []) + list(c.get("injuries_home_rows") or []):
            status = {"out": "OUT", "doubtful": "Doubtful", "questionable": "Questionable"}.get(
                r.get("status"), r.get("status") or ""
            )
            rows.append(
                {
                    "Team": r.get("team"),
                    "Player": r.get("player"),
                    "Pos": r.get("position") or "",
                    "Status": status,
                    "Injury": r.get("injury") or "",
                    "Practice": r.get("practice") or "",
                    "Starter": "yes" if r.get("is_starter") else "",
                    "Game": f"{c['away_team']} @ {c['home_team']}",
                }
            )
    if not rows:
        st.info("No OUT / Doubtful / Questionable listings in the nflverse injury file for this week.")
        return
    st.dataframe(rows, hide_index=True, width="stretch")


def main():
    qp = st.query_params
    seasons = [2026, 2025, 2024]
    try:
        qp_season = int(qp.get("season", 2026))
    except (TypeError, ValueError):
        qp_season = 2026
    if qp_season not in seasons:
        qp_season = 2026

    pages = ["Week board", "Teams", "Injuries"]
    page_key = {"week": "Week board", "teams": "Teams", "injuries": "Injuries"}
    qp_page = page_key.get(str(qp.get("page", "week")), "Week board")

    title_col, page_col, season_col, week_col = st.columns([4.2, 2.4, 1.1, 1.1])
    with title_col:
        st.title("NFL Matchup Board")
        st.caption("Context for the pool, not predicted scores.")
    with page_col:
        st.caption("Page")
        page = st.radio("Page", pages, index=pages.index(qp_page), horizontal=True, label_visibility="collapsed")
    with season_col:
        st.caption("Season")
        season = st.selectbox("Season", seasons, index=seasons.index(qp_season), label_visibility="collapsed")
    try:
        weeks = _weeks(season)
    except Exception as exc:
        st.error(f"Could not load schedule: {exc}")
        return
    try:
        qp_week = int(qp.get("week", current_week(season)))
    except (TypeError, ValueError):
        qp_week = current_week(season)
    if qp_week not in weeks:
        qp_week = weeks[0] if weeks else 1
    with week_col:
        st.caption("Week")
        week = st.selectbox("Week", weeks, index=weeks.index(qp_week), label_visibility="collapsed")

    page_id = {"Week board": "week", "Teams": "teams", "Injuries": "injuries"}[page]
    url_season = str(qp.get("season", ""))
    url_week = str(qp.get("week", ""))
    url_page = str(qp.get("page", "week") or "week")
    if str(season) != url_season or str(week) != url_week or page_id != url_page:
        game_keep = qp.get("game") if str(season) == url_season and str(week) == url_week and page_id == "week" else None
        _set_view(season, week, game_keep, qp.get("view") if game_keep else None, page=page_id)
        st.rerun()

    try:
        cards = _cards(season, week)
    except Exception as exc:
        st.exception(exc)
        return
    if not cards:
        st.warning("No games for that week.")
        return

    by_id = {c.get("game_id"): c for c in cards}
    game_id = qp.get("game") if page_id == "week" else None
    view = qp.get("view")
    selected = by_id.get(game_id)

    if page_id == "teams":
        _render_teams_page(season, week)
        return
    if page_id == "injuries":
        _render_league_injuries(cards, season, week)
        return

    if selected:
        back, _ = st.columns([1, 6])
        if back.button("← Week board"):
            _set_view(season, week, page="week")
            st.rerun()
        title = f"{selected['away_team']} @ {selected['home_team']}"
        if selected.get("away_score") is not None and selected.get("home_score") is not None:
            title += f"  ({int(selected['away_score'])}–{int(selected['home_score'])})"
        st.subheader(title)
        which = st.radio(
            "section",
            ["Matchup", "Injuries"],
            index=1 if view == "injuries" else 0,
            horizontal=True,
            label_visibility="collapsed",
        )
        if which == "Injuries":
            render_injuries(selected)
        else:
            render_card(selected)
        return

    st.markdown(f"**{season} week {week}**")
    _render_board(cards, season, week)
    st.caption(
        "When is kickoff in Pacific time. Injuries shows listed OUT and Questionable counts; "
        "click for the full report. Hover Win% for nfelo vs moneyline."
    )


if __name__ == "__main__":
    main()
