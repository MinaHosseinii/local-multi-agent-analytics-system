import copy
import json
import uuid
from datetime import datetime, timezone

from cleaning_proposal import propose_cleaning
from messy_orders import MESSY_ROWS

from pathlib import Path
from cleaning_storage import save_decision


def decide_proposal(proposal, decision):
    """Apply an explicit decision to the reviewed proposal."""
    if decision not in {"approve", "reject"}:
        raise ValueError("Decision must be 'approve' or 'reject'.")

    approved = decision == "approve"

    audit = {
        "decision_id": uuid.uuid4().hex,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "rows_before": proposal["rows_before"],
        "proposed_rows_after": proposal["rows_after"],
        "proposed_changes": copy.deepcopy(proposal["changes"]),
        "applied_changes": (
            copy.deepcopy(proposal["changes"]) if approved else []
        ),
    }

    if not approved:
        return {
            "status": "rejected",
            "dataset": None,
            "audit": audit,
        }

    return {
        "status": "approved",
        "dataset": {
            "name": f"orders_cleaned_{audit['decision_id']}",
            "rows": copy.deepcopy(proposal["candidate_rows"]),
            "source_row_numbers": list(proposal["source_row_numbers"]),
            "quality": copy.deepcopy(proposal["candidate_quality"]),
        },
        "audit": audit,
    }


def main():
    original = copy.deepcopy(MESSY_ROWS)
    proposal = propose_cleaning(MESSY_ROWS)

    preview = {
        "rows_before": proposal["rows_before"],
        "rows_after": proposal["rows_after"],
        "changes": proposal["changes"],
    }

    print("REVIEW THESE PROPOSED CHANGES:")
    print(json.dumps(preview, indent=2, allow_nan=False))
    print("\nUnresolved problems will remain flagged.")

    decision = input("\nType approve or reject: ").strip().lower()

    if decision not in {"approve", "reject"}:
        print("Invalid choice. No cleaned dataset was created.")
        return

    result = decide_proposal(proposal, decision)

    output_directory = (
        Path(__file__).resolve().parent / "cleaning_records"
    )
    saved_path = save_decision(result, output_directory)

    print("\nDECISION AUDIT:")
    print(json.dumps(result["audit"], indent=2, allow_nan=False))
    print("\nSTATUS:", result["status"])

    if result["dataset"] is not None:
        dataset = result["dataset"]
        print("COPY NAME:", dataset["name"])
        print("COPY ROWS:", len(dataset["rows"]))
        print("Unresolved issues remain; approval does not permit analysis.")

    print("SOURCE UNCHANGED:", MESSY_ROWS == original)
    print("SAVED DECISION:", saved_path)


if __name__ == "__main__":
    main()
