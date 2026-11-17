from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

import polars as pl

from data import personnel


class PersonnelTests(TestCase):
    def test_depth_uses_latest_chart_per_team_before_cutoff_and_aliases(self):
        charts = pl.DataFrame(
            {
                "dt": [
                    "2024-09-01T00:00:00Z",
                    "2024-09-02T00:00:00Z",
                    "2024-09-03T00:00:00Z",
                    "2024-09-02T00:00:00Z",
                ],
                "team": ["LA", "LA", "LAR", "GB"],
                "pos_rank": [1, 1, 1, 1],
                "pos_abb": ["QB", "QB", "QB", "QB"],
                "pos_grp": ["QB", "QB", "QB", "QB"],
                "player_name": ["Old", "Future", "Rams Latest", "Packers Latest"],
                "gsis_id": ["old", "future", "latest", "gb"],
            }
        )
        with patch.object(personnel, "load_csv", return_value=charts):
            result = personnel.depth_starters(
                2024,
                ["LAR", "GB"],
                week=2,
                as_of=datetime(2024, 9, 3, tzinfo=timezone.utc),
            )
        self.assertEqual(set(result.get_column("team")), {"LA", "GB"})
        self.assertEqual(set(result.get_column("gsis_id")), {"latest", "gb"})

    def test_legacy_weekly_depth_uses_latest_prior_week(self):
        charts = pl.DataFrame(
            {
                "season": [2024, 2024, 2024],
                "club_code": ["ATL", "ATL", "ATL"],
                "week": [1, 10, 11],
                "game_type": ["REG", "REG", "REG"],
                "depth_team": [1, 1, 1],
                "gsis_id": ["week1", "week10", "week11"],
                "position": ["G", "G", "G"],
                "depth_position": ["RG", "RG", "RG"],
                "full_name": ["Early", "Current", "Future"],
            }
        )
        with patch.object(personnel, "load_csv", return_value=charts):
            result = personnel.depth_starters(
                2024, ["ATL"], week=10, as_of=datetime(2024, 9, 1, tzinfo=timezone.utc)
            )
        self.assertEqual(result.get_column("gsis_id").to_list(), ["week10"])

    def test_depth_requires_aware_cutoff(self):
        with self.assertRaises(ValueError):
            personnel.depth_starters(2024, ["LA"], week=1, as_of=datetime(2024, 9, 1))

    def test_week_one_snaps_are_typed_empty_without_fetch(self):
        with patch.object(personnel, "load_csv") as load:
            result = personnel.last_week_snaps(2024, 1, ["LA"])
        load.assert_not_called()
        self.assertTrue(result.is_empty())
        self.assertEqual(result.schema["team"], pl.String)

    def test_injury_feed_canonicalizes_alias_before_filter(self):
        injuries = pl.DataFrame(
            {
                "team": ["LAR"],
                "week": [1],
                "gsis_id": ["x"],
                "position": ["QB"],
                "full_name": ["Player Name"],
                "report_status": ["Out"],
                "report_primary_injury": ["knee"],
                "practice_status": [None],
            }
        )
        with patch.object(personnel, "load_csv", return_value=injuries):
            result = personnel.key_injuries(2024, 1, ["LA"])
        self.assertEqual(result.get_column("team").to_list(), ["LA"])
