"""nfelo Elo snapshot and game probability loaders."""

from __future__ import annotations

import polars as pl

from data.io import load_csv
from data.teamref import canonical

ELO_URL = "https://raw.githubusercontent.com/greerreNFL/nfelo/main/output_data/elo_snapshot.csv"
GAMES_URL = (
    "https://raw.githubusercontent.com/greerreNFL/nfelo/main/output_data/nfelo_games.csv"
)

def _alias_team(value: object) -> str | None:
    if value is None:
        return None
    return canonical(str(value))


def _alias_game_id(value: object) -> str | None:
    """Rewrite the away/home codes inside ``season_week_away_home`` game ids.

    nfelo still publishes historical franchise codes (LAR, OAK), so ids would
    otherwise never match the nflverse schedule.
    """
    if value is None:
        return None
    text = str(value).strip()
    parts = text.split("_")
    if len(parts) != 4:
        return text
    season, week, away, home = parts
    return "_".join((season, week, canonical(away), canonical(home)))


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


def load_elo_snapshot(season: int, week: int) -> pl.DataFrame:
    """Latest available same-season ratings through the requested week."""
    df = load_csv(ELO_URL)
    required = {"team", "nfelo", "pts_vs_avg", "season", "week"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"nfelo snapshot missing required columns: {', '.join(missing)}")
    if df.is_empty():
        return _empty_elo_snapshot()

    snapshot = df.filter((pl.col("season") == season) & (pl.col("week") <= week))
    if snapshot.is_empty():
        return _empty_elo_snapshot()
    snapshot = (
        snapshot.sort("week")
        .unique(subset=["team"], keep="last")
        .with_columns(pl.col("team").map_elements(_alias_team, return_dtype=pl.Utf8))
    )
    return snapshot.select("team", "nfelo", "pts_vs_avg")

def load_nfelo_games(season: int) -> pl.DataFrame:
    """nfelo close-line game probabilities for ``season``."""
    df = load_csv(GAMES_URL)
    if "game_id" not in df.columns:
        raise ValueError("nfelo games source missing required column: game_id")
    if not {"nfelo_home_probability_close", "nfelo_home_win_pct"} & set(df.columns):
        raise ValueError("nfelo games source missing required home probability column")
    if not {"nfelo_home_line_close", "nfelo_home_line"} & set(df.columns):
        raise ValueError("nfelo games source missing required home line column")
    if df.is_empty():
        return _empty_nfelo_games()

    prefix = f"{season}_"
    df = df.with_columns(
        pl.col("game_id").map_elements(_alias_game_id, return_dtype=pl.Utf8)
    ).filter(pl.col("game_id").str.starts_with(prefix))

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
