import copy
import math
import tempfile
import unittest
from pathlib import Path

from messy_orders import MESSY_ROWS
from cleaning_proposal import propose_cleaning
from cleaning_approval import decide_proposal
from cleaning_storage import save_decision, load_decision


class TestCleaningStorage(unittest.TestCase):
    def make_result(self, decision="approve"):
        proposal = propose_cleaning(copy.deepcopy(MESSY_ROWS))
        return decide_proposal(proposal, decision)

    def test_approved_copy_and_audit_survive_reload(self):
        result = self.make_result()

        with tempfile.TemporaryDirectory() as directory:
            path = save_decision(result, directory)
            restored = load_decision(path)

        self.assertEqual(restored, result)
        self.assertEqual(len(restored["dataset"]["rows"]), 11)
        self.assertTrue(math.isinf(
            restored["dataset"]["rows"][-1]["line_value_eur"]
        ))
        self.assertEqual(
            restored["dataset"]["quality"]["numeric_columns"]
            ["line_value_eur"]["invalid_count"],
            2,
        )

    def test_rejection_saves_audit_without_dataset(self):
        result = self.make_result("reject")

        with tempfile.TemporaryDirectory() as directory:
            restored = load_decision(save_decision(result, directory))

        self.assertIsNone(restored["dataset"])
        self.assertEqual(restored["audit"]["decision"], "reject")
        self.assertEqual(restored["audit"]["applied_changes"], [])

    def test_existing_decision_cannot_be_overwritten(self):
        result = self.make_result()

        with tempfile.TemporaryDirectory() as directory:
            path = save_decision(result, directory)
            before = Path(path).read_bytes()

            with self.assertRaises(FileExistsError):
                save_decision(result, directory)

            self.assertEqual(Path(path).read_bytes(), before)

    def test_saving_does_not_change_the_result(self):
        result = self.make_result()
        original = copy.deepcopy(result)

        with tempfile.TemporaryDirectory() as directory:
            save_decision(result, directory)

        self.assertEqual(result, original)


if __name__ == "__main__":
    unittest.main()
