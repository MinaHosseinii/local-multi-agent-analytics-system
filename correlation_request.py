import json

from model_client import chat
from agent import parse_request
from request_validation import validate_correlation_request


EXTRACTION_PROMPT = """
Extract the requested operation, correlation method, and columns.

Return exactly these three fields:
{"operation": "...", "method": null, "columns": []}

Rules:
- Extract what the user requested, not what the tools support.
- For correlation, operation is "correlation".
- For prediction, operation is "predict".
- For other operations, operation is "unsupported".
- method is "pearson", "spearman", or "kendall" only when
  the user explicitly names that method.
- Otherwise method is null. Never choose a default.
- Map "marketing cost" to "marketing_cost_eur".
- Map "order value" to "order_value_eur".
- Preserve other requested column names, such as "age" and "salary".
- Never substitute supported columns for unsupported columns.
- Do not calculate anything.

Examples:

Question: Calculate Spearman correlation between marketing cost and order value.
{"operation":"correlation","method":"spearman","columns":["marketing_cost_eur","order_value_eur"]}

Question: Calculate correlation between marketing cost and order value.
{"operation":"correlation","method":null,"columns":["marketing_cost_eur","order_value_eur"]}

Question: Calculate Pearson correlation between age and salary.
{"operation":"correlation","method":"pearson","columns":["age","salary"]}

Question: Predict next month's sales.
{"operation":"predict","method":null,"columns":[]}

Return JSON only.
"""


def extract_and_validate(question):
    response = chat([
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": question},
    ])

    print("\nRAW MODEL RESPONSE:")
    print(repr(response))

    try:
        request = parse_request(response)
    except ValueError as error:
        return {
            "request": None,
            "validation": {
                "status": "invalid",
                "message": f"Could not parse model response: {error}",
            },
        }

    return {
        "request": request,
        "validation": validate_correlation_request(request),
    }


if __name__ == "__main__":
    question = input("Your question: ")
    result = extract_and_validate(question)

    print("\nEXTRACTED REQUEST AND VALIDATION:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
