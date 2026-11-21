import json
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from model_client import chat
from agent import parse_request
from langchain_tools import inspect_dataset, calculate_mean
from dashboard_tool import create_dashboard
from langchain_tools import correlate_orders
from correlation_request import extract_and_validate

import copy
from pathlib import Path

from messy_orders import MESSY_ROWS
from cleaning_proposal import propose_cleaning
from cleaning_approval import decide_proposal
from cleaning_storage import save_decision


class State(TypedDict):
    question: str
    task: str
    inspection: dict
    calculation: dict
    answer: str
    dashboard: dict
    report_attempts: int
    review_feedback: str
    review_verdict: str
    status: str
    report_claims: dict
    analysis_error: dict
    request_validation: dict
    cleaning_result: dict


def supervisor(state):
    response = chat([
        {
            "role": "system",
            "content": """Choose the task for the user's question.

Allowed tasks:
count: number of orders
mean: average order value
count_and_mean: number of orders and average order value
dashboard: create a customer-order dashboard
correlation_pearson: Pearson correlation of marketing cost and order value
correlation_spearman: Spearman correlation of marketing cost and order value
correlation_kendall: Kendall correlation of marketing cost and order value
unsupported: anything else, including correlation without a named method

Examples:
Question: How many orders are there?
{"task":"count"}

Question: What is the average order value?
{"task":"mean"}

Question: Calculate Spearman correlation between marketing cost and order value.
{"task":"correlation_spearman"}

Question: Calculate Pearson correlation between marketing cost and order value.
{"task":"correlation_pearson"}

Question: Calculate Kendall correlation between marketing cost and order value.
{"task":"correlation_kendall"}

Return one JSON object with only the task field.
Do not calculate or answer the question.

cleaning: request a preview of removing exact duplicate order lines
and normalizing valid dates in the messy order dataset.

Example:
Preview cleaning the messy order dataset.
{"task":"cleaning"}

Cleaning always requires a preview and explicit human approval.
Other cleaning operations are unsupported.
""",
        },
        {"role": "user", "content": state["question"]},
    ])

    print("\nRAW SUPERVISOR RESPONSE:")
    print(repr(response))

    decision = parse_request(response)

    print("PARSED CLASSIFICATION:")
    print(json.dumps(decision, indent=2))

    if (
        set(decision) != {"task"}
        or not isinstance(decision["task"], str)
        or decision["task"] not in {
            "count", "mean", "count_and_mean", "dashboard", "unsupported", "correlation_pearson","correlation_spearman","correlation_kendall", "cleaning",
        }
    ):
        print(
            "Supervisor returned an invalid classification; "
            "sending the question for request validation."
        )
        return {"task": "unsupported"}

    return {"task": decision["task"]}


def data_management(state):
    result = inspect_dataset.invoke({})
    return {"inspection": result}


def analysis(state):
    import math

    try:
        result = calculate_mean.invoke({
            "column": "order_value_eur"
        })

        # Validate the tool output before downstream nodes use it.
        value = result.get("mean")

        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("The tool returned an invalid mean.")

        return {
            "calculation": result,
            "analysis_error": {},
        }

    except (ValueError, TypeError) as error:
        return {
            "calculation": {},
            "analysis_error": {
                "type": type(error).__name__,
                "message": str(error),
            },
        }


def route_after_supervisor(state):
    if state["task"] == "cleaning":
        return "cleaning"
    
    if (
        state["task"] in CORRELATION_METHODS
        or state["task"] == "unsupported"
    ):
        return "validate_request"

    if state["task"] in {"count", "count_and_mean", "dashboard"}:
        return "data_management"

    if state["task"] == "mean":
        return "analysis"

    return "reporting"


def route_after_inspection(state):
    if state["task"] in {"count_and_mean", "dashboard"}:
        return "analysis"

    return "reporting"


def route_after_analysis(state):
    if state["analysis_error"]:
        return "analysis_blocked"

    if state["task"] == "dashboard":
        return "dashboard"

    return "reporting"


