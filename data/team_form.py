"""Weekly team stats, EPA annotations, and rolling form aggregates."""

from __future__ import annotations

import polars as pl

from data.io import load_csv


RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"

_GAME_OUTPUT_COLS = [
    "season",
    "week",
    "team",
    "game_id",
    "opponent_team",
    "off_epa",
    "pass_epa",
    "rush_epa",
    "def_epa_allowed",
    "pass_epa_allowed",
    "rush_epa_allowed",
    "points_for",
    "points_against",
    "to_given",
    "to_taken",
    "to_diff",
    "sacks_suffered",
    "def_sacks",
    "special_teams_tds",
    "fg_pct",
    "pt_net_yards",
    "pt_att",
    "punt_return_yards",
    "kickoff_return_yards",
    "passing_cpoe",
    "attempts",
    "carries",
]

_SEASON_TOTAL_COLS = [
    "team",
    "games",
    "off_epa",
    "off_epa_pg",
    "pass_epa",
    "pass_epa_pg",
    "rush_epa",
    "rush_epa_pg",
    "def_epa_allowed",
    "def_epa_pg",
    "pass_epa_allowed",
    "pass_epa_allowed_pg",
    "rush_epa_allowed",
    "rush_epa_allowed_pg",
    "points_for",
    "points_against",
    "points_for_pg",
    "points_against_pg",
    "to_diff",
    "sacks_suffered",
    "def_sacks",
    "special_teams_tds",
    "fg_pct",
    "punt_net_avg",
    "passing_cpoe",
]

_RECENT_COLS = [
    "team",
    "rec_games",
    "rec_off_epa_pg",
    "rec_def_epa_pg",
    "rec_points_for_pg",
    "rec_to_diff",
]


def load_team_week_stats(season: int) -> pl.DataFrame:
    url = f"{RELEASE}/stats_team/stats_team_week_{season}.csv"
    df = load_csv(url)
    if "season_type" in df.columns:
        df = df.filter(pl.col("season_type") == "REG")
    return df


def annotate_defense_and_scoring(
    week_stats: pl.DataFrame, schedules: pl.DataFrame
) -> pl.DataFrame:
    work = week_stats
    for col in (
        "passing_epa",
        "rushing_epa",
        "passing_interceptions",
        "def_interceptions",
        "fumbles_lost_total",
        "rushing_fumbles_lost",
        "sack_fumbles_lost",
        "fumble_recovery_opp",
        "sacks_suffered",
        "def_sacks",
        "special_teams_tds",
        "fg_pct",
        "pt_net_yards",
        "pt_att",
        "punt_return_yards",
        "kickoff_return_yards",
        "passing_cpoe",
        "attempts",
        "carries",
    ):
        if col not in work.columns:
            work = work.with_columns(pl.lit(None).cast(pl.Float64).alias(col))

    opp = work.select(
        "game_id",
        pl.col("team").alias("_opp_team"),
        pl.col("passing_epa").alias("pass_epa_allowed"),
        pl.col("rushing_epa").alias("rush_epa_allowed"),
    )

    home_pts = schedules.select(
        "game_id",
        pl.col("home_team").alias("team"),
        pl.col("home_score").alias("points_for"),
        pl.col("away_score").alias("points_against"),
    )
    away_pts = schedules.select(
        "game_id",
        pl.col("away_team").alias("team"),
        pl.col("away_score").alias("points_for"),
        pl.col("home_score").alias("points_against"),
    )
    points = pl.concat([home_pts, away_pts])

    fumbles_lost = pl.coalesce(
        pl.col("fumbles_lost_total"),
        pl.col("rushing_fumbles_lost").fill_null(0) + pl.col("sack_fumbles_lost").fill_null(0),
    )

    df = (
        work.join(
            opp,
            left_on=["game_id", "opponent_team"],
            right_on=["game_id", "_opp_team"],
            how="left",
        )
        .join(points, on=["game_id", "team"], how="left")
        .with_columns(
            pl.col("passing_epa").alias("pass_epa"),
            pl.col("rushing_epa").alias("rush_epa"),
            (pl.col("passing_epa").fill_null(0) + pl.col("rushing_epa").fill_null(0)).alias(
                "off_epa"
            ),
            (
                pl.col("pass_epa_allowed").fill_null(0)
                + pl.col("rush_epa_allowed").fill_null(0)
            ).alias("def_epa_allowed"),
            (pl.col("passing_interceptions").fill_null(0) + fumbles_lost.fill_null(0)).alias(
                "to_given"
            ),
            (
                pl.col("def_interceptions").fill_null(0)
                + pl.col("fumble_recovery_opp").fill_null(0)
            ).alias("to_taken"),
        )
        .with_columns((pl.col("to_taken") - pl.col("to_given")).alias("to_diff"))
    )

    return df.select(_GAME_OUTPUT_COLS)


