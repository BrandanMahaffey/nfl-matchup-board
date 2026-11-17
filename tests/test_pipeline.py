import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import polars as pl
from streamlit.runtime.caching.ttl_cache import TTLCache

from data import io, matchups, nfelo, schedules


class PipelineRegressions(unittest.TestCase):
    def test_programming_errors_are_not_suppressed(self):
        with self.assertRaises(KeyError):
            matchups._safe(lambda: {}["missing"], pl.DataFrame())

    def test_mandatory_schedule_outage_propagates(self):
        with patch.object(schedules, "load_csv", side_effect=io.DataLoadError("down")):
            with self.assertRaises(io.DataLoadError):
                schedules.load_schedules(2026)

    def test_nfelo_keeps_prior_week_and_excludes_future(self):
        source = pl.DataFrame(
            {
                "team": ["BUF", "BUF", "CHI", "JAX"],
                "nfelo": [1500.0, 1600.0, 1450.0, 1700.0],
                "pts_vs_avg": [1.0, 2.0, 0.5, 3.0],
                "season": [2026, 2026, 2026, 2026],
                "week": [9, 10, 9, 11],
            }
        )
        with patch.object(nfelo, "load_csv", return_value=source):
            result = nfelo.load_elo_snapshot(2026, 10)
            old = nfelo.load_elo_snapshot(2025, 10)
        ratings = dict(zip(result.get_column("team"), result.get_column("nfelo")))
        self.assertEqual(ratings, {"BUF": 1600.0, "CHI": 1450.0})
        self.assertTrue(old.is_empty())

    def test_kickoff_cutoff_is_timezone_aware(self):
        kickoff = matchups._kickoff_utc({"gameday": "2026-09-13", "gametime": "1:00 PM"})
        self.assertEqual(kickoff.tzinfo, timezone.utc)
        self.assertEqual(kickoff.hour, 17)
    def test_ttl_refetches_after_expiry_without_sleep(self):
        clock = [0.0]
        cache = TTLCache(maxsize=32, ttl=3600, timer=lambda: clock[0])
        fetches = []

        def load(url):
            try:
                return cache[url]
            except KeyError:
                fetches.append(url)
                value = len(fetches)
                cache[url] = value
                return value

        self.assertEqual(load("public.csv"), 1)
        self.assertEqual(load("public.csv"), 1)
        clock[0] = 3601.0
        self.assertEqual(load("public.csv"), 2)
        self.assertEqual(fetches, ["public.csv", "public.csv"])


    def test_http_failure_is_typed(self):
        with patch.object(io.httpx, "get", side_effect=io.httpx.ConnectError("offline")):
            with self.assertRaises(io.DataLoadError):
                io._fetch("https://github.com/nflverse/data.csv?token=secret")

    def test_malformed_csv_payload_is_typed(self):
        with patch.object(io, "_fetch", return_value=b"first,second\n1,2,3"):
            with self.assertRaises(io.DataLoadError) as caught:
                io.load_csv("https://github.com/nflverse/data.csv")
        self.assertIsInstance(caught.exception.__cause__, pl.exceptions.PolarsError)


if __name__ == "__main__":
    unittest.main()
