import copy
import unittest

from messy_orders import MESSY_ROWS
from cleaning_proposal import propose_cleaning


class TestCleaningProposal(unittest.TestCase):
    def setUp(self):
        self.rows = copy.deepcopy(MESSY_ROWS)

    def test_only_expected_changes_are_proposed(self):
        proposal = propose_cleaning(self.rows)

        self.assertEqual(proposal["changes"], [
            {
                "operation": "remove_exact_duplicate",
                "source_row": 3,
                "kept_source_row": 1,
            },
            {
                "operation": "normalize_date",
                "source_row": 6,
                "before": "03.11.2026",
                "after": "2026-11-03",
            },
        ])
        self.assertEqual(proposal["rows_before"], 12)
        self.assertEqual(proposal["rows_after"], 11)

    def test_candidate_matches_expected_records(self):
        expected = copy.deepcopy(self.rows)
        expected[5]["order_date"] = "2026-11-03"
        del expected[2]

        proposal = propose_cleaning(self.rows)

        self.assertEqual(proposal["candidate_rows"], expected)

    def test_source_mapping_is_correct(self):
        proposal = propose_cleaning(self.rows)

        self.assertEqual(
            proposal["source_row_numbers"],
            [1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        )

    def test_unresolved_problems_remain_flagged(self):
        quality = propose_cleaning(self.rows)["candidate_quality"]

        # Positions now refer to the 11-row candidate.
        self.assertEqual(quality["keys"]["invalid_keys"], [8])
        self.assertEqual(
            quality["keys"]["repeated_keys"],
            [{
                "order_id": "O102",
                "line_id": 1,
                "rows": [3, 4],
                "classification": "conflict",
            }],
        )
        self.assertEqual(quality["dates"]["invalid_count"], 2)
        self.assertEqual(
            quality["numeric_columns"]["line_value_eur"]["missing_count"],
            1,
        )
        self.assertEqual(
            quality["numeric_columns"]["line_value_eur"]["invalid_count"],
            2,
        )

    def test_source_and_candidate_are_independent(self):
        original = copy.deepcopy(self.rows)
        proposal = propose_cleaning(self.rows)

        self.assertEqual(self.rows, original)

        proposal["candidate_rows"][0]["quantity"] = 999

        self.assertEqual(self.rows, original)

    def test_second_proposal_has_no_further_changes(self):
        first = propose_cleaning(self.rows)
        second = propose_cleaning(first["candidate_rows"])

        self.assertEqual(second["changes"], [])
        self.assertEqual(
            second["candidate_rows"],
            first["candidate_rows"],
        )


if __name__ == "__main__":
    unittest.main()