def _aggregate_team_stats(rows: pl.DataFrame) -> pl.DataFrame:
    if rows.is_empty():
        return pl.DataFrame({c: [] for c in _SEASON_TOTAL_COLS})

    agg = rows.group_by("team").agg(
        pl.len().alias("games"),
        pl.col("off_epa").sum(),
        pl.col("pass_epa").sum(),
        pl.col("rush_epa").sum(),
        pl.col("def_epa_allowed").sum(),
        pl.col("pass_epa_allowed").sum(),
        pl.col("rush_epa_allowed").sum(),
        pl.col("points_for").sum(),
        pl.col("points_against").sum(),
        pl.col("to_diff").sum(),
        pl.col("sacks_suffered").sum(),
        pl.col("def_sacks").sum(),
        pl.col("special_teams_tds").sum(),
        pl.col("fg_pct").mean().alias("fg_pct"),
        pl.col("pt_net_yards").sum().alias("pt_net_yards"),
        pl.col("pt_att").sum().alias("pt_att"),
        pl.col("passing_cpoe").mean().alias("passing_cpoe"),
    )

    return agg.with_columns(
        (pl.col("off_epa") / pl.col("games")).alias("off_epa_pg"),
        (pl.col("def_epa_allowed") / pl.col("games")).alias("def_epa_pg"),
        (pl.col("pass_epa") / pl.col("games")).alias("pass_epa_pg"),
        (pl.col("rush_epa") / pl.col("games")).alias("rush_epa_pg"),
        (pl.col("pass_epa_allowed") / pl.col("games")).alias("pass_epa_allowed_pg"),
        (pl.col("rush_epa_allowed") / pl.col("games")).alias("rush_epa_allowed_pg"),
        (pl.col("points_for") / pl.col("games")).alias("points_for_pg"),
        (pl.col("points_against") / pl.col("games")).alias("points_against_pg"),
        # Yards per punt, not per game: punting a lot is a sign of a stalled offense.
        pl.when(pl.col("pt_att") > 0)
        .then(pl.col("pt_net_yards") / pl.col("pt_att"))
        .otherwise(None)
        .alias("punt_net_avg"),
    ).select(_SEASON_TOTAL_COLS)


def season_totals(
    game_rows: pl.DataFrame, through_week: int | None = None
) -> pl.DataFrame:
    rows = game_rows.filter(pl.col("points_for").is_not_null())
    if through_week is not None:
        rows = rows.filter(pl.col("week") <= through_week)
    return _aggregate_team_stats(rows)


def recent_form(
    game_rows: pl.DataFrame, n: int = 3, through_week: int | None = None
) -> pl.DataFrame:
    rows = game_rows.filter(pl.col("points_for").is_not_null())
    if through_week is not None:
        rows = rows.filter(pl.col("week") <= through_week)
    if rows.is_empty():
        return pl.DataFrame({c: [] for c in _RECENT_COLS})

    ranked = (
        rows.sort(["team", "week"], descending=[False, True])
        .with_columns(
            pl.col("week")
            .rank(method="ordinal", descending=True)
            .over("team")
            .alias("_rn")
        )
        .filter(pl.col("_rn") <= n)
        .drop("_rn")
    )

    totals = _aggregate_team_stats(ranked)
    return totals.select(
        "team",
        pl.col("games").alias("rec_games"),
        pl.col("off_epa_pg").alias("rec_off_epa_pg"),
        pl.col("def_epa_pg").alias("rec_def_epa_pg"),
        pl.col("points_for_pg").alias("rec_points_for_pg"),
        pl.col("to_diff").alias("rec_to_diff"),
    )
