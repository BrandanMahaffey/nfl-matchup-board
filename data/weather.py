"""Game weather from schedule data and Open-Meteo forecasts."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import httpx
import polars as pl

_EASTERN = ZoneInfo("America/New_York")
_FORECAST_TIMEOUT = 20.0
_DEFAULT_KICKOFF = time(13, 0)
_FORECAST_CACHE: dict[tuple[float, float, str], dict[str, list]] = {}

# stadium_id -> (latitude, longitude)
STADIUMS: dict[str, tuple[float, float]] = {
    "ATL97": (33.7554, -84.4008),  # Mercedes-Benz Stadium
    "BAL00": (39.2780, -76.6227),  # M&T Bank Stadium
    "BOS00": (42.0909, -71.2643),  # Gillette Stadium
    "BUF00": (42.7738, -78.7870),  # Highmark Stadium
    "CAR00": (35.2258, -80.8528),  # Bank of America Stadium
    "CHI98": (41.8623, -87.6167),  # Soldier Field
    "CIN00": (39.0955, -84.5160),  # Paycor Stadium
    "CLE00": (41.5061, -81.6995),  # Cleveland Browns Stadium
    "DAL00": (32.7473, -97.0945),  # AT&T Stadium
    "DEN00": (39.7439, -105.0201),  # Empower Field at Mile High
    "DET00": (42.3400, -83.0456),  # Ford Field
    "GNB00": (44.5013, -88.0622),  # Lambeau Field
    "HOU00": (29.6847, -95.4107),  # NRG Stadium
    "IND00": (39.7601, -86.1639),  # Lucas Oil Stadium
    "JAX00": (30.3239, -81.6373),  # EverBank Stadium
    "KAN00": (39.0489, -94.4839),  # GEHA Field at Arrowhead Stadium
    "LAX01": (33.9535, -118.3392),  # SoFi Stadium
    "LON00": (51.5560, -0.2795),  # Wembley Stadium
    "LON02": (51.6043, -0.0664),  # Tottenham Hotspur Stadium
    "MAD01": (40.4531, -3.6883),  # Santiago Bernabéu
    "MEL00": (-37.8199, 144.9834),  # Melbourne Cricket Ground
    "MEX00": (25.6866, -100.2895),  # Estadio Banorte (Estadio BBVA)
    "MIA00": (25.9580, -80.2389),  # Hard Rock Stadium
    "MIN01": (44.9735, -93.2575),  # U.S. Bank Stadium
    "MUN01": (48.2188, 11.6247),  # Allianz Arena
    "NAS00": (36.1665, -86.7713),  # Nissan Stadium
    "NOR00": (29.9511, -90.0812),  # Caesars Superdome
    "NYC01": (40.8128, -74.0742),  # MetLife Stadium
    "PAR00": (48.9245, 2.3602),  # Stade de France
    "PHI00": (39.9008, -75.1675),  # Lincoln Financial Field
    "PHO00": (33.5276, -112.2626),  # State Farm Stadium
    "PIT00": (40.4468, -80.0158),  # Acrisure Stadium
    "RIO00": (-22.9122, -43.2302),  # Maracanã
    "SEA00": (47.5952, -122.3316),  # Lumen Field
    "SFO01": (37.4030, -121.9694),  # Levi's Stadium
    "TAM00": (27.9759, -82.5033),  # Raymond James Stadium
    "VEG00": (36.0909, -115.1833),  # Allegiant Stadium
    "WAS00": (38.9076, -76.8645),  # Northwest Stadium
}


def _empty_weather() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "game_id": pl.Series([], dtype=pl.Utf8),
            "temp_f": pl.Series([], dtype=pl.Float64),
            "wind_mph": pl.Series([], dtype=pl.Float64),
            "precip_in": pl.Series([], dtype=pl.Float64),
            "weather_note": pl.Series([], dtype=pl.Utf8),
        }
    )


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


def _parse_gametime(value: object) -> time:
    if value is None:
        return _DEFAULT_KICKOFF
    text = str(value).strip()
    if not text:
        return _DEFAULT_KICKOFF
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return _DEFAULT_KICKOFF


def _kickoff_datetime(gameday: object, gametime: object) -> datetime | None:
    day = _parse_gameday(gameday)
    if day is None:
        return None
    kick_time = _parse_gametime(gametime)
    return datetime.combine(day, kick_time, tzinfo=_EASTERN)


def _fetch_forecast(lat: float, lon: float, day: date) -> dict[str, list] | None:
    cache_key = (lat, lon, day.isoformat())
    if cache_key in _FORECAST_CACHE:
        return _FORECAST_CACHE[cache_key]

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,wind_speed_10m,precipitation"
        "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
        "&timezone=America%2FNew_York"
        f"&start_date={day.isoformat()}&end_date={day.isoformat()}"
    )
    try:
        response = httpx.get(url, timeout=_FORECAST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        return None

    _FORECAST_CACHE[cache_key] = hourly
    return hourly


def _nearest_hourly(
    hourly: dict[str, list], kickoff: datetime
) -> tuple[float | None, float | None, float | None]:
    times = hourly.get("time")
    if not times:
        return None, None, None

    temps = hourly.get("temperature_2m", [])
    winds = hourly.get("wind_speed_10m", [])
    precips = hourly.get("precipitation", [])

    best_idx = None
    best_delta = None
    for idx, stamp in enumerate(times):
        try:
            hour_dt = datetime.fromisoformat(str(stamp)).replace(tzinfo=_EASTERN)
        except ValueError:
            continue
        delta = abs((hour_dt - kickoff).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_idx = idx

    if best_idx is None:
        return None, None, None

    def _at(series: list, index: int) -> float | None:
        if index >= len(series):
            return None
        value = series[index]
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return _at(temps, best_idx), _at(winds, best_idx), _at(precips, best_idx)


def _weather_note(temp_f: float | None, wind_mph: float | None, precip_in: float | None) -> str | None:
    parts: list[str] = []
    if temp_f is not None:
        parts.append(f"{temp_f:.0f}°F")
    if wind_mph is not None:
        parts.append(f"wind {wind_mph:.0f} mph")
    if precip_in is not None and precip_in > 0:
        parts.append(f"precip {precip_in:.2f} in")
    if not parts:
        return None
    return ", ".join(parts)


def weather_for_games(games: pl.DataFrame) -> pl.DataFrame:
    """Attach weather fields for each game in ``games``."""
    if games.is_empty() or "game_id" not in games.columns:
        return _empty_weather()

    rows: list[dict[str, object]] = []
    for game in games.to_dicts():
        game_id = game.get("game_id")
        venue = str(game.get("venue") or "").lower()
        home_score = game.get("home_score")

        row: dict[str, object] = {
            "game_id": game_id,
            "temp_f": None,
            "wind_mph": None,
            "precip_in": None,
            "weather_note": None,
        }

        if venue == "indoor":
            rows.append(row)
            continue

        if venue != "outdoor":
            rows.append(row)
            continue

        if home_score is not None:
            temp = game.get("temp")
            wind = game.get("wind")
            row["temp_f"] = float(temp) if temp is not None else None
            row["wind_mph"] = float(wind) if wind is not None else None
            row["weather_note"] = _weather_note(row["temp_f"], row["wind_mph"], None)
            rows.append(row)
            continue

        stadium_id = game.get("stadium_id")
        coords = STADIUMS.get(str(stadium_id)) if stadium_id is not None else None
        kickoff = _kickoff_datetime(game.get("gameday"), game.get("gametime"))
        if coords is None or kickoff is None:
            rows.append(row)
            continue

        lat, lon = coords
        forecast = _fetch_forecast(lat, lon, kickoff.date())
        if forecast is None:
            rows.append(row)
            continue

        temp_f, wind_mph, precip_in = _nearest_hourly(forecast, kickoff)
        row["temp_f"] = temp_f
        row["wind_mph"] = wind_mph
        row["precip_in"] = precip_in
        row["weather_note"] = _weather_note(temp_f, wind_mph, precip_in)
        rows.append(row)

    if not rows:
        return _empty_weather()

    return pl.DataFrame(rows).select(
        "game_id", "temp_f", "wind_mph", "precip_in", "weather_note"
    )
