"""Join nflverse / nfelo / weather into per-game matchup cards."""

from __future__ import annotations

from typing import Any

import polars as pl

from data.nfelo import load_elo_snapshot, load_nfelo_games
from data.personnel import injury_flags, key_injuries, last_week_snaps, ol_dl_starters
from data.schedules import current_week as sched_current_week
from data.schedules import load_schedules
from data.team_form import (
    annotate_defense_and_scoring,
    load_team_week_stats,
    recent_form,
    season_totals,
)
from data.trench import team_ngs, team_pressure
from data.weather import weather_for_games

NFELO_TEAM = {"OAK": "LV", "SD": "LAC", "STL": "LA"}


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def _empty(*cols: str) -> pl.DataFrame:
    return pl.DataFrame(schema={c: pl.Utf8 for c in cols})


def _row(df: pl.DataFrame | None, team: str, col: str = "team") -> dict[str, Any]:
    if df is None or df.is_empty() or col not in df.columns:
        return {}
    hit = df.filter(pl.col(col) == team)
    if hit.is_empty():
        return {}
    return hit.to_dicts()[0]


def _num(row: dict, key: str, default: float | None = None) -> float | None:
    val = row.get(key, default)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _div(n: float | None, d: float | None) -> float | None:
    if n is None or d is None or d == 0:
        return None
    return n / d


def _pg(row: dict, total_key: str, games_key: str = "games", pg_key: str | None = None) -> float | None:
    if pg_key and row.get(pg_key) is not None:
        return _num(row, pg_key)
    return _div(_num(row, total_key), _num(row, games_key))


def _fmt(val: float | None, digits: int = 1, signed: bool = False) -> str:
    if val is None:
        return "—"
    if signed:
        return f"{val:+.{digits}f}"
    return f"{val:.{digits}f}"


def _pct(val: float | None) -> str:
    if val is None:
        return "—"
    if val > 1.5:
        return f"{val:.0f}%"
    return f"{100.0 * val:.0f}%"


def _rate_pct(val: float | None) -> float | None:
    if val is None:
        return None
    return val * 100.0 if abs(val) <= 1.5 else val


def _alias_team(team: str | None) -> str | None:
    if team is None:
        return None
    return NFELO_TEAM.get(team, team)


def format_spread(spread: float | None, home: str, away: str) -> str:
    """2026 nflverse files list a positive home spread as home favored."""
    if spread is None:
        return "—"
    if spread == 0:
        return "PK"
    if spread > 0:
        return f"{home} -{spread:g}"
    return f"{away} {spread:g}"


def current_week(season: int) -> int:
    schedules = load_schedules(season)
    return sched_current_week(schedules)


def available_weeks(season: int) -> list[int]:
    schedules = load_schedules(season)
    if schedules.is_empty() or "week" not in schedules.columns:
        return [1]
    weeks = (
        schedules.filter(pl.col("game_type") == "REG")
        .get_column("week")
        .unique()
        .sort()
        .to_list()
    )
    return [int(w) for w in weeks] or [1]


