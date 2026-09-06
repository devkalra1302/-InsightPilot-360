"""
core/data_loader.py
Step 1 of the pipeline: Upload & Profile.

Job of this module (and ONLY this module):
- Load a raw CSV/Excel file into a DataFrame.
- Produce a lightweight PROFILE of that raw data (shape, column names,
  dtypes, a preview) so the UI can show "here's what you gave me" before
  any cleaning happens.

NOT this module's job (that's data_quality.py, next):
- Deciding what's missing/duplicate/invalid.
- Fixing or dropping bad rows.
"""

import pandas as pd


def load_data(file_path_or_buffer):
    """
    Load a sales file into a DataFrame.
    Accepts either a file path (str) or a file-like object (what Streamlit's
    st.file_uploader gives you) — pandas handles both the same way.
    Supports .csv and .xlsx/.xls by checking the file extension.
    """
    name = getattr(file_path_or_buffer, "name", str(file_path_or_buffer))

    if name.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(file_path_or_buffer)
    else:
        df = pd.read_csv(file_path_or_buffer)

    return df


def profile_data(df: pd.DataFrame) -> dict:
    """
    Build a raw-data profile: a snapshot of the file as-uploaded, before any
    cleaning. Returns a plain dict so it's easy to hand to Streamlit or tests
    without any UI-specific objects leaking into core logic.
    """
    profile = {
        "n_rows": len(df),
        "n_columns": len(df.columns),
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "missing_per_column": df.isna().sum().to_dict(),
        "preview": df.head(5),
    }
    return profile


def print_profile(profile: dict) -> None:
    """Quick human-readable dump of a profile dict — for terminal testing."""
    print(f"Rows: {profile['n_rows']} | Columns: {profile['n_columns']}")
    print("\nColumns & dtypes:")
    for col in profile["columns"]:
        print(f"  - {col}: {profile['dtypes'][col]}  "
              f"(missing: {profile['missing_per_column'][col]})")
    print("\nPreview (first 5 rows):")
    print(profile["preview"])


if __name__ == "__main__":
    df = load_data("sample_data/demo_sales.csv")
    profile = profile_data(df)
    print_profile(profile)
    