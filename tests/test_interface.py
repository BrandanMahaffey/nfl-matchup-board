import unittest

from streamlit.testing.v1 import AppTest


_CARD = {
    "away_team": "BUF",
    "home_team": "KC",
    "home_win_pct": 0.56,
    "spread_line": -2.5,
    "total_line": 47.0,
    "nfelo_home": 1510,
    "nfelo_away": 1490,
    "win_pct_source": "nfelo",
    "gameday": "2026-09-10",
    "gametime": "20:20",
    "injuries_away_rows": [],
    "injuries_home_rows": [],
}


def _matchup_script(card):
    return f"from app import render_matchup\nrender_matchup({card!r})\n"


class InterfaceTest(unittest.TestCase):
    def test_matchup_glossary_renders_with_and_without_unit_stats(self):
        empty = AppTest.from_string(_matchup_script(_CARD)).run()
        self.assertFalse(empty.exception)
        self.assertTrue(empty.expander)
        glossary = " ".join(m.value for m in empty.expander[0].markdown)
        self.assertIn("Source", glossary)
        self.assertIn("Direction", glossary)
        self.assertIn("Most-pressured QB rate", glossary)

        populated_card = {**_CARD, "u_h_pass": 0.2, "u_a_pass": 0.1}
        populated = AppTest.from_string(_matchup_script(populated_card)).run()
        self.assertFalse(populated.exception)
        self.assertTrue(populated.expander)
        self.assertIn("Pass EPA/g", " ".join(m.value for m in populated.expander[0].markdown))

    def test_injury_status_options_include_ir_and_filter(self):
        script = (
            "from app import _render_league_injuries\n"
            "_render_league_injuries([{" 
            "'away_team': 'BUF', 'home_team': 'KC', "
            "'injuries_away_rows': ["
            "{'team': 'BUF', 'player': 'A IR', 'status': 'ir', 'is_starter': True},"
            "{'team': 'BUF', 'player': 'B OUT', 'status': 'out', 'is_starter': False}],"
            "'injuries_home_rows': []}], 2026, 1)\n"
        )
        app = AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        statuses = app.multiselect[0]
        self.assertIn("IR", statuses.options)
        self.assertIn("Suspended", statuses.options)
        statuses.set_value(["IR"]).run()
        self.assertFalse(app.exception)
        self.assertIn("A IR", str(app.dataframe[0].value))
        self.assertNotIn("B OUT", str(app.dataframe[0].value))


if __name__ == "__main__":
    unittest.main()
