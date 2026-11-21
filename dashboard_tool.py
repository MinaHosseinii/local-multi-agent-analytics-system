from pathlib import Path
from uuid import uuid4

from langchain_core.tools import tool


@tool
def create_dashboard(
    order_count: int,
    mean_value: float,
    values_used: int,
    missing_excluded: int,
) -> dict:
    """Create a local HTML dashboard from calculated order statistics."""
    if values_used + missing_excluded != order_count:
        raise ValueError("Order and measurement counts are inconsistent.")

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Customer orders</title>
<style>
body {{
    font-family: system-ui, sans-serif;
    max-width: 800px;
    margin: 50px auto;
    padding: 20px;
    background: #f5f7fc;
    color: #172033;
}}
section {{
    background: white;
    padding: 24px;
    border-radius: 12px;
    margin-bottom: 16px;
}}
strong {{ font-size: 28px; }}
</style>
</head>
<body>
<h1>Customer-order dashboard</h1>
<section>Total orders<br><strong>{order_count}</strong></section>
<section>Average recorded order value<br>
<strong>€{mean_value:.2f}</strong></section>
<section>
Recorded values: {values_used}<br>
Missing values excluded: {missing_excluded}
</section>
<p>The average excludes missing order values.</p>
</body>
</html>
"""

    folder = Path(__file__).resolve().parent / "dashboards"
    folder.mkdir(exist_ok=True)

    path = folder / f"orders_{uuid4().hex}.html"
    path.write_text(page, encoding="utf-8")

    return {"artifact": str(path), "order_count": order_count}
