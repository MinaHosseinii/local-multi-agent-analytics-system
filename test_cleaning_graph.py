import tempfile
import unittest
from unittest.mock import patch

from supervisor_graph import graph
from cleaning_storage import load_decision
from evaluate_full_workflow import make_state


class TestCleaningGraph(unittest.TestCase):
    def run_cleaning(self, decision, directory):
        with (
            patch(
                "supervisor_graph.chat",
                return_value='{"task":"cleaning"}',
            ),
            patch("builtins.input", return_value=decision),
            patch(
                "supervisor_graph.CLEANING_DIRECTORY",
                directory,
            ),
        ):
            updates = list(graph.stream(
                make_state("Preview cleaning the messy order dataset."),
                stream_mode="updates",
            ))

        visited = [
            node
            for update in updates
            for node in update
        ]

        self.assertEqual(visited, ["supervisor", "cleaning"])
        return updates[-1]["cleaning"]

    def test_approval_saves_copy_but_flags_analysis_blockers(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cleaning("approve", directory)
            saved = load_decision(
                result["cleaning_result"]["saved_path"]
            )

        self.assertEqual(result["status"], "approved_requires_review")
        self.assertTrue(result["cleaning_result"]["blockers"])
        self.assertEqual(len(saved["dataset"]["rows"]), 11)
        self.assertEqual(len(saved["audit"]["applied_changes"]), 2)

    def test_rejection_saves_only_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cleaning("reject", directory)
            saved = load_decision(
                result["cleaning_result"]["saved_path"]
            )

        self.assertEqual(result["status"], "rejected")
        self.assertIsNone(saved["dataset"])
        self.assertEqual(saved["audit"]["applied_changes"], [])

    def test_invalid_choice_creates_no_saved_record(self):
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cleaning("yes", directory)

            self.assertEqual(list(Path(directory).iterdir()), [])

        self.assertEqual(result["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
