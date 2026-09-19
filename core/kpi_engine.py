"""
core/kpi_engine.py
Step 4 of the pipeline: KPI Engine.

Job of this module (and ONLY this module):
- Take a sales DataFrame and compute the core business numbers, using the
  exact formulas from the spec (Section 7). Every number here must be
  traceable to a plain Pandas calculation — never estimated, never AI.

NOT this module's job:
- Deciding what counts as "bad" data (that's data_quality.py).
- Charting anything (that's app.py / Plotly, later).

NEW IN THIS VERSION:
- Not every company's file will have every column (e.g. some have no
  "cost" column at all). Each KPI function now checks it has what it
  needs BEFORE calculating. If a required column is missing, that KPI
  returns "Not available" instead of crashing the whole dashboard.
  Every other KPI still calculates normally.
"""

import pandas as pd

# Which real columns each KPI needs to run.
# app.py's column-mapping step decides which of the user's own column
# names get renamed to these — by the time this file runs, if a key
# isn't in df.columns, it means the company's file didn't have it.
REQUIRED_COLUMNS = {
    "revenue": ["revenue"],
    "profit": ["revenue", "cost"],
    "margin": ["revenue", "cost"],
    "aov": ["revenue", "order_id"],
    "growth": ["revenue", "order_date"],
    "top_products": ["revenue", "product"],
    "top_regions": ["revenue", "region"],
}

NOT_AVAILABLE = "Not available — required column(s) not provided"


def has_columns(df: pd.DataFrame, kpi_name: str) -> bool:
    """True only if every column that kpi_name needs actually exists in df."""
    needed = REQUIRED_COLUMNS[kpi_name]
    return all(col in df.columns for col in needed)


def calculate_revenue(df: pd.DataFrame):
    """Revenue = SUM(revenue). Pandas' .sum() already ignores blank cells,
    so this is safe even before data_quality.py has run."""
    if not has_columns(df, "revenue"):
        return NOT_AVAILABLE
    return round(df["revenue"].sum(), 2)


def calculate_profit(df: pd.DataFrame):
    """Profit = Revenue - Cost, using the totals, matching the spec exactly."""
    if not has_columns(df, "profit"):
        return NOT_AVAILABLE
    revenue = df["revenue"].sum()
    cost = df["cost"].sum()
    return round(revenue - cost, 2)


def calculate_margin(df: pd.DataFrame):
    """Margin % = Profit / Revenue * 100. Guarded against divide-by-zero
    AND against a missing cost column (profit depends on it too)."""
    if not has_columns(df, "margin"):
        return NOT_AVAILABLE
    revenue = df["revenue"].sum()
    if revenue == 0:
        return 0.0
    profit = revenue - df["cost"].sum()
    return round((profit / revenue) * 100, 2)


def calculate_aov(df: pd.DataFrame):
    """Average Order Value = Revenue / Number of Orders.
    Counts UNIQUE order_ids, not rows."""
    if not has_columns(df, "aov"):
        return NOT_AVAILABLE
    revenue = df["revenue"].sum()
    n_orders = df["order_id"].nunique()
    if n_orders == 0:
        return 0.0
    return round(revenue / n_orders, 2)


def calculate_growth(df: pd.DataFrame, date_col: str = "order_date"):
    """
    Revenue Growth = (Current Period - Previous Period) / Previous Period * 100
    "Period" = calendar month. Compares the two most recent months with data.
    errors="coerce" turns unparseable dates (like the broken "31/13/2025"
    row) into NaT instead of crashing — those rows are excluded, not guessed.
    """
    if not has_columns(df, "growth"):
        return NOT_AVAILABLE

    dates = pd.to_datetime(df[date_col], errors="coerce")
    valid = df.loc[dates.notna()].copy()
    valid["_month"] = dates[dates.notna()].dt.to_period("M")

    monthly_revenue = valid.groupby("_month")["revenue"].sum().sort_index()

    if len(monthly_revenue) < 2:
        return 0.0

    previous, current = monthly_revenue.iloc[-2], monthly_revenue.iloc[-1]
    if previous == 0:
        return 0.0
    return round(((current - previous) / previous) * 100, 2)


def top_products(df: pd.DataFrame, n: int = 5):
    """Rank products by SUM(revenue), descending."""
    if not has_columns(df, "top_products"):
        return NOT_AVAILABLE
    ranked = df.groupby("product")["revenue"].sum().sort_values(ascending=False)
    return list(ranked.head(n).round(2).items())


def top_regions(df: pd.DataFrame, n: int = 5):
    """Same idea, grouped by region instead."""
    if not has_columns(df, "top_regions"):
        return NOT_AVAILABLE
    ranked = df.groupby("region")["revenue"].sum().sort_values(ascending=False)
    return list(ranked.head(n).round(2).items())


def calculate_kpis(df: pd.DataFrame) -> dict:
    """Runs every KPI above, returns one dict — the single function
    app.py will actually call. Missing-column KPIs come back as the
    NOT_AVAILABLE string instead of crashing this whole function."""
    return {
        "revenue": calculate_revenue(df),
        "profit": calculate_profit(df),
        "margin_pct": calculate_margin(df),
        "aov": calculate_aov(df),
        "growth_pct": calculate_growth(df),
        "top_products": top_products(df),
        "top_regions": top_regions(df),
    }


def print_kpis(kpis: dict) -> None:
    """Terminal-friendly dump, for testing before app.py exists.
    Handles both real numbers and the NOT_AVAILABLE message safely."""

    def fmt_money(value):
        return f"${value:,.2f}" if isinstance(value, (int, float)) else value

    def fmt_pct(value):
        return f"{value}%" if isinstance(value, (int, float)) else value

    print(f"Revenue:        {fmt_money(kpis['revenue'])}")
    print(f"Profit:         {fmt_money(kpis['profit'])}")
    print(f"Margin:         {fmt_pct(kpis['margin_pct'])}")
    print(f"AOV:            {fmt_money(kpis['aov'])}")
    print(f"Growth (MoM):   {fmt_pct(kpis['growth_pct'])}")

    print("\nTop Products:")
    if isinstance(kpis["top_products"], str):
        print(f"  {kpis['top_products']}")
    else:
        for name, rev in kpis["top_products"]:
            print(f"  - {name}: ${rev:,.2f}")

    print("\nTop Regions:")
    if isinstance(kpis["top_regions"], str):
        print(f"  {kpis['top_regions']}")
    else:
        for name, rev in kpis["top_regions"]:
            print(f"  - {name}: ${rev:,.2f}")


if __name__ == "__main__":
    from data_loader import load_data

    df = load_data("sample_data/demo_sales.csv")
    kpis = calculate_kpis(df)
    print_kpis(kpis)