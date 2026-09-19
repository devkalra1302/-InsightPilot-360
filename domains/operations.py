"""
domains/operations.py
Phase 2 — Operations domain KPI logic (GENERAL TEMPLATE).

Job of this module (and ONLY this module):
- Take an orders/operations DataFrame and compute the Operations KPIs from
  the Phase 2 spec (Section 6.4): Average Fulfillment Time, On-Time
  Delivery Rate, Cycle Time, Backlog Count. Every number here must be
  traceable to a plain Pandas calculation — never estimated, never AI.
  Same discipline as sales.py, finance.py and customer.py.

NOT this module's job:
- Deciding what counts as "bad" data for the quality panel (that's
  data_quality.py, unchanged). This file only protects its OWN math from
  bad rows (duplicate orders, unreadable dates, impossible date order).
- Charting anything (that's app.py / Plotly).
- Anything about Sales, Finance, Inventory, or Customer.

TEMPLATE WARNING (from the Phase 2 spec):
- "Operations" means different things in different industries. This is a
  starting set for a real client, not a fixed standard. Expect to change
  column names and definitions per company.

SAME PATTERN AS finance.py / customer.py:
- Each KPI function checks it has the columns it needs BEFORE calculating.
  If one is missing, that KPI returns NOT_AVAILABLE instead of crashing
  the whole dashboard. Every other KPI still calculates normally.

Expected columns (one row per order):
    order_id, order_date, due_date, delivery_date,
    start_date, completion_date, status

IMPORTANT — blank dates are not always "bad data":
- A pending or cancelled order has NO delivery_date / completion_date yet.
  That is normal. So each KPI only looks at rows that have the dates IT
  needs, and quietly skips the rest.
"""

import pandas as pd

# Which real columns each KPI needs to run.
REQUIRED_COLUMNS = {
    "avg_fulfillment_time": ["order_date", "delivery_date"],
    "on_time_delivery_rate": ["delivery_date", "due_date"],
    "cycle_time": ["start_date", "completion_date"],
    "backlog_count": ["status"],
}

NOT_AVAILABLE = "Not available — required column(s) not provided"

# The status text that means "not shipped yet". Compared AFTER cleaning
# the text (see _clean_status), so "Pending" and " PENDING " both match.
PENDING_STATUS = "pending"


def has_columns(df: pd.DataFrame, kpi_name: str) -> bool:
    """True only if every column that kpi_name needs actually exists in df."""
    needed = REQUIRED_COLUMNS[kpi_name]
    return all(col in df.columns for col in needed)


def _dedupe_orders(df: pd.DataFrame) -> pd.DataFrame:
    """
    Shared helper: if order_id exists, count each order once (keep the
    first) so a duplicated row can't inflate the KPIs. Returns a copy —
    the original DataFrame is never modified.
    """
    data = df.copy()
    if "order_id" in data.columns:
        data = data.drop_duplicates(subset="order_id", keep="first")
    return data


def _days_between(df: pd.DataFrame, start_col: str, end_col: str) -> pd.Series:
    """
    Shared helper: whole days from start_col to end_col for each row.
    - errors="coerce" turns an unreadable date (e.g. "2026-02-30") into
      NaT instead of crashing.
    - Rows where either date is blank/unreadable are dropped: nothing to
      measure (e.g. a pending order with no delivery_date yet).
    - Negative gaps (ended BEFORE it started) are impossible, so they are
      treated as data errors and dropped rather than pulling averages down.
    """
    start = pd.to_datetime(df[start_col], errors="coerce")
    end = pd.to_datetime(df[end_col], errors="coerce")
    days = (end - start).dt.days
    return days[days.notna() & (days >= 0)]


def calculate_avg_fulfillment_time(df: pd.DataFrame):
    """
    Average Fulfillment Time = AVG(delivery_date - order_date), in days.
    Only orders that actually have both dates are measured.
    """
    if not has_columns(df, "avg_fulfillment_time"):
        return NOT_AVAILABLE
    data = _dedupe_orders(df)
    days = _days_between(data, "order_date", "delivery_date")
    if len(days) == 0:
        return 0.0
    return round(float(days.mean()), 2)


