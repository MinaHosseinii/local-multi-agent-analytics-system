import copy
import unittest

from data_tools import validate_order_keys
from data_tools import validate_order_keys, validate_order_dates
from data_tools import deduplicate_order_lines
from data_tools import validate_numeric_column
from data_tools import prepare_numeric_pairs
from data_tools import calculate_correlation


class TestOrderKeys(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"order_id": "O01", "line_id": 1, "quantity": 2},
            {"order_id": "O01", "line_id": 2, "quantity": 1},

            {"order_id": "O02", "line_id": 1, "quantity": 1},
            {"order_id": "O02", "line_id": 1, "quantity": 1},

            {"order_id": "O03", "line_id": 1, "quantity": 1},
            {"order_id": "O03", "line_id": 1, "quantity": 3},

            {"order_id": None, "line_id": 1, "quantity": 1},
        ]

    def test_different_lines_in_same_order_are_valid(self):
        result = validate_order_keys(self.rows[:2])
        self.assertEqual(result["invalid_keys"], [])
        self.assertEqual(result["repeated_keys"], [])

    def test_exact_duplicate_is_detected(self):
        result = validate_order_keys(self.rows)
        self.assertEqual(result["repeated_keys"][0], {
            "order_id": "O02",
            "line_id": 1,
            "rows": [3, 4],
            "classification": "exact_duplicate",
        })

    def test_conflicting_quantity_is_detected(self):
        result = validate_order_keys(self.rows)
        self.assertEqual(result["repeated_keys"][1], {
            "order_id": "O03",
            "line_id": 1,
            "rows": [5, 6],
            "classification": "conflict",
        })

    def test_missing_order_id_is_detected(self):
        result = validate_order_keys(self.rows)
        self.assertEqual(result["invalid_keys"], [7])

    def test_invalid_line_ids_are_rejected(self):
        for line_id in (None, 0, -1, True, "1"):
            with self.subTest(line_id=line_id):
                result = validate_order_keys([
                    {"order_id": "O01", "line_id": line_id}
                ])
                self.assertEqual(result["invalid_keys"], [1])

    def test_empty_or_padded_order_ids_are_rejected(self):
        for order_id in ("", "   ", " O01", "O01 "):
            with self.subTest(order_id=order_id):
                result = validate_order_keys([
                    {"order_id": order_id, "line_id": 1}
                ])
                self.assertEqual(result["invalid_keys"], [1])

    def test_source_data_is_preserved(self):
        before = copy.deepcopy(self.rows)
        validate_order_keys(self.rows)
        self.assertEqual(self.rows, before)

    def test_empty_dataset(self):
        self.assertEqual(validate_order_keys([]), {
            "row_count": 0,
            "invalid_keys": [],
            "repeated_keys": [],
        })


