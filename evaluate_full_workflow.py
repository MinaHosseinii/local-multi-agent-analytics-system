import json
from pathlib import Path
from urllib.error import URLError

from supervisor_graph import graph


CASES = [
    {
        "question": (
            "Calculate Spearman correlation between "
            "marketing cost and order value."
        ),
        "expected_status": "completed",
        "should_calculate": True,
        "expected_method": "spearman",
    },
    {
        "question": (
            "Calculate correlation between marketing cost and order value."
        ),
        "expected_status": "clarify",
        "should_calculate": False,
        "expected_method": None,
    },
    {
        "question": (
            "Calculate Pearson correlation between age and salary."
        ),
        "expected_status": "unsupported",
        "should_calculate": False,
        "expected_method": None,
    },
    {
        "question": "Predict next month's sales.",
        "expected_status": "unsupported",
        "should_calculate": False,
        "expected_method": None,
    },
]


def make_state(question):
    return {
        "question": question,
        "task": "",
        "inspection": {},
        "calculation": {},
        "answer": "",
        "dashboard": {},
        "report_attempts": 0,
        "review_feedback": "",
        "review_verdict": "",
        "status": "running",
        "report_claims": {},
        "analysis_error": {},
        "request_validation": {},
    }


def main():
    records = []

    for number, case in enumerate(CASES, start=1):
        print(
            f"\nCASE {number}/{len(CASES)}: {case['question']}",
            flush=True,
        )

        state = make_state(case["question"])
        visited = []
        failures = []

        try:
            for update in graph.stream(
                state,
                stream_mode="updates",
            ):
                for node, changes in update.items():
                    visited.append(node)
                    state.update(changes)

            if state["status"] != case["expected_status"]:
                failures.append(
                    f"Expected status {case['expected_status']!r}; "
                    f"received {state['status']!r}."
                )

            if case["should_calculate"]:
                if "correlation" not in visited:
                    failures.append("Correlation node did not run.")

                if "correlation_report" not in visited:
                    failures.append("Correlation report did not run.")

                calculation = state["calculation"]

                if calculation.get("ok") is not True:
                    failures.append("No successful calculation.")

                if calculation.get("method") != case["expected_method"]:
                    failures.append("Wrong correlation method.")

                if (
                    calculation.get("x_column") != "marketing_cost_eur"
                    or calculation.get("y_column") != "order_value_eur"
                ):
                    failures.append("Wrong calculation columns.")

            else:
                forbidden = {
                    "analysis",
                    "correlation",
                    "dashboard",
                    "correlation_report",
                }

                unexpected = sorted(forbidden.intersection(visited))

                if unexpected:
                    failures.append(
                        f"Unexpected nodes executed: {unexpected}."
                    )

                if state["calculation"]:
                    failures.append(
                        "A calculation was recorded for a rejected request."
                    )

            outcome = "FAIL" if failures else "PASS"

        except (ValueError, TypeError, URLError, TimeoutError) as error:
            outcome = "ERROR"
            failures.append(f"{type(error).__name__}: {error}")

        record = {
            "question": case["question"],
            "outcome": outcome,
            "visited_nodes": visited,
            "status": state["status"],
            "answer": state["answer"],
            "calculation": state["calculation"],
            "failures": failures,
        }
        records.append(record)

        print("Visited nodes:", visited, flush=True)
        print("Final status:", state["status"], flush=True)
        print("Answer:", state["answer"], flush=True)
        print(outcome, flush=True)

        for failure in failures:
            print(" -", failure, flush=True)

    output = (
        Path(__file__).resolve().parent
        / "full_workflow_evaluation.json"
    )
    output.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    passed = sum(record["outcome"] == "PASS" for record in records)
    print(f"\nPassed: {passed}/{len(CASES)}")
    print(f"Report: {output}")


if __name__ == "__main__":
    main()
