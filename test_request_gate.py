import unittest
from unittest.mock import patch

from supervisor_graph import graph


class TestRequestGate(unittest.TestCase):
    def run_case(self, question, extracted_request, supervisor_response='{"task":"correlation_spearman"}'):
        state = {
            "question": question,
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
            "request_validation": {},
        }

        with (
            # Deliberately simulate a wrong initial classification.
            patch(
                "supervisor_graph.chat",
                return_value=supervisor_response,
            ),
            # Supply extracted fields, but use the REAL validator.
            patch(
                "correlation_request.chat",
                return_value=extracted_request,
            ),
            # Replace the tool so we can verify it was never called.
            patch(
                "supervisor_graph.correlate_orders"
            ) as tool,
        ):
            updates = list(graph.stream(
                state,
                stream_mode="updates",
            ))

            tool.invoke.assert_not_called()

        visited = []
        final_state = dict(state)

        for update in updates:
            for node, changes in update.items():
                visited.append(node)
                final_state.update(changes)

        self.assertEqual(
            visited,
            ["supervisor", "validate_request", "request_stopped"],
        )
        self.assertEqual(final_state["calculation"], {})

        return final_state

    def test_missing_method_stops_for_clarification(self):
        state = self.run_case(
            "Calculate correlation between marketing cost and order value.",
            (
                '{"operation":"correlation","method":null,'
                '"columns":["marketing_cost_eur","order_value_eur"]}'
            ),
        )

        self.assertEqual(state["status"], "clarify")
        self.assertIn("Which method", state["answer"])

    def test_unsupported_columns_stop_execution(self):
        state = self.run_case(
            "Calculate Pearson correlation between age and salary.",
            (
                '{"operation":"correlation","method":"pearson",'
                '"columns":["age","salary"]}'
            ),
        )

        self.assertEqual(state["status"], "unsupported")

    def test_prediction_stops_execution(self):
        state = self.run_case(
            "Predict next month's sales.",
            '{"operation":"predict","method":null,"columns":[]}',
        )

        self.assertEqual(state["status"], "unsupported")

    def test_invalid_model_json_stops_execution(self):
        state = self.run_case(
            "Calculate correlation between marketing cost and order value.",
            "This is not JSON.",
        )

        self.assertEqual(state["status"], "invalid")

    def test_invalid_supervisor_task_does_not_crash(self):
        state = self.run_case(
            question="Predict next month's sales.",
            extracted_request=(
                '{"operation":"predict","method":null,"columns":[]}'
            ),
            supervisor_response='{"task":"predict"}',
        )

        self.assertEqual(state["status"], "unsupported")


if __name__ == "__main__":
    unittest.main()
