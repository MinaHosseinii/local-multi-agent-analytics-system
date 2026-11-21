def make_row(order_id, line_id, date, quantity, value, marketing):
    return {
        "order_id": order_id,
        "line_id": line_id,
        "order_date": date,
        "quantity": quantity,
        "line_value_eur": value,
        "marketing_cost_eur": marketing,
    }


MESSY_ROWS = [
    make_row("O101", 1, "2026-11-01", 2, 100.0, 10.0),
    make_row("O101", 2, "2026-11-01", 1, 50.0, 5.0),

    # Exact duplicate of row 1.
    make_row("O101", 1, "2026-11-01", 2, 100.0, 10.0),

    # Same key, conflicting quantity and value.
    make_row("O102", 1, "2026-11-02", 1, 80.0, 8.0),
    make_row("O102", 1, "2026-11-02", 3, 240.0, 8.0),

    # Valid alternative date format.
    make_row("O103", 1, "03.11.2026", 1, 120.0, 12.0),

    # Impossible date.
    make_row("O104", 1, "2026-02-30", 1, 90.0, 9.0),

    # Ambiguous date format.
    make_row("O105", 1, "04/11/2026", 1, 110.0, 11.0),

    # Invalid order ID.
    make_row(None, 1, "2026-11-05", 1, 60.0, 6.0),

    # Missing measurement.
    make_row("O107", 1, "2026-11-06", 1, None, 7.0),

    # Numeric-looking text: requires explicit conversion.
    make_row("O108", 1, "2026-11-07", 1, "150.00", 15.0),

    # Invalid numeric value.
    make_row("O109", 1, "2026-11-08", 1, float("inf"), 16.0),
]
