import json
from pathlib import Path
from urllib.error import URLError

from correlation_request import extract_and_validate


CASES = [
    {
        "question": (
            "Use Pearson to measure the relationship between "
            "order value and marketing cost."
        ),
        "operation": "correlation",
        "method": "pearson",
        "columns": ["marketing_cost_eur", "order_value_eur"],
        "status": "ready",
    },
    {
        "question": (
            "Find the Spearman correlation of marketing cost "
            "and order value."
        ),
        "operation": "correlation",
        "method": "spearman",
        "columns": ["marketing_cost_eur", "order_value_eur"],
        "status": "ready",
    },
    {
        "question": (
            "For marketing cost versus order value, "
            "calculate Kendall correlation."
        ),
        "operation": "correlation",
        "method": "kendall",
        "columns": ["marketing_cost_eur", "order_value_eur"],
        "status": "ready",
    },
    {
        "question": (
            "Are marketing cost and order value correlated?"
        ),
        "operation": "correlation",
        "method": None,
        "columns": ["marketing_cost_eur", "order_value_eur"],
        "status": "clarify",
    },
    {
        "question": (
            "Calculate correlation between order value and marketing cost."
        ),
        "operation": "correlation",
        "method": None,
        "columns": ["marketing_cost_eur", "order_value_eur"],
        "status": "clarify",
    },
    {
        "question": (
            "Use Pearson to calculate correlation between age and salary."
        ),
        "operation": "correlation",
        "method": "pearson",
        "columns": ["age", "salary"],
        "status": "unsupported",
    },
    {
        "question": (
            "Calculate Spearman correlation between "
            "marketing cost and salary."
        ),
        "operation": "correlation",
        "method": "spearman",
        "columns": ["marketing_cost_eur", "salary"],
        "status": "unsupported",
    },
    {
        "question": "Predict next month's sales.",
        "operation": "predict",
        "method": None,
        "columns": [],
        "status": "unsupported",
    },
]


def check_result(case, result):
    request = result["request"]
    validation = result["validation"]
    errors = []

    if not isinstance(request, dict):
        return ["No parsed request."]

    if request.get("operation") != case["operation"]:
        errors.append("Wrong operation.")

    if request.get("method") != case["method"]:
        errors.append("Wrong or invented method.")

    columns = request.get("columns")

    # Column order does not matter for this correlation comparison.
    if (
        not isinstance(columns, list)
        or not all(isinstance(column, str) for column in columns)
        or sorted(columns) != sorted(case["columns"])
    ):
        errors.append("Wrong or substituted columns.")

    if validation.get("status") != case["status"]:
        errors.append("Wrong validation status.")

    return errors


def main():
    records = []

    for number, case in enumerate(CASES, start=1):
        print(
            f"\nCASE {number}/{len(CASES)}: {case['question']}",
            flush=True,
        )

        try:
            result = extract_and_validate(case["question"])
            errors = check_result(case, result)
            outcome = "WRONG" if errors else "PASS"
        except (ValueError, TypeError, URLError, TimeoutError) as error:
            result = None
            errors = [f"{type(error).__name__}: {error}"]
            outcome = "ERROR"

        records.append({
            "case": case,
            "result": result,
            "outcome": outcome,
            "errors": errors,
        })

        print(outcome, flush=True)

        if errors:
            print(" ".join(errors), flush=True)
            print(json.dumps(result, indent=2), flush=True)

    passed = sum(record["outcome"] == "PASS" for record in records)

    output = (
        Path(__file__).resolve().parent
        / "extraction_evaluation.json"
    )
    output.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nPassed: {passed}/{len(CASES)}")
    print(f"Report: {output}")


if __name__ == "__main__":
    main()
