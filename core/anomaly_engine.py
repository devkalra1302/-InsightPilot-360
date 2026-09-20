"""
core/anomaly_engine.py
Step 5 of the pipeline: Anomaly Detection (rule-based, per spec —
"NumPy z-score/IQR... no model training required").

Job of this module (and ONLY this module):
- Flag rows that look statistically unusual using simple, explainable
  statistics. Every flag must be traceable to a formula — no ML.

NOT this module's job:
- Deciding those rows are "wrong" or removing them (a real anomaly might be
  a legitimate huge order — this module just raises a flag for a human).

PHASE 2 CHANGE:
- run_anomaly_checks used to assume Sales's columns ("revenue",
  "quantity") whenever no columns list was given. Now that app.py calls
  this for 5 different domains, each with different column names, a
  column that doesn't exist in a given domain's file must be skipped
  gracefully — not crash the whole dashboard. Same pattern every other
  Phase 2 file follows: check first, return a "not available" style
  result if the column is missing, keep going for everything else.
"""

import pandas as pd
import numpy as np

NOT_AVAILABLE = "Not available — required column(s) not provided"


def detect_anomalies_zscore(df: pd.DataFrame, column: str, threshold: float = 3.0) -> pd.DataFrame:
    """
    Z-score method: how many standard deviations away from the mean is
    each value? Anything beyond `threshold` (default 3) is flagged.
    z = (value - mean) / std_dev
    """
    result = df.copy()
    mean = df[column].mean()
    std = df[column].std()

    if std == 0 or pd.isna(std):
        result[f"{column}_zscore"] = 0.0
        result[f"{column}_is_anomaly"] = False
        return result

    result[f"{column}_zscore"] = ((df[column] - mean) / std).round(2)
    result[f"{column}_is_anomaly"] = result[f"{column}_zscore"].abs() > threshold
    return result


def detect_anomalies_iqr(df: pd.DataFrame, column: str, multiplier: float = 1.5) -> pd.DataFrame:
    """
    IQR method: flags values far outside the "normal" middle 50% of data.
    Less thrown off by extreme values than z-score, since it skips the mean.
    IQR = Q3 - Q1; bounds = Q1 - m*IQR, Q3 + m*IQR
    """
    result = df.copy()
    q1 = df[column].quantile(0.25)
    q3 = df[column].quantile(0.75)
    iqr = q3 - q1

    lower_bound = q1 - multiplier * iqr
    upper_bound = q3 + multiplier * iqr

    result[f"{column}_is_anomaly"] = (df[column] < lower_bound) | (df[column] > upper_bound)
    return result


def get_anomaly_summary(df: pd.DataFrame, column: str, method: str = "zscore") -> dict:
    """
    Runs the chosen method on one column, returns a clean summary dict.
    NEW: checks the column actually exists BEFORE touching it. A missing
    column returns the same NOT_AVAILABLE shape the KPI modules use,
    instead of a KeyError.
    """
    if column not in df.columns:
        return {
            "column": column,
            "method": method,
            "n_anomalies": 0,
            "anomaly_rows": [],
            "available": False,
            "note": NOT_AVAILABLE,
        }

    if method == "zscore":
        flagged_df = detect_anomalies_zscore(df, column)
    elif method == "iqr":
        flagged_df = detect_anomalies_iqr(df, column)
    else:
        raise ValueError("method must be 'zscore' or 'iqr'")

    anomaly_col = f"{column}_is_anomaly"
    anomalies = flagged_df[flagged_df[anomaly_col]]

    return {
        "column": column,
        "method": method,
        "n_anomalies": len(anomalies),
        "anomaly_rows": anomalies.to_dict(orient="records"),
        "available": True,
    }


def run_anomaly_checks(df: pd.DataFrame, columns: list = None, method: str = "zscore") -> dict:
    """
    The one function app.py will call. Checks revenue and quantity by
    default (Sales' historical default, kept for backward compatibility
    when nothing is passed), but Phase 2 callers should always pass an
    explicit `columns` list matching the current domain — see
    DOMAIN_CONFIG in app.py.
    """
    if columns is None:
        columns = ["revenue", "quantity"]

    return {col: get_anomaly_summary(df, col, method=method) for col in columns}


def print_anomaly_report(report: dict) -> None:
    """Terminal-friendly dump for testing before app.py exists."""
    for column, summary in report.items():
        print(f"\n=== {column} ({summary['method']}) ===")
        if not summary.get("available", True):
            print(f"  {summary['note']}")
            continue
        print(f"Anomalies found: {summary['n_anomalies']}")
        for row in summary["anomaly_rows"]:
            order_id = row.get("order_id", "?")
            print(f"  - order_id {order_id}: {column} = {row[column]}")


if __name__ == "__main__":
    from data_loader import load_data

    df = load_data("sample_data/demo_sales.csv")

    print("########## Z-SCORE METHOD ##########")
    report_z = run_anomaly_checks(df, method="zscore")
    print_anomaly_report(report_z)

    print("\n########## IQR METHOD ##########")
    report_iqr = run_anomaly_checks(df, method="iqr")
    print_anomaly_report(report_iqr)