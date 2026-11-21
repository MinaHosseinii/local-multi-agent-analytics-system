import json
from pathlib import Path
from urllib.error import URLError

from supervisor_graph import supervisor


CASES = [
    ("How many orders are there?", "count"),
    ("Tell me the total number of orders.", "count"),

    ("What is the average recorded order value?", "mean"),
    ("Calculate the mean order value.", "mean"),

    (
        "How many orders are there and what is their average value?",
        "count_and_mean",
    ),
    ("Create a customer-order dashboard.", "dashboard"),

    (
        "Calculate Pearson correlation between marketing cost "
        "and order value.",
        "correlation_pearson",
    ),
    (
        "Use Spearman to assess the relationship between "
        "order value and marketing cost.",
        "correlation_spearman",
    ),
    (
        "Calculate Kendall correlation between marketing cost "
        "and order value.",
        "correlation_kendall",
    ),

    # These are outside our current supported tasks.
    (
        "Calculate correlation between marketing cost and order value.",
        "unsupported",
    ),
    (
        "Calculate Pearson correlation between age and salary.",
        "unsupported",
    ),
    ("Predict next month's sales.", "unsupported"),
]


def main():
    results = []

    for number, (question, expected) in enumerate(CASES, start=1):
        print(f"\nCASE {number}/{len(CASES)}: {question}", flush=True)

        actual = None
        error = None

        try:
            actual = supervisor({"question": question})["task"]
        except (ValueError, TypeError, URLError, TimeoutError) as exc:
            error = f"{type(exc).__name__}: {exc}"

        if error:
            outcome = "ERROR"
        elif actual == expected:
            outcome = "PASS"
        else:
            outcome = "WRONG"

        record = {
            "question": question,
            "expected": expected,
            "actual": actual,
            "outcome": outcome,
            "error": error,
        }
        results.append(record)

        print(
            f"{outcome}: expected={expected}, actual={actual}",
            flush=True,
        )
        if error:
            print(error, flush=True)

    passed = sum(r["outcome"] == "PASS" for r in results)
    wrong = sum(r["outcome"] == "WRONG" for r in results)
    errors = sum(r["outcome"] == "ERROR" for r in results)

    report = {
        "total": len(results),
        "passed": passed,
        "wrong": wrong,
        "errors": errors,
        "accuracy_on_these_cases": passed / len(results),
        "results": results,
    }

    output = Path(__file__).resolve().parent / "supervisor_evaluation.json"
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nCorrect classifications: {passed}/{len(results)}")
    print(f"Wrong classifications: {wrong}")
    print(f"Request or format errors: {errors}")
    print(f"Report saved to: {output}")


if __name__ == "__main__":
    main()
