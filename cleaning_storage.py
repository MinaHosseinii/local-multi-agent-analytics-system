import json
import math
from pathlib import Path


# Reserved marker used to store non-finite floats in valid JSON.
MARKER = "__nonfinite_float__"


def encode_values(value):
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            label = "nan"
        else:
            label = "inf" if value > 0 else "-inf"

        return {MARKER: label}

    if isinstance(value, dict):
        if MARKER in value:
            raise ValueError("Input contains a reserved storage marker.")

        return {
            key: encode_values(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [encode_values(item) for item in value]

    return value


def decode_object(value):
    if set(value) == {MARKER}:
        label = value[MARKER]

        if label not in {"nan", "inf", "-inf"}:
            raise ValueError("Invalid stored numeric marker.")

        return float(label)

    return value


def save_decision(result, directory):
    directory = Path(directory)

    decision_id = result["audit"]["decision_id"]

    if (
        not isinstance(decision_id, str)
        or len(decision_id) != 32
        or any(char not in "0123456789abcdef" for char in decision_id)
    ):
        raise ValueError("Invalid decision ID.")

    document = {
        "format_version": 1,
        "result": result,
    }

    # Serialize before creating the file.
    text = json.dumps(
        encode_values(document),
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    )

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"decision_{decision_id}.json"

    # Exclusive creation prevents overwriting a previous decision.
    with path.open("x", encoding="utf-8") as file:
        file.write(text)

    return path


def load_decision(path):
    document = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_hook=decode_object,
    )

    if document.get("format_version") != 1:
        raise ValueError("Unsupported storage format.")

    return document["result"]
