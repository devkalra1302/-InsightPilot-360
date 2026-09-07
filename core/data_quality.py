"""
data_quality.py
----------------
Part of InsightPilot 360 (Sales MVP) — Phase 1.

This module checks the quality of an uploaded sales dataset WITHOUT
modifying it. It only reports problems (missing values, duplicate rows,
invalid dates) so the Streamlit dashboard can display a "Data Quality"
panel, exactly as shown in the product wireframe:

    Data Quality
    Missing values: 12 rows
    Duplicates: 3 rows
    Invalid dates: 0

No cleaning/fixing happens here — that is intentionally out of scope for
Phase 1 (see product spec, Section 3).

Author: Harsh
"""

import pandas as pd


def check_missing_values(df: pd.DataFrame) -> dict:
    """
    Count missing (NaN/empty) values in the dataset.

    What it takes in:
        df -> the full sales DataFrame (as produced by data_loader.py)

    What it gives out:
        A dictionary like:
        {
            "total_missing_rows": 12,
            "missing_by_column": {"cost": 5, "region": 7}
        }
        "total_missing_rows" = number of rows that have AT LEAST ONE
        missing value (not total missing cells).
        "missing_by_column" only lists columns that actually have
        missing values (columns with 0 missing are skipped).
    """
    if df is None or df.empty:
        return {"total_missing_rows": 0, "missing_by_column": {}}

    missing_per_column = df.isna().sum()
    missing_by_column = {
        col: int(count) for col, count in missing_per_column.items() if count > 0
    }

    # A row counts as "missing" if ANY of its columns is NaN
    total_missing_rows = int(df.isna().any(axis=1).sum())

    return {
        "total_missing_rows": total_missing_rows,
        "missing_by_column": missing_by_column,
    }


def check_duplicate_rows(df: pd.DataFrame, subset: list | None = None) -> dict:
    """
    Find fully (or partially) duplicated rows.

    What it takes in:
        df     -> the full sales DataFrame
        subset -> optional list of column names to check duplicates on
                  (e.g. ["order_id"]). If None, checks EVERY column —
                  meaning the entire row must repeat to count as a duplicate.

    What it gives out:
        {
            "duplicate_count": 3,
            "duplicate_row_indexes": [14, 27, 40]
        }
        duplicate_row_indexes are the DataFrame index positions of the
        duplicate rows (excluding the first occurrence), so the dashboard
        or a future cleaning step can locate them if needed.
    """
    if df is None or df.empty:
        return {"duplicate_count": 0, "duplicate_row_indexes": []}

    is_duplicate = df.duplicated(subset=subset, keep="first")
    duplicate_indexes = df[is_duplicate].index.tolist()

    return {
        "duplicate_count": int(is_duplicate.sum()),
        "duplicate_row_indexes": duplicate_indexes,
    }


def check_invalid_dates(df: pd.DataFrame, date_column: str = "order_date") -> dict:
    """
    Find rows where the date column cannot be parsed as a real date.

    What it takes in:
        df          -> the full sales DataFrame
        date_column -> name of the column that holds the order date.
                        Defaults to "order_date" (matches demo_sales.csv).
                        Pass a different name if data_loader.py maps it
                        to something else after column mapping.

    What it gives out:
        {
            "invalid_date_count": 0,
            "invalid_date_row_indexes": []
        }
        If the date_column doesn't exist in the DataFrame at all, returns
        the same shape with count 0 and an extra "error" key explaining
        why (so the caller can show a friendly message instead of crashing).
    """
    if df is None or df.empty:
        return {"invalid_date_count": 0, "invalid_date_row_indexes": []}

    if date_column not in df.columns:
        return {
            "invalid_date_count": 0,
            "invalid_date_row_indexes": [],
            "error": f"Column '{date_column}' not found in dataset.",
        }

    parsed_dates = pd.to_datetime(df[date_column], errors="coerce")
    invalid_mask = parsed_dates.isna() & df[date_column].notna()
    # notna() check above excludes rows that were ALREADY missing —
    # those are counted by check_missing_values(), not here, to avoid
    # double-counting the same row under two different issues.

    invalid_indexes = df[invalid_mask].index.tolist()

    return {
        "invalid_date_count": int(invalid_mask.sum()),
        "invalid_date_row_indexes": invalid_indexes,
    }


def run_data_quality_checks(df: pd.DataFrame, date_column: str = "order_date") -> dict:
    """
    Main entry point — runs all three checks together and returns one
    combined report. This is the function app.py / the Streamlit
    dashboard should call directly.

    What it takes in:
        df          -> the full sales DataFrame
        date_column -> name of the date column (default "order_date")

    What it gives out:
        {
            "missing_values": {...},   # output of check_missing_values()
            "duplicates": {...},       # output of check_duplicate_rows()
            "invalid_dates": {...},    # output of check_invalid_dates()
            "summary": {
                "missing_values_rows": 12,
                "duplicate_rows": 3,
                "invalid_date_rows": 0
            }
        }
        The "summary" key is a flat, ready-to-display version matching
        the wireframe panel exactly — app.py can plug these three
        numbers straight into the UI without digging into nested dicts.
    """
    missing_result = check_missing_values(df)
    duplicate_result = check_duplicate_rows(df)
    invalid_date_result = check_invalid_dates(df, date_column=date_column)

    return {
        "missing_values": missing_result,
        "duplicates": duplicate_result,
        "invalid_dates": invalid_date_result,
        "summary": {
            "missing_values_rows": missing_result["total_missing_rows"],
            "duplicate_rows": duplicate_result["duplicate_count"],
            "invalid_date_rows": invalid_date_result["invalid_date_count"],
        },
    }


if __name__ == "__main__":
    # Quick manual test using the demo dataset — run this file directly
    # with: python core/data_quality.py
    sample_df = pd.read_csv("sample_data/demo_sales.csv")
    report = run_data_quality_checks(sample_df, date_column="order_date")
    print(report["summary"])