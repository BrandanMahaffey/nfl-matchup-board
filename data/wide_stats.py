"""Season-to-date nflverse team tables and Next Gen Stats team tables."""

from __future__ import annotations

from typing import Any

import polars as pl

from data.io import load_csv
from data.team_form import load_team_week_stats
from data.teamref import canonical

RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"

_SKIP_NFLVERSE = {
    "season",
    "week",
    "season_type",
    "game_id",
    "opponent_team",
    "fg_made_list",
    "fg_missed_list",
    "fg_blocked_list",
    "fg_made_distance",
    "fg_missed_distance",
    "fg_blocked_distance",
    "gwfg_distance",
}


def _through(week: int) -> int:
    return week - 1 if week > 1 else 0


def _filter_weeks(df: pl.DataFrame, season: int, week: int) -> pl.DataFrame:
    through = _through(week)
    if df.is_empty():
        return df
    if "season" in df.columns:
        df = df.filter(pl.col("season") == season)
    if "season_type" in df.columns:
        df = df.filter(pl.col("season_type") == "REG")
    if "week" in df.columns:
        # A week-one snapshot has no prior regular-season weeks.
        df = df.filter(pl.col("week") >= 1, pl.col("week") <= through)
    return df

 
def _valid_weight(value: str, weight: str) -> pl.Expr:
    return (
        pl.col(value).is_not_null()
        & pl.col(value).is_finite()
        & pl.col(weight).is_not_null()
        & pl.col(weight).is_finite()
        & (pl.col(weight) > 0)
    )


def _weighted_sum(value: str, weight: str) -> pl.Expr:
    valid = _valid_weight(value, weight)
    return pl.when(valid).then(pl.col(value) * pl.col(weight)).otherwise(0).sum()


def _valid_weight_sum(weight: str, value: str) -> pl.Expr:
    valid = _valid_weight(value, weight)
    return pl.when(valid).then(pl.col(weight)).otherwise(0).sum()



