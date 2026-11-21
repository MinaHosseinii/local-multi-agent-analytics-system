#These are integration tests: they check that your calculation function and LangGraph routing work together, including which nodes actually execute.
import copy
import unittest

from reliability_graph import graph, initial_state


class TestAnalysisRouting(unittest.TestCase):
    def run_graph(self, rows, method="pearson"):
        updates = list(graph.stream(
            initial_state(rows, method),
            stream_mode="updates",
        ))

        visited = [
            node
            for update in updates
            for node in update
        ]

        return updates, visited

    def test_success_reaches_reporting(self):
        rows = [
            {"x": 1, "y": 10},
            {"x": 2, "y": 20},
            {"x": 3, "y": 30},
        ]

        updates, visited = self.run_graph(rows)

        self.assertEqual(visited, ["analysis", "report"])
        self.assertEqual(
            updates[-1]["report"]["status"], "completed"
        )

    def test_invalid_data_cannot_reach_reporting(self):
        rows = [
            {"x": 1, "y": 10},
            {"x": 2, "y": "twenty"},
            {"x": 3, "y": 30},
        ]

        updates, visited = self.run_graph(rows)

        self.assertEqual(visited, ["analysis", "blocked"])
        self.assertNotIn("report", visited)
        self.assertEqual(
            updates[-1]["blocked"]["status"], "blocked"
        )
        self.assertFalse(updates[0]["analysis"]["result"]["ok"])

    def test_unknown_method_is_handled(self):
        rows = [
            {"x": 1, "y": 10},
            {"x": 2, "y": 20},
            {"x": 3, "y": 30},
        ]

        updates, visited = self.run_graph(rows, method="invented")

        self.assertEqual(visited, ["analysis", "blocked"])
        self.assertEqual(
            updates[0]["analysis"]["result"]["reason"],
            "invalid_request",
        )

    def test_graph_preserves_source(self):
        rows = [
            {"x": 1, "y": 10},
            {"x": 2, "y": 20},
            {"x": 3, "y": 30},
        ]
        original = copy.deepcopy(rows)

        self.run_graph(rows)

        self.assertEqual(rows, original)


if __name__ == "__main__":
    unittest.main()
