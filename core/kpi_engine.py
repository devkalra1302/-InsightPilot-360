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
"""

import pandas as pd


def calculate_revenue(df: pd.DataFrame) -> float:
    """Revenue = SUM(revenue). Pandas' .sum() already ignores blank cells,
    so this is safe even before data_quality.py has run."""
    return round(df["revenue"].sum(), 2)


def calculate_profit(df: pd.DataFrame) -> float:
    """Profit = Revenue - Cost, using the totals, matching the spec exactly."""
    revenue = calculate_revenue(df)
    cost = round(df["cost"].sum(), 2)
    return round(revenue - cost, 2)


def calculate_margin(df: pd.DataFrame) -> float:
    """Margin % = Profit / Revenue * 100. Guarded against divide-by-zero."""
    revenue = calculate_revenue(df)
    if revenue == 0:
        return 0.0
    profit = calculate_profit(df)
    return round((profit / revenue) * 100, 2)


def calculate_aov(df: pd.DataFrame) -> float:
    """Average Order Value = Revenue / Number of Orders.
    Counts UNIQUE order_ids, not rows."""
    revenue = calculate_revenue(df)
    n_orders = df["order_id"].nunique()
    if n_orders == 0:
        return 0.0
    return round(revenue / n_orders, 2)


def calculate_growth(df: pd.DataFrame, date_col: str = "order_date") -> float:
    """
    Revenue Growth = (Current Period - Previous Period) / Previous Period * 100
    "Period" = calendar month. Compares the two most recent months with data.
    errors="coerce" turns unparseable dates (like the broken "31/13/2025"
    row) into NaT instead of crashing — those rows are excluded, not guessed.
    """
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


def top_products(df: pd.DataFrame, n: int = 5) -> list:
    """Rank products by SUM(revenue), descending."""
    ranked = df.groupby("product")["revenue"].sum().sort_values(ascending=False)
    return list(ranked.head(n).round(2).items())


def top_regions(df: pd.DataFrame, n: int = 5) -> list:
    """Same idea, grouped by region instead."""
    ranked = df.groupby("region")["revenue"].sum().sort_values(ascending=False)
    return list(ranked.head(n).round(2).items())


def calculate_kpis(df: pd.DataFrame) -> dict:
    """Runs every KPI above, returns one dict — the single function
    app.py will actually call."""
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
    """Terminal-friendly dump, for testing before app.py exists."""
    print(f"Revenue:        ${kpis['revenue']:,.2f}")
    print(f"Profit:         ${kpis['profit']:,.2f}")
    print(f"Margin:         {kpis['margin_pct']}%")
    print(f"AOV:            ${kpis['aov']:,.2f}")
    print(f"Growth (MoM):   {kpis['growth_pct']}%")
    print("\nTop Products:")
    for name, rev in kpis["top_products"]:
        print(f"  - {name}: ${rev:,.2f}")
    print("\nTop Regions:")
    for name, rev in kpis["top_regions"]:
        print(f"  - {name}: ${rev:,.2f}")


if __name__ == "__main__":
    from data_loader import load_data

    df = load_data("sample_data/demo_sales.csv")
    kpis = calculate_kpis(df)
    print_kpis(kpis)