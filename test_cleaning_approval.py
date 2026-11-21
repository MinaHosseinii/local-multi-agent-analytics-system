import copy
import unittest

from messy_orders import MESSY_ROWS
from cleaning_proposal import propose_cleaning
from cleaning_approval import decide_proposal


class TestCleaningApproval(unittest.TestCase):
    def setUp(self):
        self.rows = copy.deepcopy(MESSY_ROWS)
        self.proposal = propose_cleaning(self.rows)

    def test_approval_creates_a_separate_copy(self):
        result = decide_proposal(self.proposal, "approve")

        self.assertEqual(result["status"], "approved")
        self.assertEqual(len(result["dataset"]["rows"]), 11)
        self.assertEqual(
            result["audit"]["applied_changes"],
            self.proposal["changes"],
        )
        self.assertTrue(result["audit"]["decision_id"])
        self.assertTrue(result["audit"]["timestamp_utc"])

    def test_rejection_creates_no_dataset(self):
        result = decide_proposal(self.proposal, "reject")

        self.assertEqual(result["status"], "rejected")
        self.assertIsNone(result["dataset"])
        self.assertEqual(result["audit"]["applied_changes"], [])
        self.assertEqual(
            result["audit"]["proposed_changes"],
            self.proposal["changes"],
        )

    def test_invalid_decision_is_rejected(self):
        with self.assertRaises(ValueError):
            decide_proposal(self.proposal, "yes")

    def test_approved_copy_is_independent(self):
        original = copy.deepcopy(self.rows)
        proposal_before = copy.deepcopy(self.proposal)

        result = decide_proposal(self.proposal, "approve")
        result["dataset"]["rows"][0]["quantity"] = 999
        result["audit"]["applied_changes"][0]["source_row"] = 999

        self.assertEqual(self.rows, original)
        self.assertEqual(self.proposal, proposal_before)


if __name__ == "__main__":
    unittest.main()
