"""
domains/customer.py
Phase 2 — Customer domain KPI logic.

Job of this module (and ONLY this module):
- Take a customer/orders DataFrame and compute the Customer KPIs from the
  Phase 2 spec (Section 6.3): Total Customers, Repeat Purchase Rate,
  Churn Rate, Customer Lifetime Value. Every number here must be
  traceable to a plain Pandas calculation — never estimated, never AI.
  Same discipline as domains/sales.py and domains/finance.py.

NOT this module's job:
- Deciding what counts as "bad" data for the quality panel (that's
  data_quality.py, unchanged). This file only protects its OWN math from
  bad rows (blank customer, duplicate order, unreadable date).
- Charting anything (that's app.py / Plotly).
- Anything about Sales, Finance, Inventory, or Operations.

SAME PATTERN AS finance.py:
- Each KPI function checks it has the columns it needs BEFORE calculating.
  If one is missing, that KPI returns NOT_AVAILABLE instead of crashing
  the whole dashboard. Every other KPI still calculates normally.

Expected columns (one row per order):
    customer_id, order_id, order_date, sale_amount
"""

import pandas as pd

# Which real columns each KPI needs to run.
# NOTE: the spec lists "last_order_date" for churn, but real order files
# have one row per order with an order_date, so we derive each customer's
# last order from order_date instead (decision confirmed with the team).
REQUIRED_COLUMNS = {
    "total_customers": ["customer_id"],
    "repeat_purchase_rate": ["customer_id", "order_id"],
    "churn_rate": ["customer_id", "order_date"],
    "customer_lifetime_value": ["sale_amount", "order_id", "customer_id"],
}

NOT_AVAILABLE = "Not available — required column(s) not provided"

# Churn window: "recent" = last 90 days of data, "prior" = the 90 days
# before that. Kept as one named constant so it's a one-line change later.
CHURN_PERIOD_DAYS = 90


def has_columns(df: pd.DataFrame, kpi_name: str) -> bool:
    """True only if every column that kpi_name needs actually exists in df."""
    needed = REQUIRED_COLUMNS[kpi_name]
    return all(col in df.columns for col in needed)


def _clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    """
    Shared helper: protects the KPI math from two kinds of bad rows.
    1. Rows with no customer_id are dropped — an order we can't attribute
       to a customer can't be counted as a customer.
    2. If order_id exists, repeated order_ids are counted once (keep the
       first) so a duplicated row can't inflate order counts.
    Returns a copy — the original DataFrame is never modified.
    """
    data = df.copy()
    data = data[data["customer_id"].notna()]
    # Blank strings like "" or "  " count as missing too.
    data = data[data["customer_id"].astype(str).str.strip() != ""]
    if "order_id" in data.columns:
        data = data.drop_duplicates(subset="order_id", keep="first")
    return data


def calculate_total_customers(df: pd.DataFrame):
    """Total Customers = COUNT(DISTINCT customer_id)."""
    if not has_columns(df, "total_customers"):
        return NOT_AVAILABLE
    data = _clean_orders(df)
    return int(data["customer_id"].nunique())


def calculate_repeat_purchase_rate(df: pd.DataFrame):
    """
    Repeat Purchase Rate = customers with >1 order / total customers * 100.
    We count DISTINCT order_ids per customer, so one order split across
    several rows still counts as one order.
    """
    if not has_columns(df, "repeat_purchase_rate"):
        return NOT_AVAILABLE
    data = _clean_orders(df)
    orders_per_customer = data.groupby("customer_id")["order_id"].nunique()
    if len(orders_per_customer) == 0:
        return 0.0
    repeat_customers = (orders_per_customer > 1).sum()
    return round(float(repeat_customers / len(orders_per_customer) * 100), 2)


