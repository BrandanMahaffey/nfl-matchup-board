import unittest
from datetime import date
from unittest.mock import Mock, patch

import polars as pl

from data import weather


class WeatherRegressions(unittest.TestCase):
    def setUp(self):
        weather._FORECAST_CACHE.clear()

    def test_non_object_json_payload_returns_none(self):
        response = Mock()
        response.json.return_value = []

        with patch.object(weather.httpx, "get", return_value=response):
            result = weather._fetch_forecast(40.0, -75.0, date(2026, 9, 13))

        self.assertIsNone(result)
        response.raise_for_status.assert_called_once_with()

    def test_object_payload_returns_hourly_forecast(self):
        hourly = {"time": ["2026-09-13T13:00"], "temperature_2m": [72.0]}
        response = Mock()
        response.json.return_value = {"hourly": hourly}

        with patch.object(weather.httpx, "get", return_value=response):
            result = weather._fetch_forecast(40.0, -75.0, date(2026, 9, 13))

        self.assertEqual(result, hourly)

    def test_completed_outdoor_game_keeps_observed_values_and_adds_precipitation(self):
        games = pl.DataFrame(
            [
                {
                    "game_id": "2026_01_BUF_KC",
                    "venue": "outdoor",
                    "home_score": 24,
                    "temp": 61.0,
                    "wind": 7.0,
                    "stadium_id": "ATL97",
                    "gameday": date(2026, 9, 13),
                    "gametime": "13:00",
                }
            ]
        )
        hourly = {
            "time": ["2026-09-13T13:00"],
            "temperature_2m": [59.0],
            "wind_speed_10m": [9.0],
            "rain": [0.06],
            "snowfall": [0.0],
        }

        with patch.object(weather, "_fetch_forecast", return_value=hourly):
            row = weather.weather_for_games(games).row(0, named=True)

        self.assertEqual(row["temp_f"], 61.0)
        self.assertEqual(row["wind_mph"], 7.0)
        self.assertEqual(row["rain_in"], 0.06)
        self.assertEqual(row["snow_in"], 0.0)

if __name__ == "__main__":
    unittest.main()
