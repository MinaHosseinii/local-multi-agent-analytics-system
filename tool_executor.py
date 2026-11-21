import inspect
import json

from data_tools import inspect_dataset, calculate_mean


TOOLS = {
    "inspect_dataset": inspect_dataset,
    "calculate_mean": calculate_mean,
}


def execute_tool(request):
    try:
        if not isinstance(request, dict):
            raise ValueError("Request must be a dictionary.")

        if set(request) != {"tool", "arguments"}:
            raise ValueError("Request must contain tool and arguments.")

        name = request["tool"]
        arguments = request["arguments"]

        if not isinstance(name, str) or name not in TOOLS:
            raise ValueError("Unknown or unpermitted tool.")

        if not isinstance(arguments, dict):
            raise ValueError("Arguments must be a dictionary.")

        if not all(isinstance(value, str) for value in arguments.values()):
            raise ValueError("Argument values must be strings.")

        function = TOOLS[name]

        # Reject missing or unexpected arguments before execution.
        inspect.signature(function).bind(**arguments)

        result = function(**arguments)

        return {"ok": True, "result": result}

    except (ValueError, TypeError) as error:
        return {
            "ok": False,
            "error": {
                "type": type(error).__name__,
                "message": str(error),
            },
        }


if __name__ == "__main__":
    requests = [
        {
            "tool": "calculate_mean",
            "arguments": {"column": "order_value_eur"},
        },
        {
            "tool": "calculate_mean",
            "arguments": {"column": "customer_type"},
        },
    ]

    for request in requests:
        print("\nREQUEST:")
        print(json.dumps(request, indent=2))

        print("RESULT:")
        print(json.dumps(execute_tool(request), indent=2))