def calculate_churn_rate(df: pd.DataFrame, period_days: int = CHURN_PERIOD_DAYS):
    """
    Churn Rate = customers active in the PRIOR period but NOT in the
    CURRENT period / customers active in the prior period * 100.

    The spec doesn't say how long "inactive" is, so we define it plainly:
    - latest date in the data = "today" for this calculation
    - current period = the last `period_days` days up to that date
    - prior period   = the `period_days` days just before that
    A customer who ordered in the prior period but not the current one
    is churned. Rows with an unreadable date are ignored for churn only
    (errors="coerce" turns a bad date into NaT instead of crashing).
    """
    if not has_columns(df, "churn_rate"):
        return NOT_AVAILABLE

    data = _clean_orders(df)
    dates = pd.to_datetime(data["order_date"], errors="coerce")
    data = data.loc[dates.notna()].copy()
    data["_date"] = dates[dates.notna()]
    if data.empty:
        return 0.0

    latest = data["_date"].max()
    current_start = latest - pd.Timedelta(days=period_days)
    prior_start = latest - pd.Timedelta(days=2 * period_days)

    current = data[data["_date"] > current_start]
    prior = data[(data["_date"] > prior_start) & (data["_date"] <= current_start)]

    prior_customers = set(prior["customer_id"])
    if len(prior_customers) == 0:
        # No one to lose = nothing to divide by; avoid divide-by-zero.
        return 0.0
    current_customers = set(current["customer_id"])
    churned = prior_customers - current_customers
    return round(len(churned) / len(prior_customers) * 100, 2)


def calculate_customer_lifetime_value(df: pd.DataFrame):
    """
    CLV = Average Order Value * Average Orders per Customer (spec formula).
    - AOV uses only orders that HAVE an amount. A blank sale_amount is
      "unknown", not zero, so it must not drag the average down.
    - Average orders per customer uses all distinct orders, since an order
      with a blank amount was still a real order.
    Negative amounts (possible refunds) are left in on purpose — they
    reduce CLV, which is the honest answer.
    """
    if not has_columns(df, "customer_lifetime_value"):
        return NOT_AVAILABLE

    data = _clean_orders(df)
    total_customers = data["customer_id"].nunique()
    total_orders = data["order_id"].nunique()
    if total_customers == 0 or total_orders == 0:
        return 0.0

    with_amount = data[data["sale_amount"].notna()]
    orders_with_amount = with_amount["order_id"].nunique()
    if orders_with_amount == 0:
        return 0.0

    aov = with_amount["sale_amount"].sum() / orders_with_amount
    orders_per_customer = total_orders / total_customers
    return round(float(aov * orders_per_customer), 2)


def calculate_kpis(df: pd.DataFrame) -> dict:
    """
    Runs every Customer KPI and returns them in one dict, so app.py can
    show them all with a single call — same idea as finance.py / sales.py.
    Each KPI is independent: one missing column only affects that KPI.
    """
    return {
        "total_customers": calculate_total_customers(df),
        "repeat_purchase_rate": calculate_repeat_purchase_rate(df),
        "churn_rate": calculate_churn_rate(df),
        "customer_lifetime_value": calculate_customer_lifetime_value(df),
    }


# ---------------------------------------------------------------------
# Standalone test: run from the repo root with
#     python domains/customer.py
# Not used by app.py — it only runs when this file is executed directly.
# ---------------------------------------------------------------------
if __name__ == "__main__":
    from pathlib import Path

    csv_path = Path(__file__).resolve().parent.parent / "sample_data" / "demo_customer.csv"
    demo = pd.read_csv(csv_path)
    results = calculate_kpis(demo)

    # Hand-checked answers for demo_customer.csv (Pandas reference calc).
    expected = {
        "total_customers": 16,
        "repeat_purchase_rate": 68.75,
        "churn_rate": 40.0,
        "customer_lifetime_value": 1001.30,
    }

    print("--- Full demo_customer.csv ---")
    all_pass = True
    for name, value in results.items():
        ok = abs(value - expected[name]) < 0.01
        all_pass = all_pass and ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {value} (expected {expected[name]})")

    # Missing-column safety test: remove sale_amount. ONLY CLV may fail.
    print("\n--- Same data WITHOUT sale_amount column ---")
    safe = calculate_kpis(demo.drop(columns=["sale_amount"]))
    for name, value in safe.items():
        print(f"{name}: {value}")
    only_clv_missing = (
        safe["customer_lifetime_value"] == NOT_AVAILABLE
        and safe["total_customers"] == expected["total_customers"]
        and safe["churn_rate"] == expected["churn_rate"]
    )
    print("PASS" if only_clv_missing else "FAIL", "missing-column safety")

    print("\nALL TESTS PASSED" if (all_pass and only_clv_missing) else "\nSOME TESTS FAILED")
