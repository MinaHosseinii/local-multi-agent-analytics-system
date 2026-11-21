import unittest
from unittest.mock import patch

from supervisor_graph import graph


class TestSupervisorReliability(unittest.TestCase):
    def make_state(self):
        return {
            "question": "What is the average recorded order value?",
            "task": "",
            "inspection": {},
            "calculation": {},
            "answer": "",
            "dashboard": {},
            "report_attempts": 0,
            "review_feedback": "",
            "review_verdict": "",
            "status": "running",
            "report_claims": {},
            "analysis_error": {},
        }

    def run_with_tool(self, **mock_options):
        with (
            patch(
                "supervisor_graph.chat",
                return_value='{"task": "mean"}',
            ) as model,
            patch(
                "supervisor_graph.calculate_mean"
            ) as mock_tool,
        ):
            mock_tool.invoke.configure_mock(**mock_options)

            updates = list(graph.stream(
                self.make_state(),
                stream_mode="updates",
            ))

            mock_tool.invoke.assert_called_once_with({
                "column": "order_value_eur"
            })

        visited = [
            node
            for update in updates
            for node in update
        ]

        self.assertEqual(model.call_count, 1)

        return updates, visited
    

    def test_tool_exception_blocks_downstream_nodes(self):
        updates, visited = self.run_with_tool(
            side_effect=ValueError("No recorded numeric values.")
        )

        self.assertEqual(
            visited,
            ["supervisor", "analysis", "analysis_blocked"],
        )
        self.assertEqual(
            updates[-1]["analysis_blocked"]["status"],
            "blocked",
        )

    def test_non_finite_mean_is_blocked(self):
        updates, visited = self.run_with_tool(
            return_value={
                "column": "order_value_eur",
                "mean": float("nan"),
                "values_used": 4,
                "missing_excluded": 1,
            }
        )

        self.assertEqual(
            visited,
            ["supervisor", "analysis", "analysis_blocked"],
        )
        self.assertEqual(
            updates[1]["analysis"]["calculation"],
            {},
        )


if __name__ == "__main__":
    unittest.main()
