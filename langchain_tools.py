import json

from langchain_core.tools import tool
from data_tools import ROWS
from data_tools import calculate_correlation as calculate_correlation_function

from data_tools import (
    inspect_dataset as inspect_python,
    calculate_mean as mean_python,
)


@tool
def inspect_dataset() -> dict:
    """Report customer-order row count, columns, and missing values."""
    return inspect_python()


@tool
def calculate_mean(column: str) -> dict:
    """Calculate a numeric column's mean, excluding missing values."""
    return mean_python(column)


@tool
def correlate_orders(method: str) -> dict:
    """Calculate correlation between marketing cost and order value.

    Supported methods: pearson, spearman, kendall.
    Missing pairs are excluded and reported; invalid data blocks analysis.
    """
    return calculate_correlation_function(
        ROWS,
        "marketing_cost_eur",
        "order_value_eur",
        method,
    )

if __name__ == "__main__":
    print("TOOL NAME:")
    print(calculate_mean.name)

    print("\nTOOL DESCRIPTION:")
    print(calculate_mean.description)

    print("\nINPUT SCHEMA:")
    print(json.dumps(
        calculate_mean.get_input_schema().model_json_schema(),
        indent=2,
    ))

    print("\nVALID EXECUTION:")
    print(json.dumps(
        calculate_mean.invoke({"column": "order_value_eur"}),
        indent=2,
    ))

    print("\nINVALID EXECUTION:")
    try:
        calculate_mean.invoke({})
    except ValueError as error:
        print(type(error).__name__)
        print(error)
