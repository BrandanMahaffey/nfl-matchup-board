"""Weekly NFL matchup board for a family football pool."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from data.matchups import available_weeks, board_table, build_week_board, current_week, format_spread

_ICON = Path(__file__).with_name("assets") / "nfl-board.png"
st.set_page_config(
    page_title="NFL Matchup Board",
    page_icon=str(_ICON) if _ICON.exists() else "🏈",
    layout="wide",
    menu_items={"About": "NFL Matchup Board — weekly pool comparison. Built with Streamlit."},
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


def render_card(c: dict):
    away, home = c["away_team"], c["home_team"]
    title = f"{away} @ {home}"
    if c.get("away_score") is not None and c.get("home_score") is not None:
        title += f"  ({int(c['away_score'])}–{int(c['home_score'])})"
    with st.expander(title, expanded=False):
        meta = " · ".join(
            x
            for x in [
                f"{c.get('weekday') or ''} {c.get('gameday')} {c.get('gametime') or ''}".strip(),
                c.get("stadium") or "",
                c.get("venue") or "",
                f"QB {c.get('away_qb') or '—'} / {c.get('home_qb') or '—'}",
            ]
            if x
        )
        st.caption(meta)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"{home} win%", _pct(c.get("home_win_pct")), c.get("win_pct_source") or "")
        spread_s = format_spread(c.get("spread_line"), home, away)
        c2.metric("Spread", spread_s, f"nfelo {_fmt(c.get('nfelo_home_line'), 1, True)}" if c.get("nfelo_home_line") is not None else "market")
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
        i1.markdown(f"**{away} injuries**  \n{c.get('injuries_away') or 'none flagged'}")
        i2.markdown(f"**{home} injuries**  \n{c.get('injuries_home') or 'none flagged'}")

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


def main():
    st.title("NFL Matchup Board")
    st.caption(
        "Join-first weekly board · nflverse + PFR pressure + NGS + nfelo (else moneyline) + outdoor weather. "
        "Context for the pool, not predicted scores."
    )
    season = st.sidebar.selectbox("Season", [2026, 2025, 2024], index=0)
    try:
        weeks = _weeks(season)
        default_week = current_week(season)
        if default_week not in weeks:
            default_week = weeks[0]
        week = st.sidebar.selectbox("Week", weeks, index=weeks.index(default_week))
    except Exception as exc:
        st.error(f"Could not load schedule: {exc}")
        return

    st.sidebar.markdown(
        "Private family app. Sources: nflverse GitHub releases, nfelo `output_data`, Open-Meteo. No PFF."
    )

    try:
        cards = _cards(season, week)
    except Exception as exc:
        st.exception(exc)
        return

    if not cards:
        st.warning("No games for that week.")
        return

    table = board_table(cards)
    st.subheader(f"{season} week {week}")
    st.dataframe(table, hide_index=True, width="stretch")
    st.markdown("### Game cards")
    for c in cards:
        render_card(c)


if __name__ == "__main__":
    main()
