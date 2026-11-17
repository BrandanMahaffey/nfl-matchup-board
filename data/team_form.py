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
    "fg_made",
    "fg_att",
    "pat_made",
    "pat_att",
    "pt_net_yards",
    "pt_att",
    "pt_inside_20",
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
    "fg_made",
    "fg_att",
    "fg_pct",
    "pat_made",
    "pat_att",
    "pat_pct",
    "punt_net_avg",
    "pt_inside_20",
    "pt_att",
    "inside_20_pct",
    "punt_return_yards",
    "kickoff_return_yards",
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
        "fg_made",
        "fg_att",
        "pat_made",
        "pat_att",
        "pt_net_yards",
        "pt_att",
        "pt_inside_20",
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
        pl.col("fg_made").sum(),
        pl.col("fg_att").sum(),
        pl.col("pat_made").sum(),
        pl.col("pat_att").sum(),
        pl.col("pt_net_yards").sum().alias("pt_net_yards"),
        pl.col("pt_att").sum().alias("pt_att"),
        pl.col("pt_inside_20").sum(),
        pl.col("punt_return_yards").sum(),
        pl.col("kickoff_return_yards").sum(),
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
        pl.when(pl.col("fg_att") > 0)
        .then(pl.col("fg_made") / pl.col("fg_att"))
        .otherwise(None)
        .alias("fg_pct"),
        pl.when(pl.col("pat_att") > 0)
        .then(pl.col("pat_made") / pl.col("pat_att"))
        .otherwise(None)
        .alias("pat_pct"),
        pl.when(pl.col("pt_att") > 0)
        .then(pl.col("pt_inside_20") / pl.col("pt_att"))
        .otherwise(None)
        .alias("inside_20_pct"),
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


_ADJ_COLS = [
    "team",
    "games",
    "adj_off_epa_pg",
    "adj_def_epa_pg",
    "adj_net_epa_pg",
    "adj_pass_epa_pg",
    "adj_rush_epa_pg",
    "adj_pass_epa_allowed_pg",
    "adj_rush_epa_allowed_pg",
    "off_epa_pg",
    "def_epa_pg",
    "sos_off",
    "sos_def",
]


# Games of opponent evidence before the observed unit is trusted as much as
# league average. k=4 is the usual public-analytics prior (rbsdm-style).
_ADJ_SHRINK_K = 4.0


def opponent_adjusted_epa(
    game_rows: pl.DataFrame, through_week: int | None = None
) -> pl.DataFrame:
    """Public-analytics Adjusted EPA from nflverse team-week EPA.

    For each game:

        Adj Off = Off EPA - (Opp Def - League Off)
        Adj Def = Def EPA allowed - (Opp Off - League Off)

    Opponent means are leave-one-out (the game being scored is dropped) and
    shrunk toward league average: weight = n / (n + 4). That is schedule-
    adjusted EPA, not PFF Adjusted EPA or Football Outsiders DVOA.
    """
    empty = pl.DataFrame({c: [] for c in _ADJ_COLS})
    if game_rows is None or game_rows.is_empty():
        return empty
    rows = game_rows.filter(pl.col("points_for").is_not_null())
    if through_week is not None:
        rows = rows.filter(pl.col("week") <= through_week)
    needed = [
        "team",
        "opponent_team",
        "off_epa",
        "def_epa_allowed",
        "pass_epa",
        "rush_epa",
        "pass_epa_allowed",
        "rush_epa_allowed",
    ]
    if rows.is_empty() or any(col not in rows.columns for col in needed):
        return empty

    def _mean(col: str) -> float:
        series = rows.get_column(col).drop_nulls()
        if series.len() == 0:
            return 0.0
        return float(series.mean())

    league_off = _mean("off_epa")
    league_pass = _mean("pass_epa")
    league_rush = _mean("rush_epa")

    opp = rows.group_by("team").agg(
        pl.len().alias("_n"),
        pl.col("off_epa").sum().alias("_sum_off"),
        pl.col("def_epa_allowed").sum().alias("_sum_def"),
        pl.col("pass_epa").sum().alias("_sum_pass"),
        pl.col("rush_epa").sum().alias("_sum_rush"),
        pl.col("pass_epa_allowed").sum().alias("_sum_pass_d"),
        pl.col("rush_epa_allowed").sum().alias("_sum_rush_d"),
    ).rename({"team": "opponent_team"})

    work = rows.join(opp, on="opponent_team", how="left")

    def _loo(sum_col: str, this_col: str, league: float) -> pl.Expr:
        observed = (
            pl.when(pl.col("_n") > 1)
            .then((pl.col(sum_col) - pl.col(this_col).fill_null(0)) / (pl.col("_n") - 1))
            .otherwise(pl.lit(league))
        )
        n_loo = pl.when(pl.col("_n") > 1).then(pl.col("_n") - 1).otherwise(0)
        weight = n_loo.cast(pl.Float64) / (n_loo.cast(pl.Float64) + _ADJ_SHRINK_K)
        return weight * observed + (1.0 - weight) * league

    work = work.with_columns(
        _loo("_sum_def", "off_epa", league_off).alias("opp_def"),
        _loo("_sum_off", "def_epa_allowed", league_off).alias("opp_off"),
        _loo("_sum_pass_d", "pass_epa", league_pass).alias("opp_pass_d"),
        _loo("_sum_rush_d", "rush_epa", league_rush).alias("opp_rush_d"),
        _loo("_sum_pass", "pass_epa_allowed", league_pass).alias("opp_pass"),
        _loo("_sum_rush", "rush_epa_allowed", league_rush).alias("opp_rush"),
    ).with_columns(
        (pl.col("off_epa") - (pl.col("opp_def") - league_off)).alias("adj_off"),
        (pl.col("def_epa_allowed") - (pl.col("opp_off") - league_off)).alias("adj_def"),
        (pl.col("pass_epa") - (pl.col("opp_pass_d") - league_pass)).alias("adj_pass"),
        (pl.col("rush_epa") - (pl.col("opp_rush_d") - league_rush)).alias("adj_rush"),
        (pl.col("pass_epa_allowed") - (pl.col("opp_pass") - league_pass)).alias("adj_pass_d"),
        (pl.col("rush_epa_allowed") - (pl.col("opp_rush") - league_rush)).alias("adj_rush_d"),
    )

    return (
        work.group_by("team")
        .agg(
            pl.len().alias("games"),
            pl.col("adj_off").mean().alias("adj_off_epa_pg"),
            pl.col("adj_def").mean().alias("adj_def_epa_pg"),
            pl.col("adj_pass").mean().alias("adj_pass_epa_pg"),
            pl.col("adj_rush").mean().alias("adj_rush_epa_pg"),
            pl.col("adj_pass_d").mean().alias("adj_pass_epa_allowed_pg"),
            pl.col("adj_rush_d").mean().alias("adj_rush_epa_allowed_pg"),
            pl.col("off_epa").mean().alias("off_epa_pg"),
            pl.col("def_epa_allowed").mean().alias("def_epa_pg"),
            pl.col("opp_def").mean().alias("sos_off"),
            pl.col("opp_off").mean().alias("sos_def"),
        )
        .with_columns(
            (pl.col("adj_off_epa_pg") - pl.col("adj_def_epa_pg")).alias("adj_net_epa_pg")
        )
        .select(_ADJ_COLS)
    )
