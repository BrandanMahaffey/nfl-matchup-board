"""nfelo Elo snapshot and game probability loaders."""

from __future__ import annotations

import polars as pl

from data.io import load_csv

ELO_URL = "https://raw.githubusercontent.com/greerreNFL/nfelo/main/output_data/elo_snapshot.csv"
GAMES_URL = (
    "https://raw.githubusercontent.com/greerreNFL/nfelo/main/output_data/nfelo_games.csv"
)

_TEAM_ALIAS = {"OAK": "LV"}


def _alias_team(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return _TEAM_ALIAS.get(text, text)


def _empty_elo_snapshot() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "team": pl.Series([], dtype=pl.Utf8),
            "nfelo": pl.Series([], dtype=pl.Float64),
            "pts_vs_avg": pl.Series([], dtype=pl.Float64),
        }
    )


def _empty_nfelo_games() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "game_id": pl.Series([], dtype=pl.Utf8),
            "nfelo_home_win_pct": pl.Series([], dtype=pl.Float64),
            "nfelo_home_line": pl.Series([], dtype=pl.Float64),
        }
    )


def load_elo_snapshot() -> pl.DataFrame:
    """Latest per-team nfelo ratings from the nfelo GitHub snapshot."""
    try:
        df = load_csv(ELO_URL)
    except RuntimeError:
        return _empty_elo_snapshot()

    if df.is_empty():
        return _empty_elo_snapshot()

    required = {"team", "nfelo", "pts_vs_avg", "season", "week"}
    if not required.issubset(df.columns):
        return _empty_elo_snapshot()

    if "team" in df.columns:
        df = df.with_columns(
            pl.col("team").map_elements(_alias_team, return_dtype=pl.Utf8)
        )

    latest_season = df.select(pl.col("season").max()).item()
    latest_week = (
        df.filter(pl.col("season") == latest_season)
        .select(pl.col("week").max())
        .item()
    )

    snapshot = df.filter(
        (pl.col("season") == latest_season) & (pl.col("week") == latest_week)
    )

    if snapshot.is_empty():
        return _empty_elo_snapshot()

    return snapshot.select("team", "nfelo", "pts_vs_avg")


def load_nfelo_games(season: int) -> pl.DataFrame:
    """nfelo close-line game probabilities for ``season``."""
    try:
        df = load_csv(GAMES_URL)
    except RuntimeError:
        return _empty_nfelo_games()

    if df.is_empty() or "game_id" not in df.columns:
        return _empty_nfelo_games()

    prefix = f"{season}_"
    df = df.filter(pl.col("game_id").cast(pl.Utf8).str.starts_with(prefix))

    if df.is_empty():
        return _empty_nfelo_games()

    rename_map: dict[str, str] = {}
    if "nfelo_home_probability_close" in df.columns:
        rename_map["nfelo_home_probability_close"] = "nfelo_home_win_pct"
    if "nfelo_home_line_close" in df.columns:
        rename_map["nfelo_home_line_close"] = "nfelo_home_line"

    if rename_map:
        df = df.rename(rename_map)

    for col in ("game_id", "nfelo_home_win_pct", "nfelo_home_line"):
        if col not in df.columns:
            df = df.with_columns(pl.lit(None).alias(col))

    return df.select("game_id", "nfelo_home_win_pct", "nfelo_home_line")
