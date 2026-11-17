import unittest
import html
import re
from urllib.parse import parse_qs, urlsplit

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
    def test_mobile_card_uses_compact_weather_instead_of_outdoor_label(self):
        from app import _conditions_text, _mobile_board

        outdoor = {
            **_CARD,
            "game_id": "2026_01_BUF_KC",
            "venue": "outdoor",
            "wx_temp_f": 43.4,
            "wx_wind_mph": 12.2,
            "wx_rain_in": 0.08,
            "wx_snow_in": 0.0,
        }
        self.assertEqual(_conditions_text(outdoor), '43°F · 12 mph wind · 0.08" rain')
        rendered = _mobile_board([outdoor], 2026, 1, {"BUF": 1.2, "KC": 2.3})
        self.assertIn("43°F · 12 mph wind", rendered)
        self.assertNotIn("Conditions: Outdoor", rendered)
        self.assertEqual(_conditions_text({"venue": "indoor"}), "Indoor")
        self.assertEqual(_conditions_text({"venue": "outdoor"}), "Weather unavailable")

    def test_phone_card_preserves_game_context_and_missing_scores(self):
        card = {**_CARD, "game_id": "2026_01_BUF_KC", "home_score": 0, "away_score": 7}
        script = (
            "import streamlit as st\n"
            "from app import _mobile_board\n"
            "st.query_params['theme'] = 'light'\n"
            f"st.markdown(_mobile_board([{card!r}], 2026, 1, {{}}), unsafe_allow_html=True)\n"
        )
        app = AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        rendered = app.markdown[-1].value
        href = html.unescape(re.search(r'href="([^"]+)"', rendered).group(1))
        self.assertEqual(parse_qs(urlsplit(href).query), {
            "season": ["2026"], "week": ["1"], "game": ["2026_01_BUF_KC"], "theme": ["light"],
        })
        self.assertIn("7-0", rendered)
        self.assertIn("56%", rendered)
        self.assertIn("View BUF at KC breakdown", rendered)
        missing = AppTest.from_string(script.replace("'home_score': 0", "'home_score': None")).run()
        self.assertFalse(missing.exception)
        self.assertIn("Not available", missing.markdown[-1].value)

    def test_matchup_glossary_renders_with_and_without_unit_stats(self):
        empty = AppTest.from_string(_matchup_script(_CARD)).run()
        self.assertFalse(empty.exception)
        self.assertTrue(empty.expander)
        glossary = " ".join(m.value for m in empty.expander[0].markdown)
        self.assertIn("Source", glossary)
        self.assertIn("Direction", glossary)
        self.assertIn("Pressure rate allowed", glossary)

        populated_card = {**_CARD, "u_h_pass": 0.2, "u_a_pass": 0.1}
        populated = AppTest.from_string(_matchup_script(populated_card)).run()
        self.assertFalse(populated.exception)
        self.assertTrue(populated.expander)
        self.assertIn("Pass EPA/g", " ".join(m.value for m in populated.expander[0].markdown))

    def test_mobile_injury_cards_include_fields_escape_text_and_optional_game(self):
        from app import _mobile_injury_cards

        rows = [{
            "team": "BUF",
            "player": "<A & B>",
            "position": "QB",
            "status": "questionable",
            "roster_status": "pup",
            "is_starter": True,
            "injury": "肩 <ankle>",
            "practice": "Limited",
            "game": "Thursday",
            "first_reported_week": 2,
            "last_reported_week": 4,
            "is_carried": True,
        }]
        rendered = _mobile_injury_cards(rows, with_game=True)
        for label in (
            "Team", "Player", "Pos", "Status", "Roster", "Starter", "Injury", "Practice",
            "Since", "Last report", "Game",
        ):
            self.assertIn(label, rendered)
        for value in ("BUF", "QB", "Questionable", "PUP", "Yes", "Limited", "Wk 2", "Wk 4 · carried", "Thursday"):
            self.assertIn(value, rendered)
        self.assertIn("&lt;A &amp; B&gt;", rendered)
        self.assertIn("&lt;ankle&gt;", rendered)
        self.assertNotIn("<A & B>", rendered)
        self.assertNotIn("<ankle>", rendered)

        without_game = _mobile_injury_cards(rows, with_game=False)
        self.assertNotIn("Thursday", without_game)

    def test_mobile_injury_cards_empty_input_is_safe(self):
        from app import _mobile_injury_cards

        self.assertEqual(_mobile_injury_cards([]), "")
        self.assertEqual(_mobile_injury_cards(None), "")

    def test_mobile_layout_keeps_glossary_and_reference_containment_scoped(self):
        from pathlib import Path

        source = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 480px)", source)
        self.assertRegex(source, r"(?is)glossary.{0,250}(overflow|scroll)")
        self.assertRegex(source, r"(?is)reference.{0,250}(overflow|scroll)")

    def test_injury_roster_lists_are_counted_additive_toggles(self):
        script = (
            "from app import _render_league_injuries\n"
            "_render_league_injuries([{"
            "'away_team': 'BUF', 'home_team': 'KC', "
            "'injuries_away_rows': ["
            "{'team': 'BUF', 'player': 'A IR', 'status': None, 'roster_status': 'ir', 'is_starter': True},"
            "{'team': 'BUF', 'player': 'B PUP', 'status': None, 'roster_status': 'pup', 'is_starter': False},"
            "{'team': 'BUF', 'player': 'C OUT', 'status': 'out', 'roster_status': None, 'is_starter': False}],"
            "'injuries_home_rows': []}], 2026, 1)\n"
        )
        app = AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        roster_lists = app.multiselect[1]
        self.assertEqual(
            roster_lists.options,
            ["IR (1)", "PUP (1)", "NFI (0)", "Suspended (0)"],
        )

        app.multiselect[0].set_value([])
        roster_lists.set_value(["IR (1)"])
        app.run()
        self.assertFalse(app.exception)
        self.assertIn("A IR", str(app.dataframe[0].value))
        self.assertNotIn("B PUP", str(app.dataframe[0].value))
        self.assertNotIn("C OUT", str(app.dataframe[0].value))

        app.multiselect[0].set_value(["OUT"])
        app.multiselect[1].set_value(["PUP (1)"])
        app.run()
        self.assertFalse(app.exception)
        self.assertNotIn("A IR", str(app.dataframe[0].value))
        self.assertIn("B PUP", str(app.dataframe[0].value))
        self.assertIn("C OUT", str(app.dataframe[0].value))


if __name__ == "__main__":
    unittest.main()
