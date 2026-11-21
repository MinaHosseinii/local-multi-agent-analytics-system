from urllib.error import URLError

from supervisor_graph import graph


METHODS = {
    "pearson": "Pearson",
    "spearman": "Spearman",
    "kendall": "Kendall",
}


def make_state(question):
    # Fresh request state prevents old results leaking into a new answer.
    return {
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


def run_question(question):
    state = make_state(question)

    for update in graph.stream(state, stream_mode="updates"):
        for changes in update.values():
            state.update(changes)

    return state


def main():
    pending_question = None

    print("Interactive data assistant")
    print("Commands: /status, /cancel, /exit")
    print("Ask a question. Cleaning approval still uses its own prompt.")

    while True:
        try:
            text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            break

        if not text:
            continue

        if text == "/exit":
            print("Session ended.")
            break

        if text == "/status":
            if pending_question:
                print("Awaiting a correlation method for:")
                print(pending_question)
            else:
                print("Ready for a new question.")
            continue

        if text == "/cancel":
            pending_question = None
            print("Pending question cleared.")
            continue

        if text.startswith("/"):
            print("Unknown command. Use /status, /cancel, or /exit.")
            continue

        original_question = pending_question or text

        if pending_question:
            method = METHODS.get(text.lower().rstrip("."))

            if method is None:
                print(
                    "Reply with Pearson, Spearman, or Kendall. "
                    "Use /cancel to start a different question."
                )
                continue

            # Re-submit the original question with the user's choice.
            # It still passes through the supervisor and validation.
            question = (
                f"{pending_question}\n"
                f"The user has now explicitly selected "
                f"{method} as the correlation method."
            )
        else:
            question = text

        try:
            state = run_question(question)
        except (ValueError, TypeError, URLError, TimeoutError) as error:
            print(f"Request failed: {error}")
            print("You can retry or use /cancel.")
            continue

        print("\nAssistant:", state["answer"] or "No answer was produced.")
        print("Status:", state["status"])

        if state["status"] == "clarify":
            pending_question = original_question
        else:
            pending_question = None


if __name__ == "__main__":
    main()
