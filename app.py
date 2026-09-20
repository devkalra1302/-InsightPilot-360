"""
app.py
Step 6 of the pipeline: the Streamlit dashboard itself.

Job of this file (and ONLY this file):
- Give the user a webpage: pick a domain, upload a file, then display
  everything the domain's KPI module + the shared core modules already
  calculated (KPIs, data quality, trend, anomalies), plus a button to
  download the Excel report.

NOT this file's job:
- Calculating anything. Every number on this page comes from calling one
  of the domain functions below — app.py never does its own math. If a
  number is wrong, the bug lives in that domain module, not here.

PHASE 2 CHANGE:
- Before, this file only knew about Sales. Now there are 5 domains, each
  with different column names and different KPI shapes (some KPIs are
  plain numbers, some are lists like "Reorder Flag" or "Top Products").
  DOMAIN_CONFIG below is the "Domain Manager" the spec describes — one
  dictionary entry per domain, telling this file everything it needs to
  route to the right logic WITHOUT hardcoding Sales-specific column names
  anywhere in the display code.
"""

import sys
import os
import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append("core")
sys.path.append("domains")
sys.path.append("reports")

from data_loader import load_data, profile_data
from data_quality import run_data_quality_checks
from trend_analyzer import run_trend_analysis
from anomaly_engine import run_anomaly_checks
from excel_exporter import export_to_excel

from domains import sales, finance, inventory, customer, operations


# ---------------------------------------------------------------------
# DOMAIN MANAGER
# ---------------------------------------------------------------------
# One entry per domain. This is the single place that knows column names
# differ across domains — everything below this dictionary is generic
# and works the same way regardless of which domain is selected.
#
# "metrics"  -> KPIs that are a single number. Shown as st.metric cards.
#               Each tuple is (dict_key, display_label, format_type).
#               format_type is one of: "money", "percent", "number", "days".
# "lists"    -> KPIs that are a list of things (flagged products, top N).
#               Each tuple is (dict_key, display_label, column_names).
#               column_names has 2 entries for (name, value) pairs like
#               Top Products, or 1 entry for plain name-only lists like
#               Reorder Flag / Dead Stock.
# "date_column" / "value_column" / "segment_column" feed run_trend_analysis.
#               segment_column=None means "skip the breakdown chart, still
#               show the overall trend." value_column=None means "skip
#               trend analysis entirely" — used for Operations, which has
#               no revenue-like numeric column to trend.
DOMAIN_CONFIG = {
    "Sales": {
        "calculate_kpis": sales.calculate_kpis,
        "date_column": "order_date",
        "value_column": "revenue",
        "segment_column": "region",
        "metrics": [
            ("revenue", "Revenue", "money"),
            ("profit", "Profit", "money"),
            ("margin_pct", "Margin", "percent"),
            ("aov", "AOV", "money"),
            ("growth_pct", "Growth (MoM)", "percent"),
        ],
        "lists": [
            ("top_products", "Top Products", ["Product", "Revenue"]),
            ("top_regions", "Top Regions", ["Region", "Revenue"]),
        ],
    },
    "Finance": {
        "calculate_kpis": finance.calculate_kpis,
        "date_column": "date",
        "value_column": "income",
        "segment_column": None,
        "metrics": [
            ("total_revenue", "Total Revenue", "money"),
            ("total_expenses", "Total Expenses", "money"),
            ("net_profit", "Net Profit", "money"),
            ("burn_rate", "Burn Rate / mo", "money"),
            ("expense_growth_pct", "Expense Growth", "percent"),
        ],
        "lists": [],
    },
    "Inventory": {
        "calculate_kpis": inventory.calculate_kpis,
        "date_column": "date",
        "value_column": "units_sold",
        "segment_column": "product",
        "metrics": [
            ("stock_turnover_ratio", "Stock Turnover Ratio", "number"),
            ("days_of_inventory", "Days of Inventory", "days"),
        ],
        "lists": [
            ("reorder_flag", "Products Needing Reorder", ["Product"]),
            ("dead_stock", "Dead Stock (No Sales)", ["Product"]),
        ],
    },
    "Customer": {
        "calculate_kpis": customer.calculate_kpis,
        "date_column": "order_date",
        "value_column": "sale_amount",
        "segment_column": None,
        "metrics": [
            ("total_customers", "Total Customers", "number"),
            ("repeat_purchase_rate", "Repeat Purchase Rate", "percent"),
            ("churn_rate", "Churn Rate", "percent"),
            ("customer_lifetime_value", "Customer Lifetime Value", "money"),
        ],
        "lists": [],
    },
    "Operations": {
        "calculate_kpis": operations.calculate_kpis,
        "date_column": None,   # no single date column suits a trend chart
        "value_column": None,  # no revenue-like numeric column to trend
        "segment_column": None,
        "metrics": [
            ("avg_fulfillment_time", "Avg Fulfillment Time", "days"),
            ("on_time_delivery_rate", "On-Time Delivery Rate", "percent"),
            ("cycle_time", "Cycle Time", "days"),
            ("backlog_count", "Backlog Count", "number"),
        ],
        "lists": [],
    },
}