def _norm_team(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df
    col = "team" if "team" in df.columns else ("team_abbr" if "team_abbr" in df.columns else None)
    if col is None:
        return df
    if col != "team":
        df = df.rename({col: "team"})
    return df.with_columns(pl.col("team").cast(pl.Utf8).map_elements(canonical, return_dtype=pl.Utf8))


def _safe_csv(url: str) -> pl.DataFrame:
    try:
        return load_csv(url)
    except RuntimeError:
        return pl.DataFrame()


def league_nflverse_rows(season: int, week: int) -> list[dict[str, Any]]:
    """Team-season totals from nflverse stats_team_week, skipping play lists."""
    raw = load_team_week_stats(season)
    raw = _filter_weeks(raw, season, week)
    if raw.is_empty() or "team" not in raw.columns:
        return []

    num_cols = [
        c
        for c, dtype in zip(raw.columns, raw.dtypes)
        if c not in _SKIP_NFLVERSE | {"team"} and dtype.is_numeric()
    ]
    if not num_cols:
        return []

    work = raw.with_columns([pl.col(c).cast(pl.Float64, strict=False) for c in num_cols])
    weight_cpoe = "attempts" if "attempts" in work.columns else None
    max_cols = {"fg_long", "pt_long"}
    skip_sum = {"fg_pct", "pat_pct"} | max_cols
    aggs: list[pl.Expr] = [pl.len().alias("games")]
    for col in num_cols:
        if col in skip_sum:
            if col in max_cols:
                aggs.append(pl.col(col).max().alias(col))
            continue
        if col == "passing_cpoe" and weight_cpoe:
            aggs.append(_weighted_sum(col, weight_cpoe).alias("_cpoe_w"))
            aggs.append(_valid_weight_sum(weight_cpoe, col).alias("_cpoe_att"))
            continue
        aggs.append(pl.col(col).sum())

    grouped = work.group_by("team").agg(aggs)
    extras: list[pl.Expr] = []
    if "completions" in grouped.columns and "attempts" in grouped.columns:
        extras.append(
            pl.when(pl.col("attempts") > 0)
            .then(pl.col("completions") / pl.col("attempts") * 100.0)
            .otherwise(None)
            .alias("cmp_pct")
        )
    if "carries" in grouped.columns and "rushing_yards" in grouped.columns:
        extras.append(
            pl.when(pl.col("carries") > 0)
            .then(pl.col("rushing_yards") / pl.col("carries"))
            .otherwise(None)
            .alias("ypc")
        )
    if "receptions" in grouped.columns and "targets" in grouped.columns:
        extras.append(
            pl.when(pl.col("targets") > 0)
            .then(pl.col("receptions") / pl.col("targets") * 100.0)
            .otherwise(None)
            .alias("catch_pct")
        )
    if "fg_made" in grouped.columns and "fg_att" in grouped.columns:
        extras.append(
            pl.when(pl.col("fg_att") > 0)
            .then(pl.col("fg_made") / pl.col("fg_att") * 100.0)
            .otherwise(None)
            .alias("fg_pct")
        )
    if "pat_made" in grouped.columns and "pat_att" in grouped.columns:
        extras.append(
            pl.when(pl.col("pat_att") > 0)
            .then(pl.col("pat_made") / pl.col("pat_att") * 100.0)
            .otherwise(None)
            .alias("pat_pct")
        )
    if "pt_net_yards" in grouped.columns and "pt_att" in grouped.columns:
        extras.append(
            pl.when(pl.col("pt_att") > 0)
            .then(pl.col("pt_net_yards") / pl.col("pt_att"))
            .otherwise(None)
            .alias("punt_net_avg")
        )
    if "pt_inside_20" in grouped.columns and "pt_att" in grouped.columns:
        extras.append(
            pl.when(pl.col("pt_att") > 0)
            .then(pl.col("pt_inside_20") / pl.col("pt_att") * 100.0)
            .otherwise(None)
            .alias("inside_20_pct")
        )
    if "_cpoe_w" in grouped.columns and "_cpoe_att" in grouped.columns:
        extras.append(
            pl.when(pl.col("_cpoe_att") > 0)
            .then(pl.col("_cpoe_w") / pl.col("_cpoe_att"))
            .otherwise(None)
            .alias("passing_cpoe")
        )
    if extras:
        grouped = grouped.with_columns(extras)
        drops = [c for c in ("_cpoe_w", "_cpoe_att") if c in grouped.columns]
        if drops:
            grouped = grouped.drop(drops)

    rows = grouped.to_dicts()
    rows.sort(key=lambda r: str(r.get("team") or ""))
    return rows


def _as_f64(df: pl.DataFrame, *cols: str) -> pl.DataFrame:
    present = [c for c in cols if c in df.columns]
    if not present:
        return df
    return df.with_columns([pl.col(c).cast(pl.Float64, strict=False) for c in present])


def _wavg(value: str, weight: str) -> pl.Expr:
    valid = _valid_weight(value, weight)
    numerator = pl.when(valid).then(pl.col(value) * pl.col(weight)).otherwise(0).sum()
    denominator = pl.when(valid).then(pl.col(weight)).otherwise(0).sum()
    return pl.when(denominator > 0).then(numerator / denominator).otherwise(None).alias(value)


def _ngs_pass(season: int, week: int) -> pl.DataFrame:
    df = _norm_team(_safe_csv(f"{RELEASE}/nextgen_stats/ngs_passing.csv.gz"))
    df = _filter_weeks(df, season, week)
    if df.is_empty() or "team" not in df.columns:
        return pl.DataFrame()
    df = _as_f64(
        df,
        "attempts",
        "pass_attempts",
        "completions",
        "pass_yards",
        "pass_touchdowns",
        "interceptions",
        "avg_time_to_throw",
        "avg_completed_air_yards",
        "avg_intended_air_yards",
        "avg_air_yards_differential",
        "aggressiveness",
        "avg_air_yards_to_sticks",
        "expected_completion_percentage",
        "completion_percentage_above_expectation",
        "avg_air_distance",
        "passer_rating",
        "max_completed_air_distance",
    )
    att = "attempts" if "attempts" in df.columns else "pass_attempts"
    if att not in df.columns:
        return pl.DataFrame()
    wcols = [
        c
        for c in (
            "avg_time_to_throw",
            "avg_completed_air_yards",
            "avg_intended_air_yards",
            "avg_air_yards_differential",
            "aggressiveness",
            "avg_air_yards_to_sticks",
            "expected_completion_percentage",
            "completion_percentage_above_expectation",
            "avg_air_distance",
            "passer_rating",
        )
        if c in df.columns
    ]
    aggs = [pl.col(att).fill_null(0).sum().alias("attempts")]
    if "completions" in df.columns:
        aggs.append(pl.col("completions").fill_null(0).sum())
    if "pass_yards" in df.columns:
        aggs.append(pl.col("pass_yards").fill_null(0).sum())
    if "pass_touchdowns" in df.columns:
        aggs.append(pl.col("pass_touchdowns").fill_null(0).sum().alias("pass_tds"))
    if "interceptions" in df.columns:
        aggs.append(pl.col("interceptions").fill_null(0).sum())
    if "max_completed_air_distance" in df.columns:
        aggs.append(pl.col("max_completed_air_distance").max().alias("max_completed_air"))
    for col in wcols:
        aggs.append(_wavg(col, att))
    return df.group_by("team").agg(aggs)


def _ngs_rush(season: int, week: int) -> pl.DataFrame:
    df = _norm_team(_safe_csv(f"{RELEASE}/nextgen_stats/ngs_rushing.csv.gz"))
    df = _filter_weeks(df, season, week)
    if df.is_empty() or "team" not in df.columns:
        return pl.DataFrame()
    df = _as_f64(
        df,
        "rush_attempts",
        "rush_yards",
        "rush_touchdowns",
        "expected_rush_yards",
        "rush_yards_over_expected",
        "efficiency",
        "percent_attempts_gte_eight_defenders",
        "avg_time_to_los",
        "rush_yards_over_expected_per_att",
        "rush_pct_over_expected",
    )
    if "rush_attempts" not in df.columns:
        return pl.DataFrame()
    att = "rush_attempts"
    wcols = [
        c
        for c in (
            "efficiency",
            "percent_attempts_gte_eight_defenders",
            "avg_time_to_los",
            "rush_yards_over_expected_per_att",
            "rush_pct_over_expected",
        )
        if c in df.columns
    ]
    aggs = [pl.col(att).fill_null(0).sum().alias("rush_att")]
    if "rush_yards" in df.columns:
        aggs.append(pl.col("rush_yards").fill_null(0).sum())
    if "rush_touchdowns" in df.columns:
        aggs.append(pl.col("rush_touchdowns").fill_null(0).sum().alias("rush_tds"))
    if "expected_rush_yards" in df.columns:
        aggs.append(pl.col("expected_rush_yards").fill_null(0).sum().alias("exp_rush_yds"))
    if "rush_yards_over_expected" in df.columns:
        aggs.append(pl.col("rush_yards_over_expected").fill_null(0).sum().alias("ryoe"))
    for col in wcols:
        aggs.append(_wavg(col, att))
    out = df.group_by("team").agg(aggs)
    if "rush_att" in out.columns and "ryoe" in out.columns:
        out = out.with_columns(
            pl.when(pl.col("rush_att") > 0)
            .then(pl.col("ryoe") / pl.col("rush_att"))
            .otherwise(None)
            .alias("ryoe_per_att")
        )
    if "rush_att" in out.columns and "rush_yards" in out.columns:
        out = out.with_columns(
            pl.when(pl.col("rush_att") > 0)
            .then(pl.col("rush_yards") / pl.col("rush_att"))
            .otherwise(None)
            .alias("ypc")
        )
    return out


def _ngs_recv(season: int, week: int) -> pl.DataFrame:
    df = _norm_team(_safe_csv(f"{RELEASE}/nextgen_stats/ngs_receiving.csv.gz"))
    df = _filter_weeks(df, season, week)
    if df.is_empty() or "team" not in df.columns:
        return pl.DataFrame()
    df = _as_f64(
        df,
        "targets",
        "receptions",
        "yards",
        "rec_touchdowns",
        "avg_cushion",
        "avg_separation",
        "avg_intended_air_yards",
        "avg_yac",
        "avg_expected_yac",
        "avg_yac_above_expectation",
    )
    if "targets" not in df.columns:
        return pl.DataFrame()
    wt = "targets"
    wcols = [
        c
        for c in (
            "avg_cushion",
            "avg_separation",
            "avg_intended_air_yards",
            "avg_yac",
            "avg_expected_yac",
            "avg_yac_above_expectation",
        )
        if c in df.columns
    ]
    aggs = [pl.col(wt).fill_null(0).sum().alias("targets")]
    if "receptions" in df.columns:
        aggs.append(pl.col("receptions").fill_null(0).sum())
    if "yards" in df.columns:
        aggs.append(pl.col("yards").fill_null(0).sum().alias("rec_yards"))
    if "rec_touchdowns" in df.columns:
        aggs.append(pl.col("rec_touchdowns").fill_null(0).sum().alias("rec_tds"))
    for col in wcols:
        aggs.append(_wavg(col, wt))
    out = df.group_by("team").agg(aggs)
    if "targets" in out.columns and "receptions" in out.columns:
        out = out.with_columns(
            pl.when(pl.col("targets") > 0)
            .then(pl.col("receptions") / pl.col("targets") * 100.0)
            .otherwise(None)
            .alias("catch_pct")
        )
    return out


def league_ngs_rows(season: int, week: int) -> dict[str, list[dict[str, Any]]]:
    """Player-week Next Gen Stats rolled to team totals, weighted by volume."""
    passing = _ngs_pass(season, week)
    rushing = _ngs_rush(season, week)
    receiving = _ngs_recv(season, week)
    return {
        "passing": passing.sort("team").to_dicts() if not passing.is_empty() else [],
        "rushing": rushing.sort("team").to_dicts() if not rushing.is_empty() else [],
        "receiving": receiving.sort("team").to_dicts() if not receiving.is_empty() else [],
    }
