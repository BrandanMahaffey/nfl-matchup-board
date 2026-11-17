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

    def test_injury_state_history_carries_persistent_and_expires_weekly(self):
        injuries = pl.DataFrame(
            {
                "team": ["LAR", "LA", "LA", "LA"],
                "week": [1, 1, 2, 3],
                "gsis_id": ["ir-1", "weekly-1", "new-1", "ir-1"],
                "full_name": ["Persistent", "Weekly", "New Player", "Persistent"],
                "position": ["QB", "WR", "WR", "QB"],
                "report_status": ["IR", "Out", "Questionable", None],
                "practice_status": [None, None, None, "Full Participation"],
            }
        )
        history = personnel.injury_state_history(injuries, through_week=3, teams=["LA"])
        self.assertEqual([row["full_name"] for row in history[0]["rows"]], ["Persistent", "Weekly"])
        self.assertEqual(
            {row["full_name"] for row in history[1]["rows"]}, {"Persistent", "New Player"}
        )
        persistent = next(row for row in history[1]["rows"] if row["full_name"] == "Persistent")
        self.assertTrue(persistent["is_carried"])
        self.assertEqual(history[2]["rows"], [])

    def test_injury_state_replacement_and_full_participation_resolution(self):
        injuries = pl.DataFrame(
            {
                "team": ["GB", "GB", "GB"],
                "week": [1, 2, 3],
                "gsis_id": ["x", "x", "x"],
                "full_name": ["Player", "Player", "Player"],
                "position": ["QB", "QB", "QB"],
                "report_status": ["Out", "Suspended", None],
                "practice_status": [None, None, "Full"],
            }
        )
        history = personnel.injury_state_history(injuries, through_week=3)
        self.assertEqual(history[1]["rows"][0]["report_status"], "Suspended")
        self.assertEqual(history[1]["rows"][0]["first_reported_week"], 2)
        self.assertEqual(history[2]["rows"], [])

    def test_injury_duplicate_selection_name_fallback_and_immutable_history(self):
        injuries = pl.DataFrame(
            {
                "team": ["LAR", "LA", "LA"],
                "week": [1, 1, 2],
                "gsis_id": [None, None, None],
                "full_name": ["Name Fallback", "Name Fallback", "Name Fallback"],
                "position": ["QB", "QB", "QB"],
                "report_status": ["Out", "Questionable", "Questionable"],
                "practice_status": [None, None, None],
                "date_modified": [
                    "2024-09-01T00:00:00Z",
                    "2024-09-02T00:00:00Z",
                    "2024-09-03T00:00:00Z",
                ],
            }
        )
        history = personnel.injury_state_history(injuries, through_week=2, teams=["LA"])
        self.assertEqual(history[0]["rows"][0]["report_status"], "Questionable")
        self.assertEqual(history[1]["rows"][0]["full_name"], "Name Fallback")
        self.assertEqual(history[0]["rows"][0]["report_status"], "Questionable")

    def test_injury_history_keeps_unreported_intermediate_weeks(self):
        injuries = pl.DataFrame(
            {
                "team": ["GB", "GB"],
                "week": [1, 3],
                "gsis_id": ["persistent", "new"],
                "full_name": ["Persistent", "New"],
                "position": ["QB", "WR"],
                "report_status": ["IR", "Questionable"],
                "practice_status": [None, None],
            }
        )

        history = personnel.injury_state_history(injuries, through_week=3)

        self.assertEqual([snapshot["week"] for snapshot in history], [1, 2, 3])
        self.assertEqual(history[1]["rows"][0]["full_name"], "Persistent")

        self.assertTrue(history[1]["rows"][0]["is_carried"])

    def test_blank_later_report_clears_weekly_but_not_persistent_status(self):
        injuries = pl.DataFrame(
            {
                "team": ["GB", "GB", "GB", "GB"],
                "week": [1, 1, 2, 2],
                "gsis_id": ["weekly", "persistent", "weekly", "persistent"],
                "full_name": ["Weekly", "Persistent", "Weekly", "Persistent"],
                "position": ["WR", "QB", "WR", "QB"],
                "report_status": ["Out", "IR", None, None],
                "practice_status": [None, None, None, None],
            }
        )

        current = personnel.derive_injury_states(injuries, through_week=2)

        self.assertEqual(current.get_column("full_name").to_list(), ["Persistent"])
        self.assertTrue(current.row(0, named=True)["is_carried"])