class TestOrderDates(unittest.TestCase):
    def check_one(self, value):
        result = validate_order_dates([{"order_date": value}])
        return result["checks"][0]

    def test_iso_date(self):
        result = self.check_one("2026-04-03")
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["normalized_date"], "2026-04-03")

    def test_day_month_year_date(self):
        result = self.check_one("03.04.2026")
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["normalized_date"], "2026-04-03")

    def test_slash_format_is_not_guessed(self):
        result = self.check_one("03/04/2026")
        self.assertEqual(result["reason"], "unsupported_format")
        self.assertIsNone(result["normalized_date"])

    def test_impossible_date(self):
        result = self.check_one("2026-02-30")
        self.assertEqual(result["reason"], "impossible_date")

    def test_leap_year(self):
        self.assertEqual(
            self.check_one("2024-02-29")["status"], "valid"
        )
        self.assertEqual(
            self.check_one("2025-02-29")["reason"], "impossible_date"
        )

    def test_missing_values(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                self.assertEqual(
                    self.check_one(value)["status"], "missing"
                )

    def test_missing_field(self):
        result = validate_order_dates([{"order_id": "O01"}])
        self.assertEqual(
            result["checks"][0]["reason"], "missing_field"
        )

    def test_numeric_value_rejected(self):
        self.assertEqual(
            self.check_one(20260403)["reason"], "invalid_type"
        )

    def test_source_data_preserved(self):
        rows = [{"order_date": "03.04.2026"}]
        before = copy.deepcopy(rows)

        validate_order_dates(rows)

        self.assertEqual(rows, before)


class TestDeduplication(unittest.TestCase):
    def test_exact_duplicate_removed_and_audited(self):
        rows = [
            {"order_id": "O01", "line_id": 1, "quantity": 2},
            {"order_id": "O01", "line_id": 1, "quantity": 2},
        ]

        result = deduplicate_order_lines(rows)

        self.assertEqual(result["rows"], [rows[0]])
        self.assertEqual(result["audit"]["rows_before"], 2)
        self.assertEqual(result["audit"]["rows_after"], 1)
        self.assertEqual(result["audit"]["removed_count"], 1)

        removed = result["audit"]["removed_rows"][0]
        self.assertEqual(removed["source_row"], 2)
        self.assertEqual(removed["kept_source_row"], 1)
        self.assertEqual(removed["reason"], "exact_duplicate")
        self.assertEqual(removed["record"], rows[1])

    def test_conflicting_group_is_preserved_entirely(self):
        rows = [
            {"order_id": "O01", "line_id": 1, "quantity": 2},
            {"order_id": "O01", "line_id": 1, "quantity": 2},
            {"order_id": "O01", "line_id": 1, "quantity": 3},
        ]

        result = deduplicate_order_lines(rows)

        self.assertEqual(result["rows"], rows)
        self.assertEqual(result["audit"]["removed_count"], 0)
        self.assertEqual(
            result["unresolved"]["conflicting_keys"][0]["rows"],
            [1, 2, 3],
        )

    def test_invalid_keys_are_preserved(self):
        rows = [
            {"order_id": None, "line_id": 1, "quantity": 2},
            {"order_id": None, "line_id": 1, "quantity": 2},
        ]

        result = deduplicate_order_lines(rows)

        self.assertEqual(result["rows"], rows)
        self.assertEqual(result["audit"]["removed_count"], 0)
        self.assertEqual(
            result["unresolved"]["invalid_key_rows"], [1, 2]
        )

    def test_different_lines_and_order_are_preserved(self):
        rows = [
            {"order_id": "O01", "line_id": 2, "quantity": 2},
            {"order_id": "O01", "line_id": 1, "quantity": 2},
            {"order_id": "O02", "line_id": 1, "quantity": 2},
        ]

        result = deduplicate_order_lines(rows)

        self.assertEqual(result["rows"], rows)
        self.assertEqual(result["audit"]["removed_count"], 0)

    def test_source_preserved_and_output_independent(self):
        rows = [
            {"order_id": "O01", "line_id": 1, "quantity": 2},
            {"order_id": "O01", "line_id": 1, "quantity": 2},
        ]
        original = copy.deepcopy(rows)

        result = deduplicate_order_lines(rows)
        self.assertEqual(rows, original)

        # Changing the output must not change the original records.
        result["rows"][0]["quantity"] = 999
        result["audit"]["removed_rows"][0]["record"]["quantity"] = 888

        self.assertEqual(rows, original)

    def test_second_run_makes_no_further_changes(self):
        rows = [
            {"order_id": "O01", "line_id": 1, "quantity": 2},
            {"order_id": "O01", "line_id": 1, "quantity": 2},
            {"order_id": "O02", "line_id": 1, "quantity": 3},
        ]

        first = deduplicate_order_lines(rows)
        second = deduplicate_order_lines(first["rows"])

        self.assertEqual(second["rows"], first["rows"])
        self.assertEqual(second["audit"]["removed_count"], 0)
        self.assertEqual(
            first["audit"]["rows_before"],
            first["audit"]["rows_after"]
            + first["audit"]["removed_count"],
        )

    def test_empty_dataset(self):
        result = deduplicate_order_lines([])

        self.assertEqual(result["rows"], [])
        self.assertEqual(result["audit"]["rows_before"], 0)
        self.assertEqual(result["audit"]["rows_after"], 0)
        self.assertEqual(result["audit"]["removed_count"], 0)
        self.assertEqual(result["unresolved"]["invalid_key_rows"], [])
        self.assertEqual(result["unresolved"]["conflicting_keys"], [])


class TestNumericColumn(unittest.TestCase):
    def test_regular_numbers_are_valid(self):
        rows = [{"value": value} for value in [0, -5, 12, 12.5]]

        result = validate_numeric_column(rows, "value")

        self.assertEqual(result["valid_count"], 4)
        self.assertEqual(result["invalid_count"], 0)

    def test_missing_value_and_missing_field_are_distinct(self):
        result = validate_numeric_column(
            [{"value": None}, {}], "value"
        )

        self.assertEqual(result["missing_count"], 1)
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(
            result["checks"][0]["reason"], "missing_value"
        )
        self.assertEqual(
            result["checks"][1]["reason"], "missing_field"
        )

    def test_text_and_booleans_are_rejected(self):
        rows = [
            {"value": "125"},
            {"value": ""},
            {"value": True},
            {"value": False},
        ]

        result = validate_numeric_column(rows, "value")

        self.assertEqual(result["invalid_count"], 4)
        self.assertEqual(
            [check["reason"] for check in result["checks"]],
            [
                "not_numeric",
                "not_numeric",
                "boolean_not_allowed",
                "boolean_not_allowed",
            ],
        )

    def test_nan_and_infinity_are_rejected(self):
        rows = [
            {"value": float("nan")},
            {"value": float("inf")},
            {"value": float("-inf")},
        ]

        result = validate_numeric_column(rows, "value")

        self.assertEqual(result["invalid_count"], 3)
        self.assertTrue(all(
            check["reason"] == "non_finite"
            for check in result["checks"]
        ))

    def test_source_is_preserved_and_counts_balance(self):
        rows = [
            {"value": 125.0},
            {"value": None},
            {"value": "invalid"},
        ]
        original = copy.deepcopy(rows)

        result = validate_numeric_column(rows, "value")

        self.assertEqual(rows, original)
        self.assertEqual(result["valid_count"], 1)
        self.assertEqual(result["missing_count"], 1)
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(
            result["row_count"],
            result["valid_count"]
            + result["missing_count"]
            + result["invalid_count"],
        )

    def test_empty_dataset(self):
        result = validate_numeric_column([], "value")

        self.assertEqual(result["row_count"], 0)
        self.assertEqual(result["checks"], [])
        self.assertEqual(result["valid_count"], 0)
        self.assertEqual(result["missing_count"], 0)
        self.assertEqual(result["invalid_count"], 0)

class TestNumericPairs(unittest.TestCase):
    def test_pairs_remain_aligned(self):
        rows = [
            {"advertising": 100, "revenue": 300},
            {"advertising": None, "revenue": 400},
            {"advertising": 200, "revenue": None},
            {"advertising": 300, "revenue": 800},
        ]

        result = prepare_numeric_pairs(
            rows, "advertising", "revenue"
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["pairs"], [[100, 300], [300, 800]])
        self.assertEqual(result["included_rows"], [1, 4])
        self.assertEqual(result["pairs_used"], 2)
        self.assertEqual(
            result["excluded_rows"],
            [
                {
                    "row": 2,
                    "reason": "missing_value",
                    "columns": ["advertising"],
                },
                {
                    "row": 3,
                    "reason": "missing_value",
                    "columns": ["revenue"],
                },
            ],
        )
        self.assertEqual(
            result["rows_before"],
            result["pairs_used"] + len(result["excluded_rows"]),
        )

    def test_both_missing_counts_as_one_excluded_row(self):
        result = prepare_numeric_pairs(
            [{"x": None, "y": None}], "x", "y"
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["pairs_used"], 0)
        self.assertEqual(len(result["excluded_rows"]), 1)
        self.assertEqual(
            result["excluded_rows"][0]["columns"], ["x", "y"]
        )

    def test_invalid_numbers_block_preparation(self):
        for invalid in ["100", True, float("nan"), float("inf")]:
            with self.subTest(value=invalid):
                result = prepare_numeric_pairs(
                    [{"x": 1, "y": invalid}], "x", "y"
                )

                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["invalid_values"][0]["column"], "y"
                )
                self.assertNotIn("pairs", result)

    def test_missing_field_blocks_preparation(self):
        result = prepare_numeric_pairs(
            [{"x": 1}], "x", "y"
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["invalid_values"],
            [{"row": 1, "column": "y", "reason": "missing_field"}],
        )

    def test_same_column_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare_numeric_pairs(
                [{"x": 1}], "x", "x"
            )

    def test_source_data_is_preserved(self):
        rows = [
            {"x": 1, "y": 10},
            {"x": None, "y": 20},
        ]
        original = copy.deepcopy(rows)

        result = prepare_numeric_pairs(rows, "x", "y")
        result["pairs"][0][0] = 999

        self.assertEqual(rows, original)

    def test_empty_dataset(self):
        result = prepare_numeric_pairs([], "x", "y")

        self.assertTrue(result["ok"])
        self.assertEqual(result["rows_before"], 0)
        self.assertEqual(result["pairs_used"], 0)
        self.assertEqual(result["pairs"], [])
        self.assertEqual(result["excluded_rows"], [])
        

