"""PFR pressure and NGS trench metrics by team-week."""

from __future__ import annotations

import polars as pl

from data.io import load_csv
from data.teamref import canonical


RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"

_PRESSURE_COLS = [
    "week",
    "team",
    "pressure_pct_allowed",
    "pressures_allowed",
    "sacks_allowed",
    "pressures_generated",
    "sacks_generated",
    "hurries_generated",
    "top_rushers",
]

_NGS_COLS = ["week", "team", "ttt", "ryoe"]


def _empty_pressure() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "week": pl.Int64,
            "team": pl.String,
            "pressure_pct_allowed": pl.Float64,
            "pressures_allowed": pl.Float64,
            "sacks_allowed": pl.Float64,
            "pressures_generated": pl.Float64,
            "sacks_generated": pl.Float64,
            "hurries_generated": pl.Float64,
            "top_rushers": pl.String,
        }
    )


def _empty_ngs() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "week": pl.Int64,
            "team": pl.String,
            "ttt": pl.Float64,
            "ryoe": pl.Float64,
        }
    )


def _top_rushers_by_week_team(def_df: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for key, group in def_df.group_by(["week", "team"], maintain_order=True):
        week, team = key
        top = group.sort("def_pressures", descending=True).head(3)
        labels = [
            f"{r['pfr_player_name']} {int(r['def_pressures'] or 0)}"
            for r in top.iter_rows(named=True)
        ]
        rows.append({"week": week, "team": team, "top_rushers": ", ".join(labels)})
    if not rows:
        return pl.DataFrame(
            schema={"week": pl.Int64, "team": pl.String, "top_rushers": pl.String}
        )
    return pl.DataFrame(rows)


def team_pressure(season: int) -> pl.DataFrame:
    pass_url = f"{RELEASE}/pfr_advstats/advstats_week_pass_{season}.csv"
    def_url = f"{RELEASE}/pfr_advstats/advstats_week_def_{season}.csv"

    try:
        pass_df = load_csv(pass_url)
    except RuntimeError:
        return _empty_pressure()

    try:
        def_df = load_csv(def_url)
    except RuntimeError:
        def_df = pl.DataFrame()

    if pass_df.is_empty():
        return _empty_pressure()

    pass_df = pass_df.with_columns(
        pl.col("times_pressured").fill_null(0),
        pl.col("times_sacked").fill_null(0),
        pl.col("times_hurried").fill_null(0),
        pl.col("times_hit").fill_null(0),
    )

    # Pressure rate is retained from the most-pressured QB, while pressure
    # and sack counts represent every QB on the team for that week.
    qb_counts = pass_df.group_by(["week", "team"]).agg(
        pl.col("times_pressured").sum().alias("pressures_allowed"),
        pl.col("times_sacked").sum().alias("sacks_allowed"),
    )
    qb_rate = (
        pass_df.sort(["team", "week", "times_pressured"], descending=[False, False, True])
        .unique(subset=["team", "week"], keep="first")
        .select("week", "team", pl.col("times_pressured_pct").alias("pressure_pct_allowed"))
    )
    qb_week = qb_counts.join(qb_rate, on=["week", "team"], how="left").select(
        "week", "team", "pressures_allowed", "pressure_pct_allowed", "sacks_allowed"
    )

    if def_df.is_empty():
        return qb_week.with_columns(
            pl.lit(None).cast(pl.Float64).alias("pressures_generated"),
            pl.lit(None).cast(pl.Float64).alias("sacks_generated"),
            pl.lit(None).cast(pl.Float64).alias("hurries_generated"),
            pl.lit(None).cast(pl.String).alias("top_rushers"),
        ).select(_PRESSURE_COLS)


    def_df = def_df.with_columns(pl.col("def_pressures").fill_null(0))

    def_agg = def_df.group_by(["week", "team"]).agg(
        pl.col("def_pressures").sum().alias("pressures_generated"),
        pl.col("def_sacks").fill_null(0).sum().alias("sacks_generated"),
        pl.col("def_times_hurried").fill_null(0).sum().alias("hurries_generated"),
    )

    top_rushers = _top_rushers_by_week_team(def_df)

    return (
        qb_week.join(def_agg, on=["week", "team"], how="left")
        .join(top_rushers, on=["week", "team"], how="left")
        .select(_PRESSURE_COLS)
    )


def team_ngs(season: int) -> pl.DataFrame:
    pass_url = f"{RELEASE}/nextgen_stats/ngs_passing.csv.gz"
    rush_url = f"{RELEASE}/nextgen_stats/ngs_rushing.csv.gz"

    def _norm_team(df: pl.DataFrame) -> pl.DataFrame:
        if df.is_empty():
            return df
        if "team" not in df.columns and "team_abbr" in df.columns:
            df = df.rename({"team_abbr": "team"})
        if "team" not in df.columns:
            return df
        # Next Gen Stats still ships LAR where the schedule says LA.
        return df.with_columns(
            pl.col("team").cast(pl.Utf8).map_elements(canonical, return_dtype=pl.Utf8)
        )

    def _f64(df: pl.DataFrame, *cols: str) -> pl.DataFrame:
        present = [c for c in cols if c in df.columns]
        if not present:
            return df
        return df.with_columns([pl.col(c).cast(pl.Float64, strict=False) for c in present])

    try:
        pass_df = _f64(_norm_team(load_csv(pass_url)), "attempts", "pass_attempts", "avg_time_to_throw")
        if "season" in pass_df.columns:
            pass_df = pass_df.filter(pl.col("season") == season)
        if "season_type" in pass_df.columns:
            pass_df = pass_df.filter(pl.col("season_type") == "REG")
        if "week" in pass_df.columns:
            pass_df = pass_df.filter(pl.col("week") >= 1)
    except RuntimeError:
        pass_df = pl.DataFrame()

    try:
        rush_df = _f64(_norm_team(load_csv(rush_url)), "rush_yards_over_expected")
        if "season" in rush_df.columns:
            rush_df = rush_df.filter(pl.col("season") == season)
        if "season_type" in rush_df.columns:
            rush_df = rush_df.filter(pl.col("season_type") == "REG")
        if "week" in rush_df.columns:
            rush_df = rush_df.filter(pl.col("week") >= 1)
    except RuntimeError:
        rush_df = pl.DataFrame()

    if pass_df.is_empty() and rush_df.is_empty():
        return _empty_ngs()

    ttt_df = pl.DataFrame(schema={"week": pl.Int64, "team": pl.String, "ttt": pl.Float64})
    att_col = "attempts" if "attempts" in pass_df.columns else (
        "pass_attempts" if "pass_attempts" in pass_df.columns else None
    )
    if not pass_df.is_empty() and att_col and "avg_time_to_throw" in pass_df.columns:
        ttt_df = (
            pass_df.sort(["team", "week", att_col], descending=[False, False, True])
            .unique(subset=["team", "week"], keep="first")
            .select("week", "team", pl.col("avg_time_to_throw").alias("ttt"))
        )

    ryoe_df = pl.DataFrame(schema={"week": pl.Int64, "team": pl.String, "ryoe": pl.Float64})
    if not rush_df.is_empty() and "rush_yards_over_expected" in rush_df.columns:
        ryoe_df = rush_df.group_by(["week", "team"]).agg(
            pl.col("rush_yards_over_expected").fill_null(0).sum().alias("ryoe"),
        )

    if ttt_df.is_empty() and ryoe_df.is_empty():
        return _empty_ngs()
    if ttt_df.is_empty():
        return ryoe_df.with_columns(pl.lit(None).cast(pl.Float64).alias("ttt")).select(
            _NGS_COLS
        )
    if ryoe_df.is_empty():
        return ttt_df.with_columns(pl.lit(None).cast(pl.Float64).alias("ryoe")).select(
            _NGS_COLS
        )

    return ttt_df.join(ryoe_df, on=["week", "team"], how="full", coalesce=True).select(
        _NGS_COLS
    )
