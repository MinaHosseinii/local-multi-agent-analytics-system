import copy
import json
import unittest
from unittest.mock import patch

from supervisor_graph import graph


class TestCorrelationWorkflow(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {
                "order_id": "O01",
                "marketing_cost_eur": 10.0,
                "order_value_eur": 80.0,
            },
            {
                "order_id": "O02",
                "marketing_cost_eur": 20.0,
                "order_value_eur": 120.0,
            },
            {
                "order_id": "O03",
                "marketing_cost_eur": 30.0,
                "order_value_eur": None,
            },
            {
                "order_id": "O04",
                "marketing_cost_eur": 40.0,
                "order_value_eur": 200.0,
            },
            {
                "order_id": "O05",
                "marketing_cost_eur": 50.0,
                "order_value_eur": 100.0,
            },
        ]

    def run_workflow(self, rows, method="spearman"):
        state = {
            "question": (
                f"Calculate {method} correlation between "
                "marketing cost and order value."
            ),
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

        with (
            patch(
                "supervisor_graph.chat",
                return_value=json.dumps({
                    "task": f"correlation_{method}"
                }),
            ) as model,
            patch(
                "supervisor_graph.extract_and_validate",
                return_value={
                    "request": {
                        "operation": "correlation",
                        "method": method,
                        "columns": [
                            "marketing_cost_eur",
                            "order_value_eur",
                        ],
                    },
                    "validation": {
                        "status": "ready",
                        "method": method,
                        "columns": [
                            "marketing_cost_eur",
                            "order_value_eur",
                        ],
                    },
                },
            ),
            patch("langchain_tools.ROWS", rows),
        ):
            updates = list(graph.stream(
                state,
                stream_mode="updates",
            ))

        # Correlation reporting should not call the model again.
        self.assertEqual(model.call_count, 1)

        visited = []
        final_state = dict(state)

        for update in updates:
            for node, changes in update.items():
                visited.append(node)
                final_state.update(changes)

        return final_state, visited

    def test_known_spearman_result_and_missing_pair(self):
        state, visited = self.run_workflow(self.rows)

        self.assertEqual(
            visited,
            ["supervisor", "validate_request", "correlation", "correlation_report"],
        )
        self.assertEqual(state["status"], "completed")
        self.assertAlmostEqual(
            state["calculation"]["coefficient"], 0.4
        )
        self.assertEqual(
            state["calculation"]["included_rows"], [1, 2, 4, 5]
        )
        self.assertEqual(
            state["calculation"]["excluded_rows"],
            [{
                "row": 3,
                "reason": "missing_value",
                "columns": ["order_value_eur"],
            }],
        )
        self.assertIn("0.4000", state["answer"])

    def test_all_three_methods_reach_the_correct_tool_method(self):
        for method in ("pearson", "spearman", "kendall"):
            with self.subTest(method=method):
                state, visited = self.run_workflow(
                    self.rows, method
                )

                self.assertEqual(state["status"], "completed")
                self.assertEqual(
                    state["calculation"]["method"], method
                )
                self.assertEqual(
                    visited[-1], "correlation_report"
                )

    def test_invalid_text_blocks_reporting(self):
        self.rows[1]["order_value_eur"] = "invalid"

        state, visited = self.run_workflow(self.rows)

        self.assertEqual(
            visited,
            ["supervisor", "validate_request", "correlation", "analysis_blocked"],
        )
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(state["calculation"], {})
        self.assertEqual(
            state["analysis_error"]["invalid_values"],
            [{
                "row": 2,
                "column": "order_value_eur",
                "reason": "not_numeric",
            }],
        )

    def test_missing_column_blocks_reporting(self):
        del self.rows[0]["marketing_cost_eur"]

        state, visited = self.run_workflow(self.rows)

        self.assertEqual(state["status"], "blocked")
        self.assertNotIn("correlation_report", visited)
        self.assertEqual(
            state["analysis_error"]["invalid_values"],
            [{
                "row": 1,
                "column": "marketing_cost_eur",
                "reason": "missing_field",
            }],
        )

    def test_constant_column_blocks_reporting(self):
        for row in self.rows:
            row["marketing_cost_eur"] = 10.0

        state, visited = self.run_workflow(self.rows)

        self.assertEqual(state["status"], "blocked")
        self.assertEqual(
            state["analysis_error"]["reason"],
            "constant_column",
        )
        self.assertNotIn("correlation_report", visited)

    def test_insufficient_pairs_block_reporting(self):
        state, visited = self.run_workflow(self.rows[:2])

        self.assertEqual(state["status"], "blocked")
        self.assertEqual(
            state["analysis_error"]["reason"],
            "insufficient_pairs",
        )
        self.assertNotIn("correlation_report", visited)

    def test_source_records_are_preserved(self):
        original = copy.deepcopy(self.rows)

        self.run_workflow(self.rows)

        self.assertEqual(self.rows, original)


if __name__ == "__main__":
    unittest.main()