def dashboard_node(state):
    calculation = state["calculation"]

    result = create_dashboard.invoke({
        "order_count": state["inspection"]["row_count"],
        "mean_value": calculation["mean"],
        "values_used": calculation["values_used"],
        "missing_excluded": calculation["missing_excluded"],
    })

    return {"dashboard": result}


def route_after_reporting(state):
    if state["task"] == "unsupported":
        return "stop"

    return "reviewer"


def route_after_review(state):
    if state["review_verdict"] == "approve":
        return "stop"

    if state["report_attempts"] < 2:
        return "reporting"

    return "failed"


def failed_review(state):
    return {
        "status": "failed_review",
        "review_feedback": (
            "Stopped after two rejected drafts. Last feedback: "
            + state["review_feedback"]
        ),
    }


def expected_claims(state):
    """Build the required facts from actual tool results."""
    claims = {}

    if state["inspection"]:
        claims["order_count"] = state["inspection"]["row_count"]

    if state["calculation"]:
        calculation = state["calculation"]
        claims.update({
            "mean_eur": calculation["mean"],
            "values_used": calculation["values_used"],
            "missing_excluded": calculation["missing_excluded"],
        })

    return claims


def reporting(state):
    if state["task"] == "unsupported":
        return {
            "answer": "This request is not currently supported.",
            "status": "unsupported",
        }

    response = chat([
        {
            "role": "system",
            "content": (
                "You are the reporting agent. "
                "Return the supplied facts as one JSON object, "
                "using exactly the same field names and numbers. "
                "Apply reviewer feedback. Do not add explanations."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "facts": expected_claims(state),
                "feedback": state["review_feedback"],
            }),
        },
    ])

    try:
        claims = parse_request(response)
    except ValueError as error:
        claims = {"format_error": str(error)}

    return {
        "report_claims": claims,
        "answer": "",  # Do not present an unverified draft as final.
        "report_attempts": state["report_attempts"] + 1,
        "status": "draft",
    }


def numerical_errors(claims, expected):
    import math

    if set(claims) != set(expected):
        return [
            f"Required fields are {sorted(expected)}; "
            f"received {sorted(claims)}."
        ]

    errors = []

    for field, expected_value in expected.items():
        actual = claims[field]

        if field == "mean_eur":
            valid = (
                not isinstance(actual, bool)
                and isinstance(actual, (int, float))
                and math.isfinite(actual)
                and math.isclose(
                    actual,
                    expected_value,
                    rel_tol=1e-9,
                    abs_tol=1e-9,
                )
            )
        else:
            valid = (
                type(actual) is int
                and actual == expected_value
            )

        if not valid:
            errors.append(
                f"{field}: expected {expected_value!r}, "
                f"received {actual!r}."
            )

    return errors


def render_verified_answer(state):
    claims = state["report_claims"]
    sentences = []

    if "order_count" in claims:
        sentences.append(
            f"There are {claims['order_count']} orders."
        )

    if "mean_eur" in claims:
        sentences.append(
            f"The average recorded order value is "
            f"€{claims['mean_eur']:.2f}, using "
            f"{claims['values_used']} recorded values and excluding "
            f"{claims['missing_excluded']} missing value(s)."
        )

    if state["dashboard"]:
        sentences.append(
            f"Dashboard: {state['dashboard']['artifact']}"
        )

    return " ".join(sentences)