def _prep_form(season: int, week: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    schedules = load_schedules(season)
    stats = _safe(lambda: load_team_week_stats(season), pl.DataFrame())
    if stats is None or stats.is_empty():
        return pl.DataFrame(), pl.DataFrame()
    games = _safe(lambda: annotate_defense_and_scoring(stats, schedules), pl.DataFrame())
    through = week - 1 if week > 1 else 0
    season_df = _safe(lambda: season_totals(games, through_week=through), pl.DataFrame())
    recent_df = _safe(lambda: recent_form(games, n=3, through_week=through), pl.DataFrame())
    return season_df, recent_df


def _agg_by_team(df: pl.DataFrame, through: int, means: list[str], sums: list[str]) -> pl.DataFrame:
    if df is None or df.is_empty() or "team" not in df.columns:
        return pl.DataFrame()
    work = df
    if "week" in work.columns and through is not None:
        work = work.filter(pl.col("week") <= through)
    if work.is_empty():
        return pl.DataFrame()
    aggs = []
    for c in means:
        if c in work.columns:
            aggs.append(pl.col(c).mean().alias(c))
    for c in sums:
        if c in work.columns:
            aggs.append(pl.col(c).sum().alias(c))
    if not aggs:
        return pl.DataFrame()
    return work.group_by("team").agg(aggs)


def _ol_line(starters: pl.DataFrame, team: str, unit: str) -> str:
    if starters is None or starters.is_empty():
        return "—"
    rows = starters.filter((pl.col("team") == team) & (pl.col("unit") == unit))
    if rows.is_empty():
        return "—"
    order_ol = ["LT", "LG", "C", "RG", "RT"]
    order_dl = ["LDE", "LDT", "NT", "RDT", "RDE", "LOLB", "ROLB", "DE", "DT", "EDGE"]
    order = order_ol if unit == "ol" else order_dl
    by_pos: dict[str, str] = {}
    extras: list[str] = []
    for r in rows.to_dicts():
        pos = str(r.get("pos_abb") or "")
        name = str(r.get("player_name") or "").split(" ")[-1]
        label = f"{pos} {name}".strip()
        if pos in by_pos:
            extras.append(label)
        else:
            by_pos[pos] = label
    ordered = [by_pos[p] for p in order if p in by_pos]
    rest = [by_pos[p] for p in by_pos if p not in order] + extras
    return " · ".join(ordered + rest) or "—"


def _snap_line(snaps: pl.DataFrame, team: str, side: str) -> str:
    if snaps is None or snaps.is_empty() or "team" not in snaps.columns:
        return ""
    sub = snaps.filter(pl.col("team") == team)
    if sub.is_empty():
        return ""
    pct_col = "offense_pct" if side == "off" else "defense_pct"
    if pct_col not in sub.columns:
        return ""
    ranked = sub.sort(pct_col, descending=True).head(6)
    parts = []
    for r in ranked.to_dicts():
        name = str(r.get("player") or "").split(" ")[-1]
        pct = r.get(pct_col)
        if pct is None or not name:
            continue
        n = float(pct)
        if n <= 1.5:
            n *= 100.0
        parts.append(f"{name} {n:.0f}%")
    return " · ".join(parts)

def _inj_text(inj: pl.DataFrame, team: str) -> str:
    if inj is None or inj.is_empty() or "team" not in inj.columns:
        return ""
    sub = inj.filter(pl.col("team") == team)
    if sub.is_empty():
        return ""
    try:
        return injury_flags(sub) or ""
    except Exception:
        return ""


def _mismatch(home: dict, away: dict, home_key: str, away_key: str, pg: bool = True) -> float | None:
    if pg:
        hv = _pg(home, home_key, pg_key=home_key if home_key.endswith("_pg") else None)
        if hv is None:
            hv = _pg(home, home_key)
        av = _pg(away, away_key, pg_key=away_key if away_key.endswith("_pg") else None)
        if av is None:
            av = _pg(away, away_key)
        return None if hv is None or av is None else hv - av
    hv = _num(home, home_key)
    av = _num(away, away_key)
    if hv is None or av is None:
        return None
    return hv - av


def _unit_block(home: dict, away: dict, press_h: dict, press_a: dict, ngs_h: dict, ngs_a: dict) -> dict[str, Any]:
    h_pass = _pg(home, "pass_epa", pg_key="pass_epa_pg")
    a_pass_d = _pg(away, "pass_epa_allowed", pg_key="pass_epa_allowed_pg")
    a_pass = _pg(away, "pass_epa", pg_key="pass_epa_pg")
    h_pass_d = _pg(home, "pass_epa_allowed", pg_key="pass_epa_allowed_pg")
    h_rush = _pg(home, "rush_epa", pg_key="rush_epa_pg")
    a_rush_d = _pg(away, "rush_epa_allowed", pg_key="rush_epa_allowed_pg")
    a_rush = _pg(away, "rush_epa", pg_key="rush_epa_pg")
    h_rush_d = _pg(home, "rush_epa_allowed", pg_key="rush_epa_allowed_pg")
    h_pf = _pg(home, "points_for", pg_key="points_for_pg")
    a_pa = _pg(away, "points_against", pg_key="points_against_pg")
    a_pf = _pg(away, "points_for", pg_key="points_for_pg")
    h_pa = _pg(home, "points_against", pg_key="points_against_pg")
    h_to = _pg(home, "to_diff", pg_key="to_diff_pg")
    a_to = _pg(away, "to_diff", pg_key="to_diff_pg")
    if h_to is None:
        h_to = _div(_num(home, "to_diff"), _num(home, "games"))
    if a_to is None:
        a_to = _div(_num(away, "to_diff"), _num(away, "games"))

    h_press_gen = _num(press_h, "pressures_generated")
    a_press_all = _num(press_a, "pressures_allowed")
    a_press_gen = _num(press_a, "pressures_generated")
    h_press_all = _num(press_h, "pressures_allowed")
    h_pr_pct = _rate_pct(_num(press_h, "pressure_pct_allowed"))
    a_pr_pct = _rate_pct(_num(press_a, "pressure_pct_allowed"))
    h_sacks_gen = _num(press_h, "sacks_generated")
    a_sacks_all = _num(press_a, "sacks_allowed")

    h_st = _num(home, "special_teams_tds")
    a_st = _num(away, "special_teams_tds")
    h_fg = _num(home, "fg_pct")
    a_fg = _num(away, "fg_pct")
    h_net = _num(home, "pt_net_yards")
    a_net = _num(away, "pt_net_yards")

    pass_h = None if h_pass is None or a_pass_d is None else h_pass - a_pass_d
    pass_a = None if a_pass is None or h_pass_d is None else a_pass - h_pass_d
    run_h = None if h_rush is None or a_rush_d is None else h_rush - a_rush_d
    run_a = None if a_rush is None or h_rush_d is None else a_rush - h_rush_d
    score_h = None if h_pf is None or a_pa is None else h_pf - a_pa
    score_a = None if a_pf is None or h_pa is None else a_pf - h_pa
    trench_h = None if h_press_gen is None or a_press_all is None else h_press_gen - a_press_all
    trench_a = None if a_press_gen is None or h_press_all is None else a_press_gen - h_press_all
    to_gap = None if h_to is None or a_to is None else h_to - a_to
    st_fg = None if h_fg is None or a_fg is None else h_fg - a_fg

    return {
        "pass_home": pass_h,
        "pass_away": pass_a,
        "run_home": run_h,
        "run_away": run_a,
        "score_home": score_h,
        "score_away": score_a,
        "to_home": h_to,
        "to_away": a_to,
        "to_gap": to_gap,
        "trench_home": trench_h,
        "trench_away": trench_a,
        "press_pct_home": h_pr_pct,
        "press_pct_away": a_pr_pct,
        "sacks_edge_home": None if h_sacks_gen is None or a_sacks_all is None else h_sacks_gen - a_sacks_all,
        "st_tds_home": h_st,
        "st_tds_away": a_st,
        "fg_gap": st_fg,
        "fg_home": h_fg,
        "fg_away": a_fg,
        "punt_net_home": h_net,
        "punt_net_away": a_net,
        "off_epa_pg_home": _pg(home, "off_epa", pg_key="off_epa_pg"),
        "off_epa_pg_away": _pg(away, "off_epa", pg_key="off_epa_pg"),
        "def_epa_pg_home": _pg(home, "def_epa_allowed", pg_key="def_epa_pg"),
        "def_epa_pg_away": _pg(away, "def_epa_allowed", pg_key="def_epa_pg"),
        "cpoe_home": _num(home, "passing_cpoe"),
        "cpoe_away": _num(away, "passing_cpoe"),
        "ttt_home": _num(ngs_h, "ttt"),
        "ttt_away": _num(ngs_a, "ttt"),
        "ryoe_home": _num(ngs_h, "ryoe"),
        "ryoe_away": _num(ngs_a, "ryoe"),
        "h_pass": h_pass,
        "a_pass_d": a_pass_d,
        "a_pass": a_pass,
        "h_pass_d": h_pass_d,
        "h_rush": h_rush,
        "a_rush_d": a_rush_d,
        "a_rush": a_rush,
        "h_rush_d": h_rush_d,
        "h_pf": h_pf,
        "a_pa": a_pa,
        "a_pf": a_pf,
        "h_pa": h_pa,
        "h_press_gen": h_press_gen,
        "a_press_all": a_press_all,
        "a_press_gen": a_press_gen,
        "h_press_all": h_press_all,
        "top_rushers_home": press_h.get("top_rushers") or "",
        "top_rushers_away": press_a.get("top_rushers") or "",
    }


def _standouts(units: dict[str, Any], home: str, away: str) -> list[str]:
    flags: list[tuple[float, str]] = []
    checks = [
        (units.get("pass_home"), 4.0, f"{home} pass vs {away} pass D"),
        (units.get("pass_away"), 4.0, f"{away} pass vs {home} pass D"),
        (units.get("run_home"), 2.5, f"{home} run vs {away} run D"),
        (units.get("run_away"), 2.5, f"{away} run vs {home} run D"),
        (units.get("score_home"), 6.0, f"{home} scoring vs {away} allowed"),
        (units.get("score_away"), 6.0, f"{away} scoring vs {home} allowed"),
        (units.get("to_gap"), 0.6, f"{home} TO margin vs {away}"),
        (units.get("fg_gap"), 0.15, f"{home} FG% vs {away}"),
    ]
    for val, thresh, label in checks:
        if val is None or abs(val) < thresh:
            continue
        flags.append((abs(val), f"{label} {_fmt(val, 1, signed=True)}"))
    flags.sort(reverse=True)
    return [t for _, t in flags[:4]]


def _confidence(game: dict, nfelo_g: dict) -> dict[str, Any]:
    nfelo_pct = _num(nfelo_g, "nfelo_home_win_pct")
    ml_pct = _num(game, "home_ml_win_pct")
    src = "nfelo" if nfelo_pct is not None else ("moneyline" if ml_pct is not None else None)
    win_pct = nfelo_pct if nfelo_pct is not None else ml_pct
    spread = _num(game, "spread_line")
    nfelo_line = _num(nfelo_g, "nfelo_home_line")
    return {
        "home_win_pct": win_pct,
        "win_pct_source": src,
        "spread_line": spread,
        "nfelo_home_line": nfelo_line,
        "home_ml_win_pct": ml_pct,
        "nfelo_home_win_pct": nfelo_pct,
        "total_line": _num(game, "total_line"),
    }


def build_week_board(season: int, week: int) -> list[dict[str, Any]]:
    schedules = load_schedules(season)
    if schedules.is_empty():
        return []
    week_games = schedules.filter(pl.col("week") == week)
    if "game_type" in week_games.columns:
        week_games = week_games.filter(pl.col("game_type").is_in(["REG", "WC", "DIV", "CON", "SB", "POST"]))
    if week_games.is_empty():
        return []

    teams = sorted(
        set(week_games.get_column("home_team").to_list())
        | set(week_games.get_column("away_team").to_list())
    )
    through = week - 1 if week > 1 else 0

    season_df, recent_df = _prep_form(season, week)
    elo = _safe(load_elo_snapshot, pl.DataFrame())
    if not elo.is_empty() and "team" in elo.columns:
        elo = elo.with_columns(pl.col("team").replace(NFELO_TEAM, default=pl.col("team")))
    nfelo_games = _safe(lambda: load_nfelo_games(season), pl.DataFrame())
    weather = _safe(lambda: weather_for_games(week_games), pl.DataFrame())
    inj = _safe(lambda: key_injuries(season, week, teams), pl.DataFrame())
    starters = _safe(lambda: ol_dl_starters(season, teams), pl.DataFrame())
    snaps = _safe(lambda: last_week_snaps(season, week, teams), pl.DataFrame())
    press = _safe(lambda: team_pressure(season), pl.DataFrame())
    ngs = _safe(lambda: team_ngs(season), pl.DataFrame())
    press_team = _agg_by_team(
        press,
        through,
        means=["pressure_pct_allowed"],
        sums=["pressures_allowed", "pressures_generated", "sacks_allowed", "sacks_generated", "hurries_generated"],
    )
    ngs_team = _agg_by_team(ngs, through, means=["ttt"], sums=["ryoe"])
    if not press.is_empty() and "top_rushers" in press.columns and "week" in press.columns:
        latest = (
            press.filter(pl.col("week") <= through)
            .sort("week")
            .group_by("team")
            .tail(1)
            .select(["team", "top_rushers"])
            if through > 0
            else pl.DataFrame()
        )
        if not latest.is_empty() and not press_team.is_empty():
            press_team = press_team.join(latest, on="team", how="left")

    cards: list[dict[str, Any]] = []
    for g in week_games.sort(["gameday", "gametime"]).to_dicts():
        home = g.get("home_team")
        away = g.get("away_team")
        h_form = _row(season_df, home)
        a_form = _row(season_df, away)
        h_rec = _row(recent_df, home)
        a_rec = _row(recent_df, away)
        h_elo = _row(elo, home)
        a_elo = _row(elo, away)
        nf_g = _row(nfelo_games, g.get("game_id"), col="game_id")
        wx = _row(weather, g.get("game_id"), col="game_id")
        units = _unit_block(
            h_form,
            a_form,
            _row(press_team, home),
            _row(press_team, away),
            _row(ngs_team, home),
            _row(ngs_team, away),
        )
        conf = _confidence(g, nf_g)
        standouts = _standouts(units, home, away)
        venue = g.get("venue") or ("outdoor" if g.get("roof") in {"outdoors", "open"} else "indoor")
        cards.append(
            {
                "game_id": g.get("game_id"),
                "season": season,
                "week": week,
                "gameday": str(g.get("gameday") or ""),
                "weekday": g.get("weekday") or "",
                "gametime": g.get("gametime") or "",
                "away_team": away,
                "home_team": home,
                "away_score": g.get("away_score"),
                "home_score": g.get("home_score"),
                "away_qb": g.get("away_qb_name") or "",
                "home_qb": g.get("home_qb_name") or "",
                "stadium": g.get("stadium") or "",
                "roof": g.get("roof") or "",
                "venue": venue,
                "temp": g.get("temp"),
                "wind": g.get("wind"),
                "wx_temp_f": wx.get("temp_f"),
                "wx_wind_mph": wx.get("wind_mph"),
                "wx_precip_in": wx.get("precip_in"),
                "weather_note": wx.get("weather_note") or "",
                "injuries_home": _inj_text(inj, home),
                "injuries_away": _inj_text(inj, away),
                "ol_home": _ol_line(starters, home, "ol"),
                "ol_away": _ol_line(starters, away, "ol"),
                "dl_home": _ol_line(starters, home, "dl"),
                "dl_away": _ol_line(starters, away, "dl"),
                "snaps_off_home": _snap_line(snaps, home, "off"),
                "snaps_off_away": _snap_line(snaps, away, "off"),
                "snaps_def_home": _snap_line(snaps, home, "def"),
                "snaps_def_away": _snap_line(snaps, away, "def"),
                "nfelo_home": _num(h_elo, "nfelo"),
                "nfelo_away": _num(a_elo, "nfelo"),
                "pts_vs_avg_home": _num(h_elo, "pts_vs_avg"),
                "pts_vs_avg_away": _num(a_elo, "pts_vs_avg"),
                "rec_off_epa_pg_home": _num(h_rec, "rec_off_epa_pg"),
                "rec_off_epa_pg_away": _num(a_rec, "rec_off_epa_pg"),
                "rec_def_epa_pg_home": _num(h_rec, "rec_def_epa_pg"),
                "rec_def_epa_pg_away": _num(a_rec, "rec_def_epa_pg"),
                "rec_to_diff_home": _num(h_rec, "rec_to_diff"),
                "rec_to_diff_away": _num(a_rec, "rec_to_diff"),
                "standouts": standouts,
                "standout_text": " · ".join(standouts),
                **conf,
                **{f"u_{k}": v for k, v in units.items()},
            }
        )
    return cards


def board_table(cards: list[dict[str, Any]]) -> pl.DataFrame:
    rows = []
    for c in cards:
        home = c["home_team"]
        away = c["away_team"]
        spread_txt = format_spread(c.get("spread_line"), home, away)
        wx = "indoor"
        if c.get("venue") == "outdoor":
            bits = []
            t = c.get("wx_temp_f") if c.get("wx_temp_f") is not None else c.get("temp")
            w = c.get("wx_wind_mph") if c.get("wx_wind_mph") is not None else c.get("wind")
            if t is not None:
                bits.append(f"{float(t):.0f}°F")
            if w is not None:
                bits.append(f"{float(w):.0f} mph")
            if c.get("wx_precip_in"):
                bits.append(f"{float(c['wx_precip_in']):.2f} in")
            wx = " ".join(bits) or (c.get("weather_note") or "outdoor")
        score = ""
        if c.get("home_score") is not None and c.get("away_score") is not None:
            score = f"{int(c['away_score'])}-{int(c['home_score'])}"
        rows.append(
            {
                "When": f"{c.get('gameday')} {c.get('gametime') or ''}".strip(),
                "Matchup": f"{away} @ {home}",
                "Score": score,
                "Spread": spread_txt,
                "Win%": _pct(c.get("home_win_pct")) + (f" {home}" if c.get("home_win_pct") is not None else ""),
                "Src": c.get("win_pct_source") or "—",
                "Venue": wx,
                "Key injuries": " | ".join(
                    x for x in [f"{away}: {c.get('injuries_away')}" if c.get("injuries_away") else "",
                                 f"{home}: {c.get('injuries_home')}" if c.get("injuries_home") else ""]
                    if x
                ),
                "Standouts": c.get("standout_text") or "",
            }
        )
    return pl.DataFrame(rows) if rows else pl.DataFrame()
