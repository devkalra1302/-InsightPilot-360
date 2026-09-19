"""
domains/finance.py
Phase 2 — Finance domain KPI logic.

Job of this module (and ONLY this module):
- Take a finance DataFrame and compute the Finance KPIs from the Phase 2
  spec (Section 6.1). Every number here must be traceable to a plain
  Pandas calculation — never estimated, never AI. Same discipline as
  domains/sales.py.

NOT this module's job:
- Deciding what counts as "bad" data (that's data_quality.py, unchanged).
- Charting anything (that's app.py / Plotly).
- Anything about Sales, Inventory, Customer, or Operations — those live
  in their own domains/ files.

SAME PATTERN AS sales.py:
- Not every company's finance file will have every column. Each KPI
  function checks it has what it needs BEFORE calculating. If a required
  column is missing, that KPI returns NOT_AVAILABLE instead of crashing
  the whole dashboard. Every other KPI still calculates normally.
"""

import pandas as pd

# Which real columns each KPI needs to run.
# Same idea as sales.py: by the time this file runs, if a key isn't in
# df.columns, the company's file genuinely didn't have that data.
REQUIRED_COLUMNS = {
    "total_revenue": ["income"],
    "total_expenses": ["expense"],
    "net_profit": ["income", "expense"],
    "burn_rate": ["expense", "date"],
    "expense_growth": ["expense", "date"],
}

NOT_AVAILABLE = "Not available — required column(s) not provided"


def has_columns(df: pd.DataFrame, kpi_name: str) -> bool:
    """True only if every column that kpi_name needs actually exists in df."""
    needed = REQUIRED_COLUMNS[kpi_name]
    return all(col in df.columns for col in needed)


def calculate_total_revenue(df: pd.DataFrame):
    """Total Revenue = SUM(income). .sum() already skips blank cells."""
    if not has_columns(df, "total_revenue"):
        return NOT_AVAILABLE
    return round(df["income"].sum(), 2)


def calculate_total_expenses(df: pd.DataFrame):
    """Total Expenses = SUM(expense)."""
    if not has_columns(df, "total_expenses"):
        return NOT_AVAILABLE
    return round(df["expense"].sum(), 2)


def calculate_net_profit(df: pd.DataFrame):
    """Net Profit = Total Revenue - Total Expenses, per the spec formula."""
    if not has_columns(df, "net_profit"):
        return NOT_AVAILABLE
    revenue = df["income"].sum()
    expenses = df["expense"].sum()
    return round(revenue - expenses, 2)


def _monthly_expense_totals(df: pd.DataFrame, date_col: str = "date"):
    """
    Shared helper for burn_rate and expense_growth: parses the date column,
    drops rows where the date couldn't be parsed (errors="coerce" turns a
    bad date like "2025-09-31" into NaT instead of crashing), then groups
    the remaining rows by calendar month and sums expense per month.
    Returns a Series indexed by month, sorted oldest to newest.
    """
    dates = pd.to_datetime(df[date_col], errors="coerce")
    valid = df.loc[dates.notna()].copy()
    valid["_month"] = dates[dates.notna()].dt.to_period("M")
    return valid.groupby("_month")["expense"].sum().sort_index()


def calculate_burn_rate(df: pd.DataFrame):
    """
    Burn Rate = Total Expenses / Number of Months.
    "Number of months" means distinct calendar months that actually have
    data — not a fixed 12, so it works whether you upload 3 months or 3
    years of data.
    """
    if not has_columns(df, "burn_rate"):
        return NOT_AVAILABLE

    monthly = _monthly_expense_totals(df)
    if len(monthly) == 0:
        return 0.0
    return round(monthly.sum() / len(monthly), 2)


def calculate_expense_growth(df: pd.DataFrame):
    """
    Expense Growth = (Current period - Previous period) / Previous period * 100.
    "Period" = calendar month, comparing the two most recent months with
    data — identical pattern to sales.py's calculate_growth, just tracking
    expense instead of revenue (rising expense growth is a warning sign,
    not a good one, so don't read this the same way as revenue growth).
    """
    if not has_columns(df, "expense_growth"):
        return NOT_AVAILABLE

    monthly = _monthly_expense_totals(df)
    if len(monthly) < 2:
        return 0.0

    previous, current = monthly.iloc[-2], monthly.iloc[-1]
    if previous == 0:
        return 0.0
    return round(((current - previous) / previous) * 100, 2)


def calculate_kpis(df: pd.DataFrame) -> dict:
    """Runs every Finance KPI above, returns one dict — the single function
    app.py will call for the Finance domain. Missing-column KPIs come back
    as the NOT_AVAILABLE string instead of crashing this whole function."""
    return {
        "total_revenue": calculate_total_revenue(df),
        "total_expenses": calculate_total_expenses(df),
        "net_profit": calculate_net_profit(df),
        "burn_rate": calculate_burn_rate(df),
        "expense_growth_pct": calculate_expense_growth(df),
    }


def print_kpis(kpis: dict) -> None:
    """Terminal-friendly dump, for testing standalone before app.py wires
    this domain in. Handles both real numbers and NOT_AVAILABLE safely."""

    def fmt_money(value):
        return f"${value:,.2f}" if isinstance(value, (int, float)) else value

    def fmt_pct(value):
        return f"{value}%" if isinstance(value, (int, float)) else value

    print(f"Total Revenue:    {fmt_money(kpis['total_revenue'])}")
    print(f"Total Expenses:   {fmt_money(kpis['total_expenses'])}")
    print(f"Net Profit:       {fmt_money(kpis['net_profit'])}")
    print(f"Burn Rate:        {fmt_money(kpis['burn_rate'])} / month")
    print(f"Expense Growth:   {fmt_pct(kpis['expense_growth_pct'])}")


if __name__ == "__main__":
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "core"))
    from data_loader import load_data

    df = load_data("sample_data/demo_finance.csv")
    kpis = calculate_kpis(df)
    print_kpis(kpis)