import json

from data_tools import calculate_correlation


def run_case(name, rows, method="pearson"):
    print(f"\n--- {name} ---")

    try:
        result = calculate_correlation(rows, "x", "y", method)
    except ValueError as error:
        print("REQUEST REJECTED:", error)
        return

    if not result["ok"]:
        print("ANALYSIS BLOCKED:")
        print(json.dumps(result, indent=2))
        return

    print("ANALYSIS SUCCEEDED:")
    print(json.dumps(result, indent=2))


# 1. Valid data: calculation should succeed.
run_case("Valid data", [
    {"x": 1, "y": 10},
    {"x": 2, "y": 20},
    {"x": 3, "y": 30},
])

# 2. Missing data: exclude one pair and report it.
run_case("One missing value", [
    {"x": 1, "y": 10},
    {"x": 2, "y": None},
    {"x": 3, "y": 30},
    {"x": 4, "y": 40},
])

# 3. Invalid data: block the calculation.
run_case("Text inside a numeric column", [
    {"x": 1, "y": 10},
    {"x": 2, "y": "twenty"},
    {"x": 3, "y": 30},
])

# 4. No variation: correlation is undefined.
run_case("Constant column", [
    {"x": 1, "y": 10},
    {"x": 1, "y": 20},
    {"x": 1, "y": 30},
])

# 5. Invalid request: catch the exception.
run_case("Unknown method", [
    {"x": 1, "y": 10},
    {"x": 2, "y": 20},
    {"x": 3, "y": 30},
], method="invented")
