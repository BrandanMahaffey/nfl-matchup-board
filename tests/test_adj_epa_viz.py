import unittest

from data.adj_epa_viz import adj_epa_scatter, regular_epa_scatter


class AdjustedEpaVizTest(unittest.TestCase):
    def setUp(self):
        self.plot = [
            {"Team": "AAA", "Club": "Alpha", "Adj Off": 2.5, "Adj Def": -1.5, "Adj Net": 4.0, "Logo": "a"},
            {"Team": "BBB", "Club": "Beta", "Adj Off": -3.0, "Adj Def": 2.0, "Adj Net": -5.0, "Logo": "b"},
        ]

    def test_desktop_and_mobile_preserve_domains_and_values(self):
        desktop = adj_epa_scatter(self.plot)
        mobile = adj_epa_scatter(self.plot, height=300)

        self.assertEqual(desktop["height"], 660)
        self.assertEqual(mobile["height"], 300)
        for spec in (desktop, mobile):
            encodings = [layer["encoding"] for layer in spec["layer"] if "x" in layer.get("encoding", {})]
            x_scale = encodings[-1]["x"]["scale"]
            y_scale = encodings[-1]["y"]["scale"]
            self.assertEqual(x_scale["domain"], y_scale["domain"])
            self.assertEqual(x_scale["domain"][0], -x_scale["domain"][1])
            self.assertTrue(y_scale["reverse"])
            values = encodings[-1]["x"]
            self.assertEqual(values["field"], "Adj Off")

        data_values = [layer["data"]["values"] for layer in desktop["layer"] if layer.get("mark", {}).get("type") == "image"][0]
        self.assertEqual(data_values, self.plot)

    def test_regular_epa_scatter_uses_matching_symmetric_axes(self):
        plot = [
            {"Team": "AAA", "Club": "Alpha", "Off EPA/g": 5.0, "Def EPA/g": -2.0, "Net EPA/g": 7.0, "Logo": "a"},
            {"Team": "BBB", "Club": "Beta", "Off EPA/g": -4.0, "Def EPA/g": 3.0, "Net EPA/g": -7.0, "Logo": "b"},
        ]

        spec = regular_epa_scatter(plot, height=300)

        encodings = [layer["encoding"] for layer in spec["layer"] if "x" in layer.get("encoding", {})]
        plotted = encodings[-1]
        self.assertEqual(spec["height"], 300)
        self.assertEqual(plotted["x"]["field"], "Off EPA/g")
        self.assertEqual(plotted["y"]["field"], "Def EPA/g")
        self.assertEqual(plotted["x"]["scale"]["domain"], plotted["y"]["scale"]["domain"])
        self.assertTrue(plotted["y"]["scale"]["reverse"])
        self.assertIn("Net EPA/g", {tip["field"] for tip in plotted["tooltip"]})


if __name__ == "__main__":
    unittest.main()
