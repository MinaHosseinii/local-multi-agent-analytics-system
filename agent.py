import json

from model_client import chat
from tool_executor import execute_tool


SYSTEM_PROMPT = """
Select one tool for the user's question.

Available dataset: customer orders.

Columns:
- order_id: text
- customer_type: text
- order_value_eur: numeric, with some missing values

Available tools:

inspect_dataset()
Returns row count, columns, and missing-value counts.

calculate_mean(column)
Returns a numeric column's mean, excluding missing values.

Examples:

Question: How many orders are there?
Response:
{"tool": "inspect_dataset", "arguments": {}}

Question: What is the average order value?
Response:
{"tool": "calculate_mean", "arguments": {"column": "order_value_eur"}}

For an unsupported request, return:
{"unsupported": "Brief reason"}

Return exactly one JSON object, without Markdown.
Do not calculate or invent numerical results.
"""


def parse_request(text):
    text = text.strip()

    # Accept a single JSON code block if the model adds Markdown.
    if text.startswith("```"):
        lines = text.splitlines()

        if (
            len(lines) < 3
            or lines[0] not in {"```", "```json"}
            or lines[-1] != "```"
        ):
            raise ValueError("Invalid Markdown wrapper.")

        text = "\n".join(lines[1:-1])

    request = json.loads(text)

    if not isinstance(request, dict):
        raise ValueError("Expected a JSON object.")

    return request


def run_once(question):
    response = chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ])

    print("\nMODEL OUTPUT:")
    print(response)

    request = parse_request(response)

    if "unsupported" in request:
        if (
            set(request) != {"unsupported"}
            or not isinstance(request["unsupported"], str)
        ):
            raise ValueError("Invalid unsupported-response format.")

        return {
            "ok": False,
            "error": {
                "type": "UnsupportedRequest",
                "message": request["unsupported"],
            },
        }

    return execute_tool(request)

#Add the agent loop

def run_agent(question, max_steps=5):
    instructions = """
You are a customer-order analysis assistant.

Available tools:
- inspect_dataset(): returns row count, columns, and missing counts.
- calculate_mean(column): calculates a numeric column's mean.

Available columns:
- order_id: text
- customer_type: text
- order_value_eur: numeric; missing measurements are excluded.

At each step, return exactly one JSON object.

To request a tool:
{"tool": "calculate_mean", "arguments": {"column": "order_value_eur"}}

To finish after observing successful tool results:
{"final": "Answer based only on the tool results."}

For an unavailable operation:
{"unsupported": "Brief reason"}

Request one tool at a time.
Do not invent results or repeat successful calls.
If a tool returns an error, correct the request if possible.
Mention values used and missing values when reporting a mean.
No Markdown.
"""

    messages = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": question},
    ]

    observations = []
    successful_calls = {}

    for step in range(1, max_steps + 1):
        current_messages = [
            {
                "role": "system",
                "content": (
                    instructions
                    + "\nAlready completed tool calls and their results:\n"
                    + json.dumps(successful_calls)
                    + "\nDo not request these identical calls again. "
                    "Use their results, request another needed tool, "
                    "or return a final answer."
                ),
            },
            *messages[1:],
        ]

        response = chat(current_messages)

        print(f"\nSTEP {step} — MODEL:")
        print(response)

        action = parse_request(response)

        if set(action) == {"unsupported"}:
            if not isinstance(action["unsupported"], str):
                raise ValueError("Unsupported reason must be text.")

            return {
                "ok": False,
                "reason": action["unsupported"],
                "observations": observations,
            }

        if set(action) == {"final"}:
            if (
                not isinstance(action["final"], str)
                or not action["final"].strip()
            ):
                raise ValueError("Final answer must be non-empty text.")

            if any(item["ok"] for item in observations):
                return {
                    "ok": True,
                    "answer": action["final"],
                    "observations": observations,
                }

            observation = {
                "ok": False,
                "error": "Call a tool before giving a numerical answer.",
            }

        else:
            # Canonical representation identifies identical requests.
            call_key = json.dumps(action, sort_keys=True)

            if call_key in successful_calls:
                observation = {
                    "ok": False,
                    "error": (
                        "Duplicate call rejected. This operation already "
                        "succeeded. Use its result instead of repeating it."
                    ),
                    "previous_result": successful_calls[call_key],
                }

            else:
                observation = execute_tool(action)
                observations.append(observation)

                if observation["ok"]:
                    successful_calls[call_key] = observation["result"]


        print("APPLICATION FEEDBACK:")
        print(json.dumps(observation, indent=2))

        messages.append({
            "role": "assistant",
            "content": response,
        })

        messages.append({
            "role": "user",
            "content": (
                "Application observation: "
                + json.dumps(observation)
                + "\nChoose your next action."
            ),
        })

    return {
        "ok": False,
        "reason": "Maximum number of decisions reached.",
        "observations": observations,
    }


def run_workflow(question):
    response = chat([
        {
            "role": "system",
            "content": """
Classify the customer's question.

Return exactly one JSON object using these choices:

{"task": "count"}
For the number of orders.

{"task": "mean"}
For the average recorded order value.

{"task": "count_and_mean"}
For both the number of orders and average recorded order value.

{"task": "unsupported"}
For other operations.

Example:
Question: How many orders are there, and what is their average value?
Response: {"task": "count_and_mean"}

Do not request tools or calculate numbers.
Return only the classification JSON.
""",
        },
        {"role": "user", "content": question},
    ])

    print("\nMODEL CLASSIFICATION:")
    print(response)

    decision = parse_request(response)

    if set(decision) != {"task"} or not isinstance(decision["task"], str):
        raise ValueError("Expected a task classification.")

    task = decision["task"]

    plans = {
        "count": ["inspect_dataset"],
        "mean": ["calculate_mean"],
        "count_and_mean": ["inspect_dataset", "calculate_mean"],
    }

    if task == "unsupported":
        return {"ok": False, "reason": "Operation not supported."}

    if task not in plans:
        raise ValueError(f"Unknown task: {task}")

    results = {}

    for tool_name in plans[task]:
        request = {
            "tool": tool_name,
            "arguments": (
                {"column": "order_value_eur"}
                if tool_name == "calculate_mean"
                else {}
            ),
        }

        observation = execute_tool(request)

        print(f"\nTOOL: {tool_name}")
        print(json.dumps(observation, indent=2))

        if not observation["ok"]:
            return {"ok": False, "failed_tool": tool_name,
                    "observation": observation}

        results[tool_name] = observation["result"]

    sentences = []

    if "inspect_dataset" in results:
        count = results["inspect_dataset"]["row_count"]
        sentences.append(f"There are {count} orders.")

    if "calculate_mean" in results:
        calculation = results["calculate_mean"]
        sentences.append(
            f"The average recorded order value is "
            f"€{calculation['mean']:.2f}, based on "
            f"{calculation['values_used']} recorded values, with "
            f"{calculation['missing_excluded']} missing value(s) excluded."
        )

    return {
        "ok": True,
        "task": task,
        "answer": " ".join(sentences),
        "results": results,
    }


if __name__ == "__main__":
    question = input("Your question: ")

    try:
        result = run_workflow(question)
        print("\nAPPLICATION RESULT:")
        print(json.dumps(result, indent=2))

    except ValueError as error:
        print("\nMODEL RESPONSE ERROR:", error)
