import copy
import json

from messy_orders import MESSY_ROWS
from quality_report import build_quality_report
from data_tools import validate_order_keys, validate_order_dates


def propose_cleaning(rows):
    key_report = validate_order_keys(rows)
    date_report = validate_order_dates(rows)

    changes = []
    removed_rows = set()

    # Remove only duplicates whose entire key group is identical.
    for group in key_report["repeated_keys"]:
        if group["classification"] != "exact_duplicate":
            continue

        kept_row = group["rows"][0]

        for source_row in group["rows"][1:]:
            removed_rows.add(source_row)
            changes.append({
                "operation": "remove_exact_duplicate",
                "source_row": source_row,
                "kept_source_row": kept_row,
            })

    # Normalize only dates already validated as unambiguous and real.
    for check in date_report["checks"]:
        source_row = check["row"]

        if source_row in removed_rows or check["status"] != "valid":
            continue

        original_date = rows[source_row - 1]["order_date"]
        normalized_date = check["normalized_date"]

        if original_date != normalized_date:
            changes.append({
                "operation": "normalize_date",
                "source_row": source_row,
                "before": original_date,
                "after": normalized_date,
            })

    # Construct a candidate copy, not an approved dataset.
    candidate_rows = []
    source_row_numbers = []

    normalized_dates = {
        change["source_row"]: change["after"]
        for change in changes
        if change["operation"] == "normalize_date"
    }

    for source_row, row in enumerate(rows, start=1):
        if source_row in removed_rows:
            continue

        candidate = copy.deepcopy(row)

        if source_row in normalized_dates:
            candidate["order_date"] = normalized_dates[source_row]

        candidate_rows.append(candidate)
        source_row_numbers.append(source_row)

    return {
        "status": "proposed",
        "rows_before": len(rows),
        "rows_after": len(candidate_rows),
        "changes": changes,
        "candidate_rows": candidate_rows,
        # Map each candidate row back to its original source row.
        "source_row_numbers": source_row_numbers,
        "candidate_quality": build_quality_report(candidate_rows),
    }


if __name__ == "__main__":
    original = copy.deepcopy(MESSY_ROWS)
    proposal = propose_cleaning(MESSY_ROWS)

    preview = {
        "status": proposal["status"],
        "rows_before": proposal["rows_before"],
        "rows_after": proposal["rows_after"],
        "changes": proposal["changes"],
        "source_row_numbers": proposal["source_row_numbers"],
    }

    print("CLEANING PROPOSAL:")
    print(json.dumps(preview, indent=2, allow_nan=False))

    print("\nSOURCE UNCHANGED:", MESSY_ROWS == original)
    print("Proposal only: no approved dataset has been created.")