def calculate_on_time_delivery_rate(df: pd.DataFrame):
    """
    On-Time Delivery Rate = orders delivered by due date / orders that
    were delivered * 100.

    NOTE (differs slightly from the spec's wording "/ Total Orders"):
    pending and cancelled orders have no delivery yet, so they can be
    neither on time nor late. Dividing by ALL orders would make the rate
    look worse every time there is a backlog. We divide only by orders
    that have a valid delivery_date AND due_date. Easy to change later.
    """
    if not has_columns(df, "on_time_delivery_rate"):
        return NOT_AVAILABLE
    data = _dedupe_orders(df)
    delivered = pd.to_datetime(data["delivery_date"], errors="coerce")
    due = pd.to_datetime(data["due_date"], errors="coerce")
    measurable = delivered.notna() & due.notna()
    if measurable.sum() == 0:
        return 0.0
    on_time = (delivered[measurable] <= due[measurable]).sum()
    return round(float(on_time / measurable.sum() * 100), 2)


def calculate_cycle_time(df: pd.DataFrame):
    """
    Cycle Time = AVG(completion_date - start_date), in days.
    Same rules as fulfillment time: only rows with both dates, and
    "completed before it started" rows are dropped as data errors.
    """
    if not has_columns(df, "cycle_time"):
        return NOT_AVAILABLE
    data = _dedupe_orders(df)
    days = _days_between(data, "start_date", "completion_date")
    if len(days) == 0:
        return 0.0
    return round(float(days.mean()), 2)


def calculate_backlog_count(df: pd.DataFrame):
    """
    Backlog Count = COUNT(orders where status = "pending").
    Status text is cleaned first (strip spaces, lowercase) because real
    files write the same status many ways: "Pending", " PENDING ", etc.
    """
    if not has_columns(df, "backlog_count"):
        return NOT_AVAILABLE
    data = _dedupe_orders(df)
    status = data["status"].astype(str).str.strip().str.lower()
    return int((status == PENDING_STATUS).sum())


def calculate_kpis(df: pd.DataFrame) -> dict:
    """
    Runs every Operations KPI and returns them in one dict, so app.py can
    show them all with a single call — same idea as the other domains.
    Each KPI is independent: one missing column only affects that KPI.
    """
    return {
        "avg_fulfillment_time": calculate_avg_fulfillment_time(df),
        "on_time_delivery_rate": calculate_on_time_delivery_rate(df),
        "cycle_time": calculate_cycle_time(df),
        "backlog_count": calculate_backlog_count(df),
    }


# ---------------------------------------------------------------------
# Standalone test: run from the repo root with
#     python domains/operations.py
# Not used by app.py — it only runs when this file is executed directly.
# ---------------------------------------------------------------------
if __name__ == "__main__":
    from pathlib import Path

    csv_path = Path(__file__).resolve().parent.parent / "sample_data" / "demo_operations.csv"
    demo = pd.read_csv(csv_path)
    results = calculate_kpis(demo)

    # Hand-checked answers for demo_operations.csv (independent Pandas calc).
    expected = {
        "avg_fulfillment_time": 7.3,
        "on_time_delivery_rate": 44.44,
        "cycle_time": 3.72,
        "backlog_count": 9,
    }

    print("--- Full demo_operations.csv ---")
    all_pass = True
    for name, value in results.items():
        ok = abs(value - expected[name]) < 0.01
        all_pass = all_pass and ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {value} (expected {expected[name]})")

    # Missing-column safety test: remove delivery_date.
    # Fulfillment time AND on-time rate need it, so only those two may fail.
    print("\n--- Same data WITHOUT delivery_date column ---")
    safe = calculate_kpis(demo.drop(columns=["delivery_date"]))
    for name, value in safe.items():
        print(f"{name}: {value}")
    safety_ok = (
        safe["avg_fulfillment_time"] == NOT_AVAILABLE
        and safe["on_time_delivery_rate"] == NOT_AVAILABLE
        and safe["cycle_time"] == expected["cycle_time"]
        and safe["backlog_count"] == expected["backlog_count"]
    )
    print("PASS" if safety_ok else "FAIL", "missing-column safety")

    print("\nALL TESTS PASSED" if (all_pass and safety_ok) else "\nSOME TESTS FAILED")
