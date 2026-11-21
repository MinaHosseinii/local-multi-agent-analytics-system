def validate_correlation_request(request):
    """Validate a proposed request before allowing tool execution."""
    required = {"operation", "method", "columns"}

    if not isinstance(request, dict) or set(request) != required:
        return {
            "status": "invalid",
            "message": "Expected operation, method, and columns.",
        }

    if request["operation"] != "correlation":
        return {
            "status": "unsupported",
            "message": "This validator supports correlation only.",
        }

    columns = request["columns"]

    if (
        not isinstance(columns, list)
        or len(columns) != 2
        or not all(isinstance(column, str) for column in columns)
    ):
        return {
            "status": "invalid",
            "message": "Provide exactly two column names.",
        }

    supported_pair = {
        "marketing_cost_eur",
        "order_value_eur",
    }

    if set(columns) != supported_pair:
        return {
            "status": "unsupported",
            "message": (
                "Supported columns are marketing_cost_eur "
                "and order_value_eur."
            ),
        }

    method = request["method"]

    if method is None:
        return {
            "status": "clarify",
            "message": "Which method: Pearson, Spearman, or Kendall?",
        }

    if (
        not isinstance(method, str)
        or method not in {"pearson", "spearman", "kendall"}
    ):
        return {
            "status": "unsupported",
            "message": "Supported methods: pearson, spearman, kendall.",
        }

    return {
        "status": "ready",
        "method": method,
        "columns": list(columns),
    }