def reviewer(state):
    expected = expected_claims(state)
    errors = numerical_errors(state["report_claims"], expected)

    # Numerical failures cannot be overridden by the model.
    if errors:
        return {
            "review_verdict": "revise",
            "review_feedback": " ".join(errors),
            "status": "needs_revision",
        }

    # A focused model review follows the Python checks.
    response = chat([
        {
            "role": "system",
            "content": (
                "Compare reported facts with expected facts. "
                'Return exactly {"verdict":"approve"} if they match, '
                'otherwise {"verdict":"revise"}. '
                "Return JSON only."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "expected": expected,
                "reported": state["report_claims"],
            }),
        },
    ])

    try:
        decision = parse_request(response)

        if (
            set(decision) != {"verdict"}
            or not isinstance(decision["verdict"], str)
            or decision["verdict"] not in {"approve", "revise"}
        ):
            raise ValueError("Invalid reviewer decision.")

    except ValueError as error:
        return {
            "review_verdict": "revise",
            "review_feedback": f"Reviewer response invalid: {error}",
            "status": "needs_revision",
        }

    approved = decision["verdict"] == "approve"

    return {
        "review_verdict": decision["verdict"],
        "review_feedback": (
            "Python checks passed and the model approved."
            if approved
            else "Model requested revision. Use the supplied facts exactly."
        ),
        "answer": render_verified_answer(state) if approved else "",
        "status": "completed" if approved else "needs_revision",
    }
    

def analysis_blocked(state):
    error = state["analysis_error"]

    message = (
        error.get("message")
        or error.get("reason")
        or error.get("error")
        or "The analysis failed validation"
    )

    return {
        "status": "blocked",
        "answer": (
            "Analysis could not be completed: "
            + message.rstrip(".")
            + "."
        ),
    }


CORRELATION_METHODS = {
    "correlation_pearson": "pearson",
    "correlation_spearman": "spearman",
    "correlation_kendall": "kendall",
}


def correlation_node(state):
    try:
        validation = state["request_validation"]

        if validation.get("status") != "ready":
            raise ValueError("The correlation request is not validated.")

        result = correlate_orders.invoke({
            "method": validation["method"]
        })
        
    except (ValueError, TypeError) as error:
        result = {
            "ok": False,
            "reason": str(error),
        }

    if result.get("ok") is not True:
        return {
            "calculation": {},
            "analysis_error": result,
        }

    return {
        "calculation": result,
        "analysis_error": {},
    }


def route_after_correlation(state):
    if state["analysis_error"]:
        return "analysis_blocked"

    return "correlation_report"


def correlation_report(state):
    result = state["calculation"]

    return {
        "status": "completed",
        "answer": (
            f"{result['method'].capitalize()} correlation between "
            "marketing cost and recorded order value is "
            f"{result['coefficient']:.4f}, using "
            f"{result['pairs_used']} complete pairs. "
            f"Excluded rows: {len(result['excluded_rows'])}. "
            "This describes association, not causation."
        ),
    }


def validate_request_node(state):
    result = extract_and_validate(state["question"])

    return {
        "request_validation": result["validation"],
    }


def route_after_request_validation(state):
    if state["request_validation"]["status"] == "ready":
        return "correlation"

    return "request_stopped"


def request_stopped_node(state):
    validation = state["request_validation"]

    return {
        "status": validation["status"],
        "answer": validation["message"],
        "calculation": {},
    }

CLEANING_DIRECTORY = (
    Path(__file__).resolve().parent / "cleaning_records"
)


