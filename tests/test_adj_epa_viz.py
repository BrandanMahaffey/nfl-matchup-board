import unittest

from data.adj_epa_viz import adj_epa_scatter


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


if __name__ == "__main__":
    unittest.main()