def format_metric(value, format_type: str) -> str:
    """
    Turns a raw KPI value into a display string for st.metric.
    Handles NOT_AVAILABLE (a string) the same way regardless of which
    domain module produced it — every domain uses the identical message,
    so we just check "is this a string" rather than importing each
    module's NOT_AVAILABLE constant separately.
    """
    if isinstance(value, str):
        return value  # NOT_AVAILABLE message — show as-is, don't format
    if format_type == "money":
        return f"${value:,.2f}"
    if format_type == "percent":
        return f"{value}%"
    if format_type == "days":
        return f"{value} days"
    return str(value)  # "number" and anything else: show plainly


def render_metrics(kpis: dict, metrics_config: list) -> None:
    """Lays out up to 5 st.metric cards per row, however many this domain has."""
    for i in range(0, len(metrics_config), 5):
        row = metrics_config[i:i + 5]
        cols = st.columns(len(row))
        for col, (key, label, fmt) in zip(cols, row):
            col.metric(label, format_metric(kpis[key], fmt))


def render_lists(kpis: dict, lists_config: list) -> None:
    """
    Shows list-shaped KPIs (Top Products, Reorder Flag, etc.) as small
    tables side by side. Handles two shapes:
    - list of (name, value) tuples, e.g. Sales' top_products
    - plain list of names, e.g. Inventory's reorder_flag
    - the NOT_AVAILABLE string, if the required columns were missing
    - an empty list, e.g. "no products need reordering" — shown as a
      friendly message instead of a blank table.
    """
    if not lists_config:
        return
    cols = st.columns(len(lists_config))
    for col, (key, label, column_names) in zip(cols, lists_config):
        with col:
            st.subheader(label)
            value = kpis[key]
            if isinstance(value, str):
                st.write(value)  # NOT_AVAILABLE message
            elif len(value) == 0:
                st.write("None.")
            elif len(column_names) == 2:
                # (name, value) tuples, e.g. [("Desk Lamp", 36173.19), ...]
                table = pd.DataFrame(value, columns=column_names)
                st.dataframe(table, hide_index=True)
            else:
                # plain list of names, e.g. ["USB-C Hub", "Webcam HD"]
                table = pd.DataFrame(value, columns=column_names)
                st.dataframe(table, hide_index=True)


st.set_page_config(page_title="InsightPilot 360", layout="wide")

st.title("📊 InsightPilot 360")

domain = st.selectbox(
    "Which domain is this data?",
    options=list(DOMAIN_CONFIG.keys()),
)
config = DOMAIN_CONFIG[domain]

st.caption(f"Upload a {domain} CSV/Excel file to get instant KPIs, data quality checks, trends, and anomaly flags.")

uploaded_file = st.file_uploader(f"Upload your {domain.lower()} file", type=["csv", "xlsx", "xls"])

if uploaded_file is None:
    st.info(f"👆 Upload a file to get started, or try the sample file at sample_data/demo_{domain.lower()}.csv")
    st.stop()

# ---- Step 1: Load & Profile ----
df = load_data(uploaded_file)
profile = profile_data(df)