def cleaning_node(state):
    # Work on a separate snapshot of the messy dataset.
    source = copy.deepcopy(MESSY_ROWS)
    proposal = propose_cleaning(source)

    print("\nCLEANING PREVIEW:")
    print(json.dumps({
        "rows_before": proposal["rows_before"],
        "rows_after": proposal["rows_after"],
        "changes": proposal["changes"],
    }, indent=2, allow_nan=False))

    print("Unresolved issues will remain flagged.")
    decision = input("Type approve or reject: ").strip().lower()

    if decision not in {"approve", "reject"}:
        return {
            "status": "cancelled",
            "answer": "Invalid choice. No decision or dataset was saved.",
            "cleaning_result": {},
        }

    result = decide_proposal(proposal, decision)
    saved_path = save_decision(result, CLEANING_DIRECTORY)

    if result["dataset"] is None:
        return {
            "status": "rejected",
            "answer": (
                "Cleaning rejected. No cleaned dataset was created. "
                f"Decision saved: {saved_path}"
            ),
            "cleaning_result": {
                "saved_path": str(saved_path),
                "dataset_name": None,
            },
        }

    dataset = result["dataset"]
    quality = dataset["quality"]

    # Conservative policy for this cleaning workflow:
    # require valid keys/dates/numbers and no remaining missing values.
    blockers = []

    if quality["keys"]["invalid_keys"]:
        blockers.append("invalid keys")

    if quality["keys"]["repeated_keys"]:
        blockers.append("duplicate or conflicting keys")

    if quality["dates"]["invalid_count"] or quality["dates"]["missing_count"]:
        blockers.append("invalid or missing dates")

    for column, report in quality["numeric_columns"].items():
        if report["invalid_count"] or report["missing_count"]:
            blockers.append(f"invalid or missing values in {column}")

    status = "approved_requires_review" if blockers else "approved"

    return {
        "status": status,
        "answer": (
            f"Saved separate dataset {dataset['name']} "
            f"with {len(dataset['rows'])} rows. "
            + (
                "Analysis remains blocked: " + "; ".join(blockers) + ". "
                if blockers
                else "The implemented quality checks passed. "
            )
            + f"Decision saved: {saved_path}. "
            + "No analysis was executed."
        ),
        "cleaning_result": {
            "saved_path": str(saved_path),
            "dataset_name": dataset["name"],
            "blockers": blockers,
        },
    }


builder = StateGraph(State)

builder.add_node("supervisor", supervisor)
builder.add_node("data_management", data_management)
builder.add_node("analysis", analysis)
builder.add_node("reporting", reporting)
builder.add_node("dashboard", dashboard_node)
builder.add_node("reviewer", reviewer)
builder.add_node("failed_review", failed_review)
builder.add_node("analysis_blocked", analysis_blocked)
builder.add_node("correlation", correlation_node)
builder.add_node("correlation_report", correlation_report)
builder.add_node("validate_request", validate_request_node)
builder.add_node("request_stopped", request_stopped_node)
builder.add_node("cleaning", cleaning_node)

builder.add_conditional_edges(
    "supervisor",
    route_after_supervisor,
    {
        "data_management": "data_management",
        "analysis": "analysis",
        "reporting": "reporting",
        "validate_request": "validate_request",
        "cleaning": "cleaning",
    },
)

builder.add_conditional_edges(
    "data_management",
    route_after_inspection,
    {
        "analysis": "analysis",
        "reporting": "reporting",
    },
)

builder.add_conditional_edges(
    "analysis",
    route_after_analysis,
    {
        "dashboard": "dashboard",
        "reporting": "reporting",
        "analysis_blocked": "analysis_blocked",
    },
)

builder.add_edge(START, "supervisor")
builder.add_edge("dashboard", "reporting")
builder.add_conditional_edges(
    "reporting",
    route_after_reporting,
    {
        "reviewer": "reviewer",
        "stop": END,
    },
)

builder.add_conditional_edges(
    "reviewer",
    route_after_review,
    {
        "reporting": "reporting",
        "failed": "failed_review",
        "stop": END,
    },
)

builder.add_edge("failed_review", END)

builder.add_edge("analysis_blocked", END)

builder.add_conditional_edges(
    "correlation",
    route_after_correlation,
    {
        "analysis_blocked": "analysis_blocked",
        "correlation_report": "correlation_report",
    },
)

builder.add_edge("correlation_report", END)

builder.add_conditional_edges(
    "validate_request",
    route_after_request_validation,
    {
        "correlation": "correlation",
        "request_stopped": "request_stopped",
    },
)

builder.add_edge("request_stopped", END)

builder.add_edge("cleaning", END)

graph = builder.compile()


if __name__ == "__main__":
    question = input("Your question: ")

    initial_state = {
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
        "cleaning_result": {},
    }

    for update in graph.stream(initial_state, stream_mode="updates"):
        print("\nNODE UPDATE:")
        print(json.dumps(update, indent=2, ensure_ascii=False))
