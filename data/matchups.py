"""Join nflverse / nfelo / weather into per-game matchup cards."""

from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from data.io import DataLoadError
from data.nfelo import load_elo_snapshot, load_nfelo_games
from data.personnel import (
    depth_starters,
    injury_records,
    key_injuries,
    last_week_snaps,
    starter_out_line,
)
from data.schedules import current_week as sched_current_week
from data.schedules import format_kickoff_pt, load_schedules
from data.team_form import (
    annotate_defense_and_scoring,
    load_team_week_stats,
    opponent_adjusted_epa,
    recent_form,
    season_totals,
)
from data.special_teams import team_st_unit_rows
from data.trench import team_ngs, team_pressure
from data.weather import weather_for_games

NFELO_TEAM = {"OAK": "LV", "SD": "LAC", "STL": "LA"}


def _safe(fn, default):
    try:
        return fn()
    except DataLoadError:
        return default


_EASTERN = ZoneInfo("America/New_York")


def _kickoff_utc(game: dict[str, Any]) -> datetime:
    raw_day = game.get("gameday")
    if isinstance(raw_day, datetime):
        day = raw_day.date()
    elif isinstance(raw_day, date):
        day = raw_day
    else:
        day = date.fromisoformat(str(raw_day)[:10])
    raw_time = game.get("gametime")
    if isinstance(raw_time, datetime):
        local = raw_time
        if local.tzinfo is None:
            local = local.replace(tzinfo=_EASTERN)
        return local.astimezone(timezone.utc)
    if isinstance(raw_time, time):
        kickoff = raw_time
    else:
        text = str(raw_time or "13:00").strip()
        try:
            kickoff = datetime.strptime(text, "%I:%M %p").time()
        except ValueError:
            kickoff = time.fromisoformat(text[:8])
    return datetime.combine(day, kickoff, tzinfo=_EASTERN).astimezone(timezone.utc)


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
    h_net = _num(home, "punt_net_avg")
    a_net = _num(away, "punt_net_avg")

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


def _standout_sentence(key: str, val: float, home: str, away: str) -> str:
    gap = _fmt(val, 1, signed=True)
    if key == "pass_home":
        if val > 0:
            return f"{home} passing attack is much stronger than {away} pass defense ({gap} EPA/g gap)"
        return f"{away} pass defense has the edge vs {home} passing ({gap} EPA/g gap)"
    if key == "pass_away":
        if val > 0:
            return f"{away} passing attack is much stronger than {home} pass defense ({gap} EPA/g gap)"
        return f"{home} pass defense has the edge vs {away} passing ({gap} EPA/g gap)"
    if key == "run_home":
        if val > 0:
            return f"{home} run game is much stronger than {away} run defense ({gap} EPA/g gap)"
        return f"{away} run defense has the edge vs {home} rushing ({gap} EPA/g gap)"
    if key == "run_away":
        if val > 0:
            return f"{away} run game is much stronger than {home} run defense ({gap} EPA/g gap)"
        return f"{home} run defense has the edge vs {away} rushing ({gap} EPA/g gap)"
    if key == "score_home":
        if val > 0:
            return f"{home} scoring attack is much stronger than {away} defense usually allows ({gap} pts/g gap)"
        return f"{away} defense has the edge vs {home} scoring ({gap} pts/g gap)"
    if key == "score_away":
        if val > 0:
            return f"{away} scoring attack is much stronger than {home} defense usually allows ({gap} pts/g gap)"
        return f"{home} defense has the edge vs {away} scoring ({gap} pts/g gap)"
    if key == "to_gap":
        if val > 0:
            return f"{home} has a big turnover edge over {away} ({gap}/g)"
        return f"{away} has a big turnover edge over {home} ({gap}/g)"
    if key == "fg_gap":
        if val > 0:
            return f"{home} kicking has the edge over {away} ({gap} FG% gap)"
        return f"{away} kicking has the edge over {home} ({gap} FG% gap)"
    return f"{key} {gap}"


_STANDOUT_CHECKS = (
    ("pass_home", 4.0),
    ("pass_away", 4.0),
    ("run_home", 2.5),
    ("run_away", 2.5),
    ("score_home", 6.0),
    ("score_away", 6.0),
    ("to_gap", 0.6),
    ("fg_gap", 0.15),
)


def _standout_flags(units: dict[str, Any]) -> list[tuple[str, float]]:
    """Mismatches big enough to mention, largest first."""
    flags = [
        (key, float(units[key]))
        for key, thresh in _STANDOUT_CHECKS
        if units.get(key) is not None and abs(float(units[key])) >= thresh
    ]
    flags.sort(key=lambda kv: abs(kv[1]), reverse=True)
    return flags


def _standout_short(key: str, val: float, home: str, away: str) -> str:
    """Board-column version of a standout, e.g. ``BUF pass +15.5 EPA``."""
    mag = abs(val)
    if key in {"pass_home", "pass_away", "run_home", "run_away"}:
        facet = "pass" if key.startswith("pass") else "run"
        offense, defense = (home, away) if key.endswith("home") else (away, home)
        if val > 0:
            return f"{offense} {facet} +{mag:.1f} EPA"
        return f"{defense} {facet} defense +{mag:.1f} EPA"
    if key in {"score_home", "score_away"}:
        offense, defense = (home, away) if key.endswith("home") else (away, home)
        if val > 0:
            return f"{offense} scoring +{mag:.1f} pts"
        return f"{defense} defense +{mag:.1f} pts"
    if key == "to_gap":
        return f"{home if val > 0 else away} takeaways +{mag:.1f}/g"
    if key == "fg_gap":
        return f"{home if val > 0 else away} kicking +{100 * mag:.0f} FG%"
    return f"{key} {val:+.1f}"


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
    elo = _safe(lambda: load_elo_snapshot(season, week), pl.DataFrame())
    if not elo.is_empty() and "team" in elo.columns:
        elo = elo.with_columns(pl.col("team").replace(NFELO_TEAM, default=pl.col("team")))
    nfelo_games = _safe(lambda: load_nfelo_games(season), pl.DataFrame())
    weather = _safe(lambda: weather_for_games(week_games), pl.DataFrame())
    inj = _safe(lambda: key_injuries(season, week, teams), pl.DataFrame())
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
        cutoff = min(_kickoff_utc(g), datetime.now(timezone.utc))
        starters = _safe(
            lambda: depth_starters(season, teams, as_of=cutoff, week=week),
            pl.DataFrame(),
        )
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
        flags = _standout_flags(units)
        standouts = [_standout_sentence(k, v, home, away) for k, v in flags[:4]]
        venue = g.get("venue") or ("outdoor" if g.get("roof") in {"outdoors", "open"} else "indoor")
        inj_home_rows = injury_records(inj, starters, snaps, home)
        inj_away_rows = injury_records(inj, starters, snaps, away)
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
                "kickoff_pt": format_kickoff_pt(g.get("gameday"), g.get("gametime")),
                "injuries_out_home": starter_out_line(inj_home_rows),
                "injuries_out_away": starter_out_line(inj_away_rows),
                "injuries_home_rows": inj_home_rows,
                "injuries_away_rows": inj_away_rows,
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
                "standout_short": _standout_short(*flags[0], home, away) if flags else "",
                **conf,
                **{f"u_{k}": v for k, v in units.items()},
            }
        )
    return cards


def league_team_rows(season: int, week: int) -> list[dict[str, Any]]:
    """Season-to-date team form through the week before ``week``."""
    season_df, _recent = _prep_form(season, week)
    elo = _safe(lambda: load_elo_snapshot(season, week), pl.DataFrame())
    if season_df is None or season_df.is_empty():
        return []
    rows = []
    for r in season_df.to_dicts():
        team = r.get("team")
        e = _row(elo, team) if elo is not None else {}
        rows.append(
            {
                "Team": team,
                "nfelo": _num(e, "nfelo"),
                "Pts vs avg": _num(e, "pts_vs_avg"),
                "Off EPA/g": _pg(r, "off_epa", pg_key="off_epa_pg"),
                "Def EPA/g": _pg(r, "def_epa_allowed", pg_key="def_epa_pg"),
                "PF/g": _pg(r, "points_for", pg_key="points_for_pg"),
                "PA/g": _pg(r, "points_against", pg_key="points_against_pg"),
                "TO": _num(r, "to_diff"),
                "CPOE": _num(r, "passing_cpoe"),
                "Games": _num(r, "games"),
            }
        )
    rows.sort(key=lambda x: (-(x["nfelo"] or -1e9)))
    return rows


def league_adj_epa_rows(season: int, week: int) -> list[dict[str, Any]]:
    """Opponent-adjusted EPA/g through the week before ``week``."""
    schedules = load_schedules(season)
    stats = _safe(lambda: load_team_week_stats(season), pl.DataFrame())
    if stats is None or stats.is_empty():
        return []
    games = _safe(lambda: annotate_defense_and_scoring(stats, schedules), pl.DataFrame())
    through = week - 1 if week > 1 else 0
    adj = _safe(lambda: opponent_adjusted_epa(games, through_week=through), pl.DataFrame())
    if adj is None or adj.is_empty():
        return []
    rows = adj.to_dicts()
    rows.sort(
        key=lambda r: (
            -(r.get("adj_net_epa_pg") if r.get("adj_net_epa_pg") is not None else -1e9)
        )
    )
    return rows


def league_st_rows(season: int, week: int) -> list[dict[str, Any]]:
    """Special-teams season totals through the week before ``week``."""
    season_df, _recent = _prep_form(season, week)
    if season_df is None or season_df.is_empty():
        return []
    through = week - 1 if week > 1 else 0
    pbp = {r.get("team"): r for r in _safe(lambda: team_st_unit_rows(season, through), [])}
    rows = []
    for r in season_df.to_dicts():
        team = r.get("team")
        extra = pbp.get(team) or {}
        fg_made = _num(r, "fg_made")
        fg_att = _num(r, "fg_att")
        rows.append(
            {
                "team": team,
                "fg_pct": _num(r, "fg_pct"),
                "fg_made": fg_made,
                "fg_att": fg_att,
                "pat_pct": _num(r, "pat_pct"),
                "punt_net_avg": _num(r, "punt_net_avg"),
                "inside_20_pct": _num(r, "inside_20_pct"),
                "punt_return_yards": _num(extra, "pr_yards", _num(r, "punt_return_yards")),
                "kickoff_return_yards": _num(extra, "kr_yards", _num(r, "kickoff_return_yards")),
                "kr_allowed": _num(extra, "kr_allowed"),
                "pr_allowed": _num(extra, "pr_allowed"),
                "ko_yards_pg": _num(extra, "ko_yards_pg"),
                "punt_yards_pg": _num(extra, "punt_yards_pg"),
                "ko_yards_pk": _num(extra, "ko_yards_pk"),
                "punt_yards_pp": _num(extra, "punt_yards_pp"),
                "kr_avg": _num(extra, "kr_avg"),
                "kr_allowed_avg": _num(extra, "kr_allowed_avg"),
                "pr_avg": _num(extra, "pr_avg"),
                "pr_allowed_avg": _num(extra, "pr_allowed_avg"),
                "st_epa_pg": _num(extra, "st_epa_pg"),
                "ko_epa": _num(extra, "ko_epa"),
                "punt_epa": _num(extra, "punt_epa"),
                "fg_epa": _num(extra, "fg_epa"),
                "st_to_given": _num(extra, "st_to_given"),
                "st_to_taken": _num(extra, "st_to_taken"),
                "st_to_diff": _num(extra, "st_to_diff"),
                "special_teams_tds": _num(r, "special_teams_tds"),
                "games": _num(r, "games"),
            }
        )
    rows.sort(
        key=lambda x: (
            -(x["st_epa_pg"] if x["st_epa_pg"] is not None else -1e9),
            -(x["special_teams_tds"] if x["special_teams_tds"] is not None else -1e9),
            -(x["fg_pct"] if x["fg_pct"] is not None else -1e9),
        )
    )
    return rows
