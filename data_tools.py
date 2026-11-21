from statistics import mean

# Synthetic customer-order data.
# None means the order value was not recorded.
ROWS = [
    {"order_id": "O01", "customer_type": "new", "order_value_eur": 80.0, "marketing_cost_eur": 10.0},
    {"order_id": "O02", "customer_type": "returning", "order_value_eur": 120.0, "marketing_cost_eur": 20.0},
    {"order_id": "O03", "customer_type": "new", "order_value_eur": None, "marketing_cost_eur": 30.0},
    {"order_id": "O04", "customer_type": "returning", "order_value_eur": 200.0, "marketing_cost_eur": 40.0},
    {"order_id": "O05", "customer_type": "new", "order_value_eur": 100.0, "marketing_cost_eur": 50.0},
]


def inspect_dataset():
    """Report row count, available columns, and missing values."""
    columns = sorted({column for row in ROWS for column in row})

    return {
        "row_count": len(ROWS),
        "columns": columns,
        "missing_counts": {
            column: sum(row.get(column) is None for row in ROWS)
            for column in columns
        },
    }


def calculate_mean(column):
    """Calculate a numeric column's mean, excluding missing values."""
    columns = {key for row in ROWS for key in row}

    if column not in columns:
        raise ValueError(f"Unknown column: {column}")

    values = []

    for row in ROWS:
        value = row.get(column)

        if value is None:
            continue

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Column '{column}' is not numeric.")

        values.append(value)

    if not values:
        raise ValueError(f"Column '{column}' has no observed values.")

    return {
        "column": column,
        "mean": mean(values),
        "values_used": len(values),
        "missing_excluded": len(ROWS) - len(values),
    }

#This function accepts data as an argument, rather than reading the global ROWS. That makes it easier to test different inputs and later use it with multiple datasets.
def validate_order_keys(rows):
    """Detect invalid keys, exact duplicates, and conflicting order lines."""
    groups = {}
    invalid_keys = []

    for row_number, row in enumerate(rows, start=1):
        order_id = row.get("order_id")
        line_id = row.get("line_id")

        valid_order_id = (
            isinstance(order_id, str)
            and bool(order_id.strip())
            and order_id == order_id.strip()
        )

        valid_line_id = type(line_id) is int and line_id > 0

        if not valid_order_id or not valid_line_id:
            invalid_keys.append(row_number)
            continue

        key = (order_id, line_id)
        groups.setdefault(key, []).append((row_number, row))

    repeated_keys = []

    for (order_id, line_id), records in groups.items():
        if len(records) < 2:
            continue

        first_record = records[0][1]
        identical = all(
            row == first_record for _, row in records
        )

        repeated_keys.append({
            "order_id": order_id,
            "line_id": line_id,
            "rows": [number for number, _ in records],
            "classification": (
                "exact_duplicate" if identical else "conflict"
            ),
        })

    return {
        "row_count": len(rows),
        "invalid_keys": invalid_keys,
        "repeated_keys": repeated_keys,
    }


def validate_order_dates(rows, column="order_date"):
    """Validate agreed date formats without modifying source rows."""
    import re
    from datetime import datetime

    accepted_formats = [
        (r"[0-9]{4}-[0-9]{2}-[0-9]{2}", "%Y-%m-%d"),
        (r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}", "%d.%m.%Y"),
    ]

    checks = []

    for row_number, row in enumerate(rows, start=1):
        check = {
            "row": row_number,
            "status": "invalid",
            "normalized_date": None,
            "reason": "",
        }

        if column not in row:
            check["reason"] = "missing_field"

        else:
            value = row[column]

            if value is None or (
                isinstance(value, str) and not value.strip()
            ):
                check["status"] = "missing"
                check["reason"] = "missing_value"

            elif not isinstance(value, str):
                check["reason"] = "invalid_type"

            else:
                matched_format = next(
                    (
                        date_format
                        for pattern, date_format in accepted_formats
                        if re.fullmatch(pattern, value)
                    ),
                    None,
                )

                if matched_format is None:
                    check["reason"] = "unsupported_format"

                else:
                    try:
                        parsed = datetime.strptime(
                            value, matched_format
                        ).date()

                        check["status"] = "valid"
                        check["normalized_date"] = parsed.isoformat()

                    except ValueError:
                        check["reason"] = "impossible_date"

        checks.append(check)

    return {
        "row_count": len(rows),
        "valid_count": sum(c["status"] == "valid" for c in checks),
        "missing_count": sum(c["status"] == "missing" for c in checks),
        "invalid_count": sum(c["status"] == "invalid" for c in checks),
        "checks": checks,
    }


def deduplicate_order_lines(rows):
    """Remove confirmed duplicates without changing the source data."""
    import copy

    validation = validate_order_keys(rows)

    removed_numbers = set()
    removed_rows = []

    for group in validation["repeated_keys"]:
        # Preserve the entire group if its records disagree.
        if group["classification"] != "exact_duplicate":
            continue

        kept_number = group["rows"][0]

        for removed_number in group["rows"][1:]:
            removed_numbers.add(removed_number)

            removed_rows.append({
                "source_row": removed_number,
                "kept_source_row": kept_number,
                "reason": "exact_duplicate",
                "record": copy.deepcopy(rows[removed_number - 1]),
            })

    cleaned_rows = [
        copy.deepcopy(row)
        for row_number, row in enumerate(rows, start=1)
        if row_number not in removed_numbers
    ]

    return {
        "rows": cleaned_rows,
        "audit": {
            "rows_before": len(rows),
            "rows_after": len(cleaned_rows),
            "removed_count": len(removed_rows),
            "removed_rows": removed_rows,
        },
        "unresolved": {
            "invalid_key_rows": validation["invalid_keys"],
            "conflicting_keys": [
                copy.deepcopy(group)
                for group in validation["repeated_keys"]
                if group["classification"] == "conflict"
            ],
        },
    }