class TestCorrelation(unittest.TestCase):
    def make_rows(self, x, y):
        return [
            {"x": first, "y": second}
            for first, second in zip(x, y)
        ]

    def test_perfect_positive_relationship(self):
        rows = self.make_rows([1, 2, 3, 4], [10, 20, 30, 40])

        for method in ("pearson", "spearman", "kendall"):
            with self.subTest(method=method):
                result = calculate_correlation(rows, "x", "y", method)

                self.assertTrue(result["ok"])
                self.assertAlmostEqual(result["coefficient"], 1.0)

    def test_perfect_negative_relationship(self):
        rows = self.make_rows([1, 2, 3, 4], [40, 30, 20, 10])

        for method in ("pearson", "spearman", "kendall"):
            with self.subTest(method=method):
                result = calculate_correlation(rows, "x", "y", method)

                self.assertTrue(result["ok"])
                self.assertAlmostEqual(result["coefficient"], -1.0)

    def test_rank_methods_differ_from_pearson(self):
        # Increasing, but not a straight-line relationship.
        rows = self.make_rows([1, 2, 3, 4], [1, 4, 9, 16])

        pearson = calculate_correlation(rows, "x", "y", "pearson")
        spearman = calculate_correlation(rows, "x", "y", "spearman")
        kendall = calculate_correlation(rows, "x", "y", "kendall")

        self.assertTrue(pearson["ok"])
        self.assertLess(pearson["coefficient"], 0.99)
        self.assertAlmostEqual(spearman["coefficient"], 1.0)
        self.assertAlmostEqual(kendall["coefficient"], 1.0)

    def test_missing_pairs_are_excluded_and_reported(self):
        rows = [
            {"x": 1, "y": 10},
            {"x": None, "y": 999},
            {"x": 2, "y": 20},
            {"x": 3, "y": 30},
        ]

        result = calculate_correlation(rows, "x", "y")

        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["coefficient"], 1.0)
        self.assertEqual(result["pairs_used"], 3)
        self.assertEqual(result["included_rows"], [1, 3, 4])
        self.assertEqual(result["excluded_rows"][0]["row"], 2)

    def test_too_few_pairs_are_rejected(self):
        for rows in (
            [],
            [{"x": 1, "y": 10}],
            [{"x": 1, "y": 10}, {"x": 2, "y": 20}],
        ):
            with self.subTest(rows=rows):
                result = calculate_correlation(rows, "x", "y")

                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["reason"], "insufficient_pairs"
                )

    def test_either_constant_column_is_rejected(self):
        for method in ("pearson", "spearman", "kendall"):
            for x, y in (
                ([1, 1, 1], [10, 20, 30]),
                ([1, 2, 3], [10, 10, 10]),
            ):
                with self.subTest(method=method, x=x, y=y):
                    result = calculate_correlation(
                        self.make_rows(x, y), "x", "y", method
                    )

                    self.assertFalse(result["ok"])
                    self.assertEqual(
                        result["reason"], "constant_column"
                    )

    def test_invalid_data_blocks_calculation(self):
        rows = self.make_rows([1, 2, 3], [10, "20", 30])

        result = calculate_correlation(rows, "x", "y")

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["invalid_values"],
            [{"row": 2, "column": "y", "reason": "not_numeric"}],
        )
        self.assertNotIn("coefficient", result)

    def test_unknown_method_is_rejected(self):
        rows = self.make_rows([1, 2, 3], [10, 20, 30])

        with self.assertRaises(ValueError):
            calculate_correlation(rows, "x", "y", "unknown")

    def test_kendall_handles_ties(self):
        rows = self.make_rows([1, 1, 2, 3], [10, 10, 20, 30])

        result = calculate_correlation(rows, "x", "y", "kendall")

        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["coefficient"], 1.0)

    def test_source_data_is_preserved(self):
        rows = self.make_rows([1, 2, 3], [10, 20, 30])
        original = copy.deepcopy(rows)

        calculate_correlation(rows, "x", "y")

        self.assertEqual(rows, original)
        
if __name__ == "__main__":
    unittest.main()
