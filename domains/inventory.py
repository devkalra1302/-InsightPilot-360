"""
domains/inventory.py
Phase 2 — Inventory domain KPI logic.

Job of this module (and ONLY this module):
- Take an inventory DataFrame and compute the Inventory KPIs from the
  Phase 2 spec (Section 6.2). Every number here must be traceable to a
  plain Pandas calculation — never estimated, never AI. Same discipline
  as domains/sales.py and domains/finance.py.

NOT this module's job:
- Deciding what counts as "bad" data (that's data_quality.py, unchanged).
- Charting anything (that's app.py / Plotly).

SAME PATTERN AS sales.py / finance.py:
- Each KPI function checks it has the columns it needs BEFORE
  calculating. Missing columns -> NOT_AVAILABLE, instead of crashing the
  whole dashboard.

DIFFERENT FROM sales.py / finance.py:
- Two KPIs here (Reorder Flag, Dead Stock) are naturally LISTS of
  flagged products, not single numbers — same shape as top_products in
  sales.py, just answering "which products need attention" instead of
  "which products earn the most."
"""

import pandas as pd

REQUIRED_COLUMNS = {
    "stock_turnover": ["units_sold", "stock_level"],
    "reorder_flag": ["stock_level", "reorder_point", "product", "date"],
    "dead_stock": ["units_sold", "product"],
    "days_of_inventory": ["stock_level", "units_sold", "date"],
}

NOT_AVAILABLE = "Not available — required column(s) not provided"


def has_columns(df: pd.DataFrame, kpi_name: str) -> bool:
    """True only if every column that kpi_name needs actually exists in df."""
    needed = REQUIRED_COLUMNS[kpi_name]
    return all(col in df.columns for col in needed)


def calculate_stock_turnover(df: pd.DataFrame):
    """
    Stock Turnover Ratio = Total Units Sold / Average Stock on Hand.
    "Average Stock on Hand" uses the mean of every stock_level reading in
    the period (not just the latest), since stock naturally rises and
    falls as new units arrive and get sold.
    """
    if not has_columns(df, "stock_turnover"):
        return NOT_AVAILABLE

    total_units_sold = df["units_sold"].sum()
    avg_stock = df["stock_level"].mean()
    if avg_stock == 0 or pd.isna(avg_stock):
        return 0.0
    return round(total_units_sold / avg_stock, 2)


def calculate_reorder_flag(df: pd.DataFrame, date_col: str = "date"):
    """
    Reorder Flag = products whose MOST RECENT stock_level is below their
    own reorder_point. "Most recent" means we look at the latest dated
    row per product, not an average — reorder decisions are about right
    now, not the whole history. Rows with an unparseable date are
    excluded the same way growth/burn-rate calculations exclude them.
    Returns a list of product names, or an empty list if none need
    reordering.
    """
    if not has_columns(df, "reorder_flag"):
        return NOT_AVAILABLE

    dates = pd.to_datetime(df[date_col], errors="coerce")
    valid = df.loc[dates.notna()].copy()
    valid["_date"] = dates[dates.notna()]

    latest_per_product = valid.sort_values("_date").groupby("product").tail(1)
    flagged = latest_per_product[
        latest_per_product["stock_level"] < latest_per_product["reorder_point"]
    ]
    return sorted(flagged["product"].tolist())


def calculate_dead_stock(df: pd.DataFrame):
    """
    Dead Stock = products with units_sold summing to exactly 0 across the
    whole period given. These are candidates to discount or discontinue.
    Returns a list of product names, or an empty list if nothing qualifies.
    """
    if not has_columns(df, "dead_stock"):
        return NOT_AVAILABLE

    totals = df.groupby("product")["units_sold"].sum()
    dead = totals[totals == 0]
    return sorted(dead.index.tolist())


def calculate_days_of_inventory(df: pd.DataFrame, date_col: str = "date"):
    """
    Days of Inventory = Current Stock on Hand / Average Daily Usage.
    "Current Stock on Hand" = the most recent stock_level reading across
    the whole dataset (summed across products, since this is a
    company-wide health number, not per-product).
    "Average Daily Usage" = total units sold / number of distinct days
    with valid data. Rows with an unparseable date are excluded from the
    day count, same pattern as reorder_flag.
    """
    if not has_columns(df, "days_of_inventory"):
        return NOT_AVAILABLE

    dates = pd.to_datetime(df[date_col], errors="coerce")
    valid = df.loc[dates.notna()].copy()
    valid["_date"] = dates[dates.notna()]

    n_days = valid["_date"].nunique()
    if n_days == 0:
        return 0.0

    total_units_sold = valid["units_sold"].sum()
    avg_daily_usage = total_units_sold / n_days
    if avg_daily_usage == 0:
        return 0.0

    # "Current" stock = latest date's total stock across all products.
    latest_date = valid["_date"].max()
    current_stock = valid.loc[valid["_date"] == latest_date, "stock_level"].sum()

    return round(current_stock / avg_daily_usage, 2)


def calculate_kpis(df: pd.DataFrame) -> dict:
    """Runs every Inventory KPI above, returns one dict — the single
    function app.py will call for the Inventory domain. Note some values
    are lists (reorder_flag, dead_stock), not numbers — app.py's display
    logic needs to handle both shapes."""
    return {
        "stock_turnover_ratio": calculate_stock_turnover(df),
        "reorder_flag": calculate_reorder_flag(df),
        "dead_stock": calculate_dead_stock(df),
        "days_of_inventory": calculate_days_of_inventory(df),
    }


def print_kpis(kpis: dict) -> None:
    """Terminal-friendly dump, for testing standalone before app.py wires
    this domain in. Handles numbers, lists, and NOT_AVAILABLE safely."""

    def fmt_list(value, empty_msg):
        if isinstance(value, str):
            return value
        if len(value) == 0:
            return empty_msg
        return ", ".join(value)

    print(f"Stock Turnover Ratio:  {kpis['stock_turnover_ratio']}")
    print(f"Days of Inventory:     {kpis['days_of_inventory']} days")
    print(f"Reorder Flag:          {fmt_list(kpis['reorder_flag'], 'None — all stock above reorder point')}")
    print(f"Dead Stock:            {fmt_list(kpis['dead_stock'], 'None — every product sold at least one unit')}")


if __name__ == "__main__":
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "core"))
    from data_loader import load_data

    df = load_data("sample_data/demo_inventory.csv")
    kpis = calculate_kpis(df)
    print_kpis(kpis)