st.success(f"Loaded {profile['n_rows']} rows, {profile['n_columns']} columns.")

with st.expander("🔍 Raw Data Profile"):
    st.write(f"**Columns:** {', '.join(profile['columns'])}")
    st.dataframe(profile["preview"])

# ---- Step 3: Data Quality ----
# date_column now comes from DOMAIN_CONFIG instead of being hardcoded to
# "order_date" — Finance and Inventory both use "date" instead.
if config["date_column"] is not None:
    quality_report = run_data_quality_checks(df, date_column=config["date_column"])
    quality_summary = quality_report["summary"]

    st.header("Data Quality")
    q1, q2, q3 = st.columns(3)
    q1.metric("Missing Value Rows", quality_summary["missing_values_rows"])
    q2.metric("Duplicate Rows", quality_summary["duplicate_rows"])
    q3.metric("Invalid Date Rows", quality_summary["invalid_date_rows"])

    missing_by_column = quality_report["missing_values"]["missing_by_column"]
    if missing_by_column:
        st.write("**Missing values by column:**", missing_by_column)
else:
    quality_report = None
    st.info("Data quality date-based checks are skipped for this domain (no single date column configured).")

# ---- Step 4: KPIs ----
# The only line that changes per domain: which module's calculate_kpis
# gets called. Everything after this is generic.
kpis = config["calculate_kpis"](df)

st.header("Key Metrics")
render_metrics(kpis, config["metrics"])
render_lists(kpis, config["lists"])

# ---- Step 5: Trend + Anomalies ----
# Trend analysis needs a numeric value column to track over time.
# Operations has none (it's all dates/status, no revenue-like number), so
# it's skipped entirely for that domain rather than forcing a bad fit.
trend_report = None
if config["value_column"] is not None and config["date_column"] is not None:
    try:
        trend_report = run_trend_analysis(
            df,
            date_column=config["date_column"],
            value_column=config["value_column"],
            segment_column=config["segment_column"],
        )
    except Exception as e:
        st.warning(f"Trend analysis couldn't run for this domain/file: {e}")

if trend_report is not None:
    st.header("Trend")
    overall = trend_report["overall_growth"]
    st.write(
        f"**{overall['current_period']}**: {overall['current_value']:,.2f} "
        f"vs **{overall['previous_period']}**: {overall['previous_value']:,.2f} "
        f"({overall['growth_percent']}% growth)"
    )

    segment_df = pd.DataFrame(trend_report.get("segment_trends", []))
    if not segment_df.empty:
        fig = px.bar(
            segment_df, x="segment", y="growth_percent",
            color="growth_percent", color_continuous_scale="RdYlGn",
            title=f"Growth % by {config['segment_column'].title()} (Current vs Previous Month)",
            labels={"segment": config["segment_column"].title(), "growth_percent": "Growth %"},
        )
        st.plotly_chart(fig, use_container_width=True)

    if trend_report.get("insights"):
        st.write("**Insights:**")
        for sentence in trend_report["insights"]:
            st.write(f"- {sentence}")
else:
    st.header("Trend")
    st.info("Trend-over-time analysis isn't available for this domain in Phase 2 (no comparable numeric value to track).")

st.header("Anomalies")
anomaly_report = run_anomaly_checks(df, method="iqr")
for column, summary in anomaly_report.items():
    st.subheader(f"{column.title()} — {summary['n_anomalies']} anomalies found ({summary['method']})")
    if summary["anomaly_rows"]:
        st.dataframe(pd.DataFrame(summary["anomaly_rows"]))
    else:
        st.write("No anomalies detected.")

# ---- Step 7: Excel Export ----
st.header("Export")
if st.button("Generate Excel Report"):
    output_path = export_to_excel(
        df, kpis, anomaly_report,
        quality_report=quality_report,
        trend_report=trend_report,
        output_path=f"InsightPilot_360_{domain}_Report.xlsx",
    )
    with open(output_path, "rb") as f:
        st.download_button(
            "⬇ Download Excel Report",
            data=f,
            file_name=f"InsightPilot_360_{domain}_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )