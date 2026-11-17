"""Special-teams units from nflverse play-by-play.

The team-week file has net punting and return yards gained, but not kickoff
coverage or ST turnovers. Play-by-play fills those in:

- Kickoff yards = kickoff-return yards minus kickoff-return yards allowed
- Punt yards = punt-return yards minus punt-return yards allowed
- ST turnovers = muffs / lost fumbles / blocked kicks
- ST EPA = expected points on kickoffs, punts, field goals, and extra points,
  from each club's side of the ball (zero-sum across the league)
"""

from __future__ import annotations

from typing import Any

import polars as pl

from data.io import DataLoadError, load_csv, load_parquet
from data.teamref import canonical

RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"

_PBP_COLS = [
    "week",
    "season_type",
    "game_id",
    "posteam",
    "defteam",
    "play_type",
    "epa",
    "return_yards",
    "kick_distance",
    "touchback",
    "fumble",
    "fumble_lost",
    "fumbled_1_team",
    "fumble_recovery_1_team",
    "punt_blocked",
    "field_goal_result",
    "extra_point_result",
    "own_kickoff_recovery",
    "interception",
    "return_touchdown",
    "td_team",
]

_ST_TYPES = ("kickoff", "punt", "field_goal", "extra_point")


def _empty_units() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "team": pl.Utf8,
            "st_epa": pl.Float64,
            "st_epa_pg": pl.Float64,
            "ko_epa": pl.Float64,
            "punt_epa": pl.Float64,
            "fg_epa": pl.Float64,
            "kr_yards": pl.Float64,
            "kr_allowed": pl.Float64,
            "ko_yards": pl.Float64,
            "ko_yards_pg": pl.Float64,
            "ko_yards_pk": pl.Float64,
            "pr_yards": pl.Float64,
            "pr_allowed": pl.Float64,
            "punt_yards": pl.Float64,
            "punt_yards_pg": pl.Float64,
            "punt_yards_pp": pl.Float64,
            "st_to_given": pl.Float64,
            "st_to_taken": pl.Float64,
            "st_to_diff": pl.Float64,
            "st_tds_pbp": pl.Float64,
            "games_st": pl.Float64,
        }
    )


def load_st_pbp(season: int) -> pl.DataFrame:
    """Regular-season special-teams plays for ``season``."""
    parquet = f"{RELEASE}/pbp/play_by_play_{season}.parquet"
    try:
        raw = load_parquet(parquet)
    except DataLoadError:
        raw = load_csv(f"{RELEASE}/pbp/play_by_play_{season}.csv.gz")
    if raw.is_empty():
        return pl.DataFrame()

    present = [c for c in _PBP_COLS if c in raw.columns]
    if not {"week", "posteam", "defteam", "play_type"}.issubset(present):
        return pl.DataFrame()
    work = raw.select(present)
    if "season_type" in work.columns:
        work = work.filter(pl.col("season_type") == "REG")
    work = work.filter(
        pl.col("play_type").is_in(list(_ST_TYPES)),
        pl.col("posteam").is_not_null(),
        pl.col("defteam").is_not_null(),
    )
    for col, dtype in (
        ("epa", pl.Float64),
        ("return_yards", pl.Float64),
        ("kick_distance", pl.Float64),
        ("punt_blocked", pl.Float64),
        ("interception", pl.Float64),
        ("own_kickoff_recovery", pl.Float64),
        ("return_touchdown", pl.Float64),
        ("fumble", pl.Float64),
        ("fumble_lost", pl.Float64),
    ):
        if col not in work.columns:
            work = work.with_columns(pl.lit(None).cast(dtype).alias(col))
        else:
            work = work.with_columns(pl.col(col).cast(dtype, strict=False))
    for col in (
        "fumbled_1_team",
        "fumble_recovery_1_team",
        "td_team",
        "field_goal_result",
        "extra_point_result",
    ):
        if col not in work.columns:
            work = work.with_columns(pl.lit(None).cast(pl.Utf8).alias(col))

    def _canon(val: object) -> str | None:
        if val is None:
            return None
        key = canonical(str(val))
        return key or None

    return work.with_columns(
        pl.col("posteam").map_elements(_canon, return_dtype=pl.Utf8),
        pl.col("defteam").map_elements(_canon, return_dtype=pl.Utf8),
        pl.col("fumbled_1_team").map_elements(_canon, return_dtype=pl.Utf8),
        pl.col("fumble_recovery_1_team").map_elements(_canon, return_dtype=pl.Utf8),
        pl.col("td_team").map_elements(_canon, return_dtype=pl.Utf8),
        pl.col("epa").fill_null(0.0),
        pl.col("return_yards").fill_null(0.0),
    )


def _with_turnovers(plays: pl.DataFrame) -> pl.DataFrame:
    blocked = (pl.col("play_type") == "punt") & (pl.col("punt_blocked").fill_null(0) == 1)
    fumble_to = (
        pl.col("fumbled_1_team").is_not_null()
        & pl.col("fumble_recovery_1_team").is_not_null()
        & (pl.col("fumbled_1_team") != pl.col("fumble_recovery_1_team"))
    )
    intercepted = pl.col("interception").fill_null(0) == 1
    return plays.with_columns(
        pl.when(blocked)
        .then(pl.col("posteam"))
        .when(fumble_to)
        .then(pl.col("fumbled_1_team"))
        .when(intercepted)
        .then(pl.col("posteam"))
        .otherwise(None)
        .alias("to_from"),
        pl.when(blocked)
        .then(pl.col("defteam"))
        .when(fumble_to)
        .then(pl.col("fumble_recovery_1_team"))
        .when(intercepted)
        .then(pl.col("defteam"))
        .otherwise(None)
        .alias("to_to"),
    )


def _side(plays: pl.DataFrame, team_col: str, sign: int) -> pl.DataFrame:
    """One row per play from ``team_col``'s point of view."""
    team = pl.col(team_col)
    is_kickoff = pl.col("play_type") == "kickoff"
    is_punt = pl.col("play_type") == "punt"
    is_kick = pl.col("play_type").is_in(["field_goal", "extra_point"])
    kickoff_receiving = team == pl.col("defteam")
    punt_receiving = team == pl.col("posteam")
    # Kickoff: posteam is the kicking team; punt: posteam is the punting team.
    kr = pl.when(is_kickoff & kickoff_receiving).then(pl.col("return_yards")).otherwise(0.0)
    kr_all = pl.when(is_kickoff & ~kickoff_receiving).then(pl.col("return_yards")).otherwise(0.0)
    pr = pl.when(is_punt & ~punt_receiving).then(pl.col("return_yards")).otherwise(0.0)
    pr_all = pl.when(is_punt & punt_receiving).then(pl.col("return_yards")).otherwise(0.0)
    return plays.select(
        team.alias("team"),
        pl.col("game_id"),
        (pl.col("epa") * sign).alias("st_epa"),
        pl.when(is_kickoff).then(pl.col("epa") * sign).otherwise(0.0).alias("ko_epa"),
        pl.when(is_punt).then(pl.col("epa") * sign).otherwise(0.0).alias("punt_epa"),
        pl.when(is_kick).then(pl.col("epa") * sign).otherwise(0.0).alias("fg_epa"),
        kr.alias("kr_yards"),
        kr_all.alias("kr_allowed"),
        pr.alias("pr_yards"),
        pr_all.alias("pr_allowed"),
        pl.when(is_kickoff & kickoff_receiving).then(1.0).otherwise(0.0).alias("ko_recv"),
        pl.when(is_kickoff & ~kickoff_receiving).then(1.0).otherwise(0.0).alias("ko_made"),
        pl.when(is_punt & ~punt_receiving).then(1.0).otherwise(0.0).alias("pr_chances"),
        pl.when(is_punt & punt_receiving).then(1.0).otherwise(0.0).alias("punts"),
        pl.when(pl.col("to_from") == team).then(1.0).otherwise(0.0).alias("st_to_given"),
        pl.when(pl.col("to_to") == team).then(1.0).otherwise(0.0).alias("st_to_taken"),
        pl.when(pl.col("td_team") == team).then(1.0).otherwise(0.0).alias("st_tds_pbp"),
    )


def team_st_units(season: int, through_week: int | None = None) -> pl.DataFrame:
    """Per-team special-teams units through ``through_week`` (inclusive)."""
    plays = load_st_pbp(season)
    if plays.is_empty():
        return _empty_units()
    if through_week is not None:
        if through_week <= 0:
            return _empty_units()
        plays = plays.filter(pl.col("week") <= through_week)
    if plays.is_empty():
        return _empty_units()

    plays = _with_turnovers(plays)
    rows = pl.concat(
        [
            _side(plays, "posteam", 1),
            _side(plays, "defteam", -1),
        ]
    )
    rows = rows.filter(pl.col("team").is_not_null() & (pl.col("team") != ""))
    if rows.is_empty():
        return _empty_units()

    grouped = rows.group_by("team").agg(
        pl.col("game_id").n_unique().alias("games_st"),
        pl.col("st_epa").sum(),
        pl.col("ko_epa").sum(),
        pl.col("punt_epa").sum(),
        pl.col("fg_epa").sum(),
        pl.col("kr_yards").sum(),
        pl.col("kr_allowed").sum(),
        pl.col("pr_yards").sum(),
        pl.col("pr_allowed").sum(),
        pl.col("ko_recv").sum(),
        pl.col("ko_made").sum(),
        pl.col("pr_chances").sum(),
        pl.col("punts").sum(),
        pl.col("st_to_given").sum(),
        pl.col("st_to_taken").sum(),
        pl.col("st_tds_pbp").sum(),
    )
    kr_avg = pl.when(pl.col("ko_recv") > 0).then(pl.col("kr_yards") / pl.col("ko_recv")).otherwise(None)
    kr_all_avg = pl.when(pl.col("ko_made") > 0).then(pl.col("kr_allowed") / pl.col("ko_made")).otherwise(None)
    pr_avg = pl.when(pl.col("pr_chances") > 0).then(pl.col("pr_yards") / pl.col("pr_chances")).otherwise(None)
    pr_all_avg = pl.when(pl.col("punts") > 0).then(pl.col("pr_allowed") / pl.col("punts")).otherwise(None)
    return grouped.with_columns(
        (pl.col("kr_yards") - pl.col("kr_allowed")).alias("ko_yards"),
        (pl.col("pr_yards") - pl.col("pr_allowed")).alias("punt_yards"),
        (pl.col("st_to_taken") - pl.col("st_to_given")).alias("st_to_diff"),
        kr_avg.alias("kr_avg"),
        kr_all_avg.alias("kr_allowed_avg"),
        pr_avg.alias("pr_avg"),
        pr_all_avg.alias("pr_allowed_avg"),
        (kr_avg - kr_all_avg).alias("ko_yards_pk"),
        (pr_avg - pr_all_avg).alias("punt_yards_pp"),
    ).with_columns(
        pl.when(pl.col("games_st") > 0)
        .then(pl.col("st_epa") / pl.col("games_st"))
        .otherwise(None)
        .alias("st_epa_pg"),
        pl.when(pl.col("games_st") > 0)
        .then((pl.col("kr_yards") - pl.col("kr_allowed")) / pl.col("games_st"))
        .otherwise(None)
        .alias("ko_yards_pg"),
        pl.when(pl.col("games_st") > 0)
        .then((pl.col("pr_yards") - pl.col("pr_allowed")) / pl.col("games_st"))
        .otherwise(None)
        .alias("punt_yards_pg"),
    )


def team_st_unit_rows(season: int, through_week: int | None = None) -> list[dict[str, Any]]:
    df = team_st_units(season, through_week)
    if df.is_empty():
        return []
    return df.to_dicts()
