import unittest

from request_validation import validate_correlation_request


class TestRequestValidation(unittest.TestCase):
    def make_request(self, method="spearman", columns=None):
        return {
            "operation": "correlation",
            "method": method,
            "columns": (
                ["marketing_cost_eur", "order_value_eur"]
                if columns is None
                else columns
            ),
        }

    def test_supported_methods_are_ready(self):
        for method in ("pearson", "spearman", "kendall"):
            with self.subTest(method=method):
                result = validate_correlation_request(
                    self.make_request(method=method)
                )

                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["method"], method)

    def test_missing_method_requests_clarification(self):
        result = validate_correlation_request(
            self.make_request(method=None)
        )

        self.assertEqual(result["status"], "clarify")

    def test_unsupported_columns_are_rejected(self):
        result = validate_correlation_request(
            self.make_request(
                method="pearson",
                columns=["age", "salary"],
            )
        )

        self.assertEqual(result["status"], "unsupported")

    def test_reversed_column_order_is_supported(self):
        result = validate_correlation_request(
            self.make_request(
                columns=["order_value_eur", "marketing_cost_eur"]
            )
        )

        self.assertEqual(result["status"], "ready")

    def test_unknown_method_is_rejected(self):
        result = validate_correlation_request(
            self.make_request(method="invented")
        )

        self.assertEqual(result["status"], "unsupported")

    def test_malformed_requests_are_rejected(self):
        for request in (
            None,
            {},
            {"operation": "correlation"},
            self.make_request(columns="age,salary"),
            self.make_request(columns=[1, 2]),
        ):
            with self.subTest(request=request):
                result = validate_correlation_request(request)

                self.assertEqual(result["status"], "invalid")

    def test_prediction_operation_is_rejected(self):
        request = self.make_request()
        request["operation"] = "predict"

        result = validate_correlation_request(request)

        self.assertEqual(result["status"], "unsupported")


if __name__ == "__main__":
    unittest.main()
