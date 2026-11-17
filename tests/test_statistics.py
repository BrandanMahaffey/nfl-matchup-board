import unittest
from unittest.mock import patch

import polars as pl

from data import special_teams, trench, wide_stats



class StatisticsTests(unittest.TestCase):
    def test_filter_weeks_week_one_has_no_prior_rows(self):
        frame = pl.DataFrame({"season": [2024, 2024], "season_type": ["REG", "REG"], "week": [1, 2]})
        self.assertEqual(wide_stats._filter_weeks(frame, 2024, 1).height, 0)

    def test_filter_weeks_later_week_is_exclusive_cutoff(self):
        frame = pl.DataFrame({"season": [2024] * 4, "season_type": ["REG"] * 4, "week": [1, 2, 3, 4]})
        self.assertEqual(wide_stats._filter_weeks(frame, 2024, 4)["week"].to_list(), [1, 2, 3])

    def test_weighted_average_ignores_invalid_metric_and_weight(self):
        frame = pl.DataFrame({"metric": [10.0, None, float("nan"), 99.0], "weight": [2.0, 4.0, 3.0, 0.0]})
        result = frame.select(wide_stats._wavg("metric", "weight"))
        self.assertEqual(result.item(), 10.0)

    def test_weighted_average_returns_null_when_no_valid_weights(self):
        frame = pl.DataFrame({"metric": [None, float("nan")], "weight": [2.0, 3.0]})
        self.assertIsNone(frame.select(wide_stats._wavg("metric", "weight")).item())

    @patch("data.trench.load_csv")
    def test_team_pressure_sums_all_qbs_but_keeps_max_qb_rate(self, load_csv):
        passing = pl.DataFrame(
            {
                "week": [1, 1], "team": ["BUF", "BUF"],
                "times_pressured": [3, 2], "times_sacked": [1, 2],
                "times_hurried": [0, 0], "times_hit": [0, 0],
                "times_pressured_pct": [0.3, 0.2],
            }
        )
        defense = pl.DataFrame(
            {
                "week": [1], "team": ["KC"], "def_pressures": [4],
                "def_sacks": [1], "def_times_hurried": [2],
                "pfr_player_name": ["Rusher"],
            }
        )
        load_csv.side_effect = [passing, defense]
        row = trench.team_pressure(2024).filter(pl.col("team") == "BUF").row(0, named=True)
        self.assertEqual(row["pressures_allowed"], 5)
        self.assertEqual(row["sacks_allowed"], 3)
        self.assertEqual(row["pressure_pct_allowed"], 0.3)
        self.assertIsNone(row["pressures_generated"])

    @patch("data.trench.load_csv")
    def test_team_pressure_missing_defense_is_null(self, load_csv):
        passing = pl.DataFrame(
            {
                "week": [1], "team": ["BUF"], "times_pressured": [1],
                "times_sacked": [0], "times_hurried": [0], "times_hit": [0],
                "times_pressured_pct": [0.1],
            }
        )
        load_csv.side_effect = [passing, pl.DataFrame()]
        row = trench.team_pressure(2024).row(0, named=True)
        self.assertIsNone(row["pressures_generated"])
        self.assertIsNone(row["sacks_generated"])
        self.assertIsNone(row["hurries_generated"])


    def test_kickoff_return_attribution_uses_receiving_team(self):
        plays = pl.DataFrame(
            {
                "play_type": ["kickoff"],
                "posteam": ["KICK"],
                "defteam": ["RECV"],
                "return_yards": [25.0],
                "game_id": ["game"],
                "epa": [0.0],
                "to_from": [None],
                "to_to": [None],
                "td_team": [None],
            }
        )
        rows = pl.concat(
            [special_teams._side(plays, "posteam", 1), special_teams._side(plays, "defteam", -1)]
        )
        result = rows.group_by("team").agg(
            pl.col("kr_yards").sum(),
            pl.col("kr_allowed").sum(),
            pl.col("ko_recv").sum(),
            pl.col("ko_made").sum(),
        )
        recv = result.filter(pl.col("team") == "RECV").row(0, named=True)
        kick = result.filter(pl.col("team") == "KICK").row(0, named=True)
        self.assertEqual((recv["kr_yards"], recv["kr_allowed"], recv["ko_recv"]), (25.0, 0.0, 1.0))
        self.assertEqual((kick["kr_allowed"], kick["kr_yards"], kick["ko_made"]), (25.0, 0.0, 1.0))

if __name__ == "__main__":
    unittest.main()
