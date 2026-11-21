import json
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from data_tools import calculate_correlation


class AnalysisState(TypedDict):
    rows: list[dict]
    x_column: str
    y_column: str
    method: str
    result: dict
    answer: str
    status: str


def analysis_node(state):
    try:
        result = calculate_correlation(
            state["rows"],
            state["x_column"],
            state["y_column"],
            state["method"],
        )
    except ValueError as error:
        result = {
            "ok": False,
            "reason": "invalid_request",
            "detail": str(error),
        }

    return {"result": result}


def route_after_analysis(state):
    # Continue only on explicit success.
    if state["result"].get("ok") is True:
        return "report"

    return "blocked"


def report_node(state):
    result = state["result"]

    return {
        "status": "completed",
        "answer": (
            f"{result['method'].capitalize()} correlation between "
            f"{result['x_column']} and {result['y_column']}: "
            f"{result['coefficient']:.4f}, using "
            f"{result['pairs_used']} complete pairs. "
            f"Excluded rows: {len(result['excluded_rows'])}."
        ),
    }


def blocked_node(state):
    result = state["result"]
    reason = result.get("reason") or result.get("error")

    return {
        "status": "blocked",
        "answer": f"Analysis could not be completed: {reason}.",
    }


builder = StateGraph(AnalysisState)

builder.add_node("analysis", analysis_node)
builder.add_node("report", report_node)
builder.add_node("blocked", blocked_node)

builder.add_edge(START, "analysis")

builder.add_conditional_edges(
    "analysis",
    route_after_analysis,
    {
        "report": "report",
        "blocked": "blocked",
    },
)

builder.add_edge("report", END)
builder.add_edge("blocked", END)

graph = builder.compile()


def initial_state(rows, method="pearson"):
    return {
        "rows": rows,
        "x_column": "x",
        "y_column": "y",
        "method": method,
        "result": {},
        "answer": "",
        "status": "running",
    }


if __name__ == "__main__":
    cases = {
        "valid": [
            {"x": 1, "y": 10},
            {"x": 2, "y": 20},
            {"x": 3, "y": 30},
        ],
        "invalid": [
            {"x": 1, "y": 10},
            {"x": 2, "y": "twenty"},
            {"x": 3, "y": 30},
        ],
    }

    for name, rows in cases.items():
        print(f"\n--- {name.upper()} ---")

        for update in graph.stream(
            initial_state(rows),
            stream_mode="updates",
        ):
            print(json.dumps(update, indent=2))
