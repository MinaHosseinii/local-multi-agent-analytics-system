import copy
import json

from messy_orders import MESSY_ROWS
from data_tools import (
    validate_order_keys,
    validate_order_dates,
    validate_numeric_column,
)


def build_quality_report(rows):
    return {
        "row_count": len(rows),
        "keys": validate_order_keys(rows),
        "dates": validate_order_dates(rows),
        "numeric_columns": {
            column: validate_numeric_column(rows, column)
            for column in (
                "quantity",
                "line_value_eur",
                "marketing_cost_eur",
            )
        },
    }


if __name__ == "__main__":
    original = copy.deepcopy(MESSY_ROWS)

    report = build_quality_report(MESSY_ROWS)

    print("DATA QUALITY REPORT:")
    print(json.dumps(report, indent=2, allow_nan=False))

    print("\nSOURCE UNCHANGED:", MESSY_ROWS == original)
