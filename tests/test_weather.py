import unittest
from datetime import date
from unittest.mock import Mock, patch

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


if __name__ == "__main__":
    unittest.main()
