"""Weekly NFL matchup board for a family football pool."""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from data.matchups import available_weeks, build_week_board, current_week, format_spread

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
      table.board a { color: #c8a24a; text-decoration: none; font-weight: 600; }
      table.board a:hover { text-decoration: underline; }
      .win { cursor: help; border-bottom: 1px dotted #6b7785; }
      .inj { color: #e8eef4; font-size: 0.88rem; line-height: 1.35; }
      .inj a { color: #e8eef4; font-weight: 500; }
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
def _cards(season: int, week: int):
    return build_week_board(season, week)


@st.cache_data(ttl=3600)
def _weeks(season: int):
    return available_weeks(season)


def _unit_row(label, home_val, away_val, gap, home, away, digits=1, signed_gap=True):
    return {
        "Unit": label,
        away: _fmt(away_val, digits),
        home: _fmt(home_val, digits),
        "Gap (home view)": _fmt(gap, digits, signed=signed_gap),
    }


def _href(season: int, week: int, game: str | None = None, view: str | None = None) -> str:
    parts = [f"season={season}", f"week={week}"]
    if game:
        parts.append(f"game={html.escape(game, quote=True)}")
    if view:
        parts.append(f"view={html.escape(view, quote=True)}")
    return "?" + "&".join(parts)


def _set_view(season: int, week: int, game: str | None = None, view: str | None = None) -> None:
    params = {"season": str(season), "week": str(week)}
    if game:
        params["game"] = game
    if view:
        params["view"] = view
    st.query_params.clear()
    st.query_params.update(params)


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
    st.caption("Board column is starters listed as OUT. This table is the full report (OUT / Doubtful / Questionable).")
    st.dataframe(table, hide_index=True, width="stretch")
    o1, o2 = st.columns(2)
    o1.markdown(f"**{away} starters out**  \n{c.get('injuries_out_away') or 'none'}")
    o2.markdown(f"**{home} starters out**  \n{c.get('injuries_out_home') or 'none'}")


def render_card(c: dict):
    away, home = c["away_team"], c["home_team"]
    meta = " · ".join(
        x
        for x in [
            c.get("kickoff_pt") or "",
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
        t = c.get("wx_temp_f") if c.get("wx_temp_f") is not None else c.get("temp")
        w = c.get("wx_wind_mph") if c.get("wx_wind_mph") is not None else c.get("wind")
        p = c.get("wx_precip_in")
        st.info(
            "Weather: "
            + " · ".join(
                x
                for x in [
                    f"{float(t):.0f}°F" if t is not None else None,
                    f"{float(w):.0f} mph wind" if w is not None else None,
                    f"{float(p):.2f} in precip" if p else None,
                    c.get("weather_note") or None,
                ]
                if x
            )
            or "outdoor (no reading yet)"
        )

    if c.get("standouts"):
        st.markdown("**Standouts:** " + " · ".join(c["standouts"]))

    i1, i2 = st.columns(2)
    i1.markdown(f"**{away} starters out**  \n{c.get('injuries_out_away') or 'none'}")
    i2.markdown(f"**{home} starters out**  \n{c.get('injuries_out_home') or 'none'}")

    rows = [
        _unit_row("Pass EPA/g", c.get("u_h_pass"), c.get("u_a_pass"), c.get("u_pass_home"), home, away),
        _unit_row("Pass EPA allowed/g", c.get("u_h_pass_d"), c.get("u_a_pass_d"), c.get("u_pass_away"), home, away),
        _unit_row("Run EPA/g", c.get("u_h_rush"), c.get("u_a_rush"), c.get("u_run_home"), home, away),
        _unit_row("Run EPA allowed/g", c.get("u_h_rush_d"), c.get("u_a_rush_d"), c.get("u_run_away"), home, away),
        _unit_row("Points for/g", c.get("u_h_pf"), c.get("u_a_pf"), c.get("u_score_home"), home, away),
        _unit_row("Points allowed/g", c.get("u_h_pa"), c.get("u_a_pa"), c.get("u_score_away"), home, away),
        _unit_row("TO margin/g", c.get("u_to_home"), c.get("u_to_away"), c.get("u_to_gap"), home, away, digits=2),
        _unit_row("Pressures generated", c.get("u_h_press_gen"), c.get("u_a_press_gen"), c.get("u_trench_home"), home, away, digits=0),
        _unit_row("Pressures allowed", c.get("u_h_press_all"), c.get("u_a_press_all"), c.get("u_trench_away"), home, away, digits=0),
        _unit_row("Pressure % allowed", c.get("u_press_pct_home"), c.get("u_press_pct_away"), None, home, away, digits=1),
        _unit_row("Off EPA/g", c.get("u_off_epa_pg_home"), c.get("u_off_epa_pg_away"), None, home, away),
        _unit_row("Def EPA/g (allowed)", c.get("u_def_epa_pg_home"), c.get("u_def_epa_pg_away"), None, home, away),
        _unit_row("CPOE", c.get("u_cpoe_home"), c.get("u_cpoe_away"), None, home, away, digits=1),
        _unit_row("Time to throw", c.get("u_ttt_home"), c.get("u_ttt_away"), None, home, away, digits=2),
        _unit_row("RYOE (sum)", c.get("u_ryoe_home"), c.get("u_ryoe_away"), None, home, away, digits=0),
        _unit_row("ST TDs", c.get("u_st_tds_home"), c.get("u_st_tds_away"), None, home, away, digits=0),
        _unit_row("FG%", c.get("u_fg_home"), c.get("u_fg_away"), c.get("u_fg_gap"), home, away, digits=2),
        _unit_row("Punt net yds", c.get("u_punt_net_home"), c.get("u_punt_net_away"), None, home, away, digits=1),
    ]
    st.dataframe(rows, hide_index=True, width="stretch")

    st.markdown(
        f"**OL {away}** {c.get('ol_away') or '—'}  \n"
        f"**DL {home}** {c.get('dl_home') or '—'}  \n"
        f"**OL {home}** {c.get('ol_home') or '—'}  \n"
        f"**DL {away}** {c.get('dl_away') or '—'}"
    )
    s1, s2 = st.columns(2)
    s1.markdown(
        f"**{away} last-week snaps (50%+)**  \n"
        f"off {c.get('snaps_off_away') or '—'}  \n"
        f"def {c.get('snaps_def_away') or '—'}"
    )
    s2.markdown(
        f"**{home} last-week snaps (50%+)**  \n"
        f"off {c.get('snaps_off_home') or '—'}  \n"
        f"def {c.get('snaps_def_home') or '—'}"
    )
    if c.get("u_top_rushers_home") or c.get("u_top_rushers_away"):
        st.caption(
            f"PFR rushers — {away}: {c.get('u_top_rushers_away') or '—'} · "
            f"{home}: {c.get('u_top_rushers_home') or '—'}"
        )
    r1, r2 = st.columns(2)
    r1.markdown(
        f"**{away} last 3** off EPA/g {_fmt(c.get('rec_off_epa_pg_away'))} · "
        f"def EPA/g {_fmt(c.get('rec_def_epa_pg_away'))} · "
        f"TO {_fmt(c.get('rec_to_diff_away'), 1, True)}"
    )
    r2.markdown(
        f"**{home} last 3** off EPA/g {_fmt(c.get('rec_off_epa_pg_home'))} · "
        f"def EPA/g {_fmt(c.get('rec_def_epa_pg_home'))} · "
        f"TO {_fmt(c.get('rec_to_diff_home'), 1, True)}"
    )


def _board_html(cards: list[dict], season: int, week: int) -> str:
    show_score = any(c.get("home_score") is not None and c.get("away_score") is not None for c in cards)
    head = ["When", "Matchup"]
    if show_score:
        head.append("Score")
    head += ["Spread", "Win%", "Venue", "Starters out"]
    thead = "".join(f"<th>{html.escape(h)}</th>" for h in head)
    body = []
    for c in cards:
        home, away = c["home_team"], c["away_team"]
        gid = c.get("game_id") or ""
        game_url = _href(season, week, gid)
        inj_url = _href(season, week, gid, "injuries")
        src = c.get("win_pct_source") or "unknown"
        win = _pct(c.get("home_win_pct"))
        if c.get("home_win_pct") is not None:
            win = f"{win} {html.escape(home)}"
        title = f"Win% from {src}"
        away_out = html.escape(c.get("injuries_out_away") or "—")
        home_out = html.escape(c.get("injuries_out_home") or "—")
        inj = (
            f'<div class="inj"><a href="{inj_url}" title="Open injury report">'
            f"{html.escape(away)} {away_out}<br>{html.escape(home)} {home_out}</a></div>"
        )
        cells = [
            html.escape(c.get("kickoff_pt") or ""),
            f'<a href="{game_url}">{html.escape(away)} @ {html.escape(home)}</a>',
        ]
        if show_score:
            score = ""
            if c.get("home_score") is not None and c.get("away_score") is not None:
                score = f"{int(c['away_score'])}–{int(c['home_score'])}"
            cells.append(html.escape(score))
        cells += [
            html.escape(format_spread(c.get("spread_line"), home, away)),
            f'<span class="win" title="{html.escape(title)}">{win}</span>',
            html.escape(
                _venue_text(c)
            ),
            inj,
        ]
        body.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    return (
        '<div class="board-wrap"><table class="board">'
        f"<thead><tr>{thead}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


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


def _game_grid(cards: list[dict], season: int, week: int, active: str | None) -> str:
    chips = []
    for c in cards:
        gid = c.get("game_id") or ""
        label = f"{c['away_team']} @ {c['home_team']}"
        cls = "active" if gid == active else ""
        chips.append(f'<a class="{cls}" href="{_href(season, week, gid)}">{html.escape(label)}</a>')
    return '<div class="game-grid">' + "".join(chips) + "</div>"


def main():
    qp = st.query_params
    seasons = [2026, 2025, 2024]
    try:
        qp_season = int(qp.get("season", 2026))
    except (TypeError, ValueError):
        qp_season = 2026
    if qp_season not in seasons:
        qp_season = 2026

    title_col, season_col, week_col = st.columns([6, 1.15, 1.15])
    with title_col:
        st.title("NFL Matchup Board")
        st.caption("Context for the pool, not predicted scores.")
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

    url_season = str(qp.get("season", ""))
    url_week = str(qp.get("week", ""))
    if str(season) != url_season or str(week) != url_week:
        same_week = str(season) == url_season and str(week) == url_week
        game_keep = qp.get("game") if same_week else None
        _set_view(season, week, game_keep, qp.get("view") if game_keep else None)
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
    game_id = qp.get("game")
    view = qp.get("view")
    selected = by_id.get(game_id)

    if selected:
        back, _ = st.columns([1, 6])
        if back.button("← Week board"):
            _set_view(season, week)
            st.rerun()
        title = f"{selected['away_team']} @ {selected['home_team']}"
        if selected.get("away_score") is not None and selected.get("home_score") is not None:
            title += f"  ({int(selected['away_score'])}–{int(selected['home_score'])})"
        st.subheader(title)
        st.markdown(_game_grid(cards, season, week, selected.get("game_id")), unsafe_allow_html=True)
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
    st.markdown(_game_grid(cards, season, week, None), unsafe_allow_html=True)
    st.markdown(_board_html(cards, season, week), unsafe_allow_html=True)
    st.caption("Hover Win% for the source (nfelo or moneyline). Click a matchup for the card, or starters out for the injury report.")


if __name__ == "__main__":
    main()