def validate_numeric_column(rows, column):
    """Check numeric values without changing or silently converting them."""
    import math

    checks = []

    for row_number, row in enumerate(rows, start=1):
        check = {
            "row": row_number,
            "status": "invalid",
            "reason": "",
        }

        if column not in row:
            check["reason"] = "missing_field"
        else:
            value = row[column]

            if value is None:
                check["status"] = "missing"
                check["reason"] = "missing_value"

            elif isinstance(value, bool):
                # Python considers bool a subtype of int.
                check["reason"] = "boolean_not_allowed"

            elif not isinstance(value, (int, float)):
                check["reason"] = "not_numeric"

            elif isinstance(value, float) and not math.isfinite(value):
                check["reason"] = "non_finite"

            else:
                check["status"] = "valid"

        checks.append(check)

    return {
        "column": column,
        "row_count": len(rows),
        "valid_count": sum(c["status"] == "valid" for c in checks),
        "missing_count": sum(c["status"] == "missing" for c in checks),
        "invalid_count": sum(c["status"] == "invalid" for c in checks),
        "checks": checks,
    }


def prepare_numeric_pairs(rows, x_column, y_column):
    """Prepare aligned pairs, excluding only explicitly missing values."""
    if x_column == y_column:
        raise ValueError("Choose two different columns.")

    x_report = validate_numeric_column(rows, x_column)
    y_report = validate_numeric_column(rows, y_column)

    invalid_values = []

    for column, report in (
        (x_column, x_report),
        (y_column, y_report),
    ):
        for check in report["checks"]:
            if check["status"] == "invalid":
                invalid_values.append({
                    "row": check["row"],
                    "column": column,
                    "reason": check["reason"],
                })

    # Invalid data blocks the calculation rather than being silently dropped.
    if invalid_values:
        return {
            "ok": False,
            "error": "Invalid data must be resolved before analysis.",
            "invalid_values": invalid_values,
        }

    pairs = []
    included_rows = []
    excluded_rows = []

    for row_number, (row, x_check, y_check) in enumerate(
        zip(rows, x_report["checks"], y_report["checks"]),
        start=1,
    ):
        missing_columns = [
            column
            for column, check in (
                (x_column, x_check),
                (y_column, y_check),
            )
            if check["status"] == "missing"
        ]

        if missing_columns:
            excluded_rows.append({
                "row": row_number,
                "reason": "missing_value",
                "columns": missing_columns,
            })
            continue

        pairs.append([row[x_column], row[y_column]])
        included_rows.append(row_number)

    return {
        "ok": True,
        "x_column": x_column,
        "y_column": y_column,
        "rows_before": len(rows),
        "pairs_used": len(pairs),
        "pairs": pairs,
        "included_rows": included_rows,
        "excluded_rows": excluded_rows,
    }


def calculate_correlation(rows, x_column, y_column, method="pearson"):
    """Calculate a correlation coefficient from validated paired data."""
    import math
    import warnings
    from scipy import stats

    methods = {
        "pearson": stats.pearsonr,
        "spearman": stats.spearmanr,
        "kendall": stats.kendalltau,
    }

    if not isinstance(method, str) or method not in methods:
        raise ValueError(
            "Method must be 'pearson', 'spearman', or 'kendall'."
        )

    prepared = prepare_numeric_pairs(rows, x_column, y_column)

    if not prepared["ok"]:
        return prepared

    metadata = {
        "method": method,
        "x_column": x_column,
        "y_column": y_column,
        "pairs_used": prepared["pairs_used"],
        "included_rows": prepared["included_rows"],
        "excluded_rows": prepared["excluded_rows"],
    }

    # Course policy: require at least three complete pairs.
    # This minimum does not guarantee a reliable statistical conclusion.
    if prepared["pairs_used"] < 3:
        return {
            **metadata,
            "ok": False,
            "reason": "insufficient_pairs",
        }

    x = [pair[0] for pair in prepared["pairs"]]
    y = [pair[1] for pair in prepared["pairs"]]

    if len(set(x)) == 1 or len(set(y)) == 1:
        return {
            **metadata,
            "ok": False,
            "reason": "constant_column",
        }

    try:
        # Treat numerical warnings as a failed calculation.
        with warnings.catch_warnings():
            warnings.simplefilter("error")

            if method == "kendall":
                result = stats.kendalltau(x, y, variant="b")
            else:
                result = methods[method](x, y)

            coefficient = float(result.statistic)

    except (Warning, ValueError, OverflowError, FloatingPointError) as error:
        return {
            **metadata,
            "ok": False,
            "reason": "numerical_problem",
            "detail": str(error),
        }

    if not math.isfinite(coefficient) or not -1 <= coefficient <= 1:
        return {
            **metadata,
            "ok": False,
            "reason": "invalid_coefficient",
        }

    return {
        **metadata,
        "ok": True,
        "coefficient": coefficient,
    }


if __name__ == "__main__":
    import json

    print("INSPECTION:")
    print(json.dumps(inspect_dataset(), indent=2))

    print("\nCALCULATION:")
    print(json.dumps(calculate_mean("order_value_eur"), indent=2))
