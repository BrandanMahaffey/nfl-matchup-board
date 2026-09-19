"""NFL schedule loading and week helpers."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import polars as pl

from data.io import load_csv

RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"
GAMES_URL = f"{RELEASE}/schedules/games.csv"

_SCHEDULE_COLUMNS = [
    "game_id",
    "season",
    "week",
    "game_type",
    "gameday",
    "weekday",
    "gametime",
    "away_team",
    "home_team",
    "away_score",
    "home_score",
    "location",
    "spread_line",
    "away_moneyline",
    "home_moneyline",
    "total_line",
    "roof",
    "venue",
    "temp",
    "wind",
    "stadium",
    "stadium_id",
    "away_qb_name",
    "home_qb_name",
    "home_ml_win_pct",
    "away_ml_win_pct",
]

_EASTERN = ZoneInfo("America/New_York")
_OUTDOOR_ROOFS = {"outdoors", "open"}


def _empty_schedules() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "game_id": pl.Utf8,
            "season": pl.Int64,
            "week": pl.Int64,
            "game_type": pl.Utf8,
            "gameday": pl.Date,
            "weekday": pl.Utf8,
            "gametime": pl.Utf8,
            "away_team": pl.Utf8,
            "home_team": pl.Utf8,
            "away_score": pl.Float64,
            "home_score": pl.Float64,
            "location": pl.Utf8,
            "spread_line": pl.Float64,
            "away_moneyline": pl.Int64,
            "home_moneyline": pl.Int64,
            "total_line": pl.Float64,
            "roof": pl.Utf8,
            "venue": pl.Utf8,
            "temp": pl.Float64,
            "wind": pl.Float64,
            "stadium": pl.Utf8,
            "stadium_id": pl.Utf8,
            "away_qb_name": pl.Utf8,
            "home_qb_name": pl.Utf8,
            "home_ml_win_pct": pl.Float64,
            "away_ml_win_pct": pl.Float64,
        }
    )

def moneyline_to_win_pct(odds: int | float | None) -> float | None:
    """Convert American moneyline odds to implied win probability (no vig removal)."""
    if odds is None:
        return None
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    if o < 0:
        return abs(o) / (abs(o) + 100.0)
    return 100.0 / (o + 100.0)


def _derive_venue(roof: str | None) -> str:
    if roof is not None and str(roof).lower() in _OUTDOOR_ROOFS:
        return "outdoor"
    return "indoor"


def _parse_gameday(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def load_schedules(season: int) -> pl.DataFrame:
    """Load nflverse schedules for ``season`` with derived venue and ML win percentages."""
    try:
        df = load_csv(GAMES_URL)
    except RuntimeError:
        return _empty_schedules()

    if df.is_empty() or "season" not in df.columns:
        return _empty_schedules()

    df = df.filter(pl.col("season") == season)
    if df.is_empty():
        return _empty_schedules()

    if "roof" in df.columns:
        venue = pl.col("roof").map_elements(_derive_venue, return_dtype=pl.Utf8)
    else:
        venue = pl.lit("indoor")

    if "home_moneyline" in df.columns:
        home_ml = pl.col("home_moneyline").map_elements(
            moneyline_to_win_pct, return_dtype=pl.Float64
        )
    else:
        home_ml = pl.lit(None, dtype=pl.Float64)

    if "away_moneyline" in df.columns:
        away_ml = pl.col("away_moneyline").map_elements(
            moneyline_to_win_pct, return_dtype=pl.Float64
        )
    else:
        away_ml = pl.lit(None, dtype=pl.Float64)

    df = df.with_columns(
        venue=venue,
        home_ml_win_pct=home_ml,
        away_ml_win_pct=away_ml,
    )

    for col in _SCHEDULE_COLUMNS:
        if col not in df.columns:
            df = df.with_columns(pl.lit(None).alias(col))

    return df.select(_SCHEDULE_COLUMNS)


def current_week(schedules: pl.DataFrame) -> int:
    """Return the current NFL regular-season week from schedule data."""
    if schedules.is_empty() or "game_type" not in schedules.columns:
        return 1

    reg = schedules.filter(pl.col("game_type") == "REG")
    if reg.is_empty():
        return 1

    today = datetime.now(_EASTERN).date()
    in_progress_weeks: list[int] = []
    upcoming_weeks: list[int] = []
    for row in reg.select("week", "gameday", "home_score").to_dicts():
        week = row.get("week")
        gameday = _parse_gameday(row.get("gameday"))
        if week is None or gameday is None:
            continue
        week_int = int(week)
        if row.get("home_score") is not None:
            continue
        if gameday <= today:
            in_progress_weeks.append(week_int)
        else:
            upcoming_weeks.append(week_int)

    if in_progress_weeks:
        return min(in_progress_weeks)
    if upcoming_weeks:
        return min(upcoming_weeks)

    scored = reg.filter(pl.col("home_score").is_not_null())
    if not scored.is_empty() and "week" in scored.columns:
        return int(scored.select(pl.col("week").max()).item())
    return 1
