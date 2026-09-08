"""
app.py
Step 6 of the pipeline: the Streamlit dashboard itself.

Job of this file (and ONLY this file):
- Give the user a webpage: upload a file, then display everything the
  other five modules already calculated (KPIs, data quality, trend,
  anomalies), plus a button to download the Excel report.

NOT this file's job:
- Calculating anything. Every number on this page comes from calling
  one of the five core functions below — app.py never does its own
  math. If a number is wrong, the bug lives in that module, not here.
"""

import sys
import os
import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append("core")
sys.path.append("reports")

from data_loader import load_data, profile_data
from data_quality import run_data_quality_checks
from kpi_engine import calculate_kpis
from trend_analyzer import run_trend_analysis
from anomaly_engine import run_anomaly_checks
from excel_exporter import export_to_excel


st.set_page_config(page_title="InsightPilot 360 — Sales MVP", layout="wide")

st.title("📊 InsightPilot 360 — Sales Dashboard")
st.caption("Upload a sales CSV/Excel file to get instant KPIs, data quality checks, trends, and anomaly flags.")

uploaded_file = st.file_uploader("Upload your sales file", type=["csv", "xlsx", "xls"])

if uploaded_file is None:
    st.info("👆 Upload a file to get started, or try the sample file at sample_data/demo_sales.csv")
    st.stop()

# ---- Step 1: Load & Profile ----
df = load_data(uploaded_file)
profile = profile_data(df)

st.success(f"Loaded {profile['n_rows']} rows, {profile['n_columns']} columns.")

with st.expander("🔍 Raw Data Profile"):
    st.write(f"**Columns:** {', '.join(profile['columns'])}")
    st.dataframe(profile["preview"])

# ---- Step 3: Data Quality ----
quality_report = run_data_quality_checks(df, date_column="order_date")
quality_summary = quality_report["summary"]

st.header("Data Quality")
q1, q2, q3 = st.columns(3)
q1.metric("Missing Value Rows", quality_summary["missing_values_rows"])
q2.metric("Duplicate Rows", quality_summary["duplicate_rows"])
q3.metric("Invalid Date Rows", quality_summary["invalid_date_rows"])

missing_by_column = quality_report["missing_values"]["missing_by_column"]
if missing_by_column:
    st.write("**Missing values by column:**", missing_by_column)

# ---- Step 4: KPIs ----
kpis = calculate_kpis(df)

st.header("Key Metrics")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Revenue", f"${kpis['revenue']:,.2f}")
k2.metric("Profit", f"${kpis['profit']:,.2f}")
k3.metric("Margin", f"{kpis['margin_pct']}%")
k4.metric("AOV", f"${kpis['aov']:,.2f}")
k5.metric("Growth (MoM)", f"{kpis['growth_pct']}%")

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Top Products")
    top_products_df = pd.DataFrame(kpis["top_products"], columns=["Product", "Revenue"])
    st.dataframe(top_products_df, hide_index=True)
with col_b:
    st.subheader("Top Regions")
    top_regions_df = pd.DataFrame(kpis["top_regions"], columns=["Region", "Revenue"])
    st.dataframe(top_regions_df, hide_index=True)

# ---- Step 5: Trend + Anomalies ----
trend_report = run_trend_analysis(df, date_column="order_date", value_column="revenue", segment_column="region")

st.header("Revenue Trend")
overall = trend_report["overall_growth"]
st.write(
    f"**{overall['current_period']}** revenue: ${overall['current_value']:,.2f} "
    f"vs **{overall['previous_period']}**: ${overall['previous_value']:,.2f} "
    f"({overall['growth_percent']}% growth)"
)

segment_df = pd.DataFrame(trend_report["segment_trends"])
if not segment_df.empty:
    fig = px.bar(
        segment_df, x="segment", y="growth_percent",
        color="growth_percent", color_continuous_scale="RdYlGn",
        title="Revenue Growth % by Region (Current vs Previous Month)",
        labels={"segment": "Region", "growth_percent": "Growth %"},
    )
    st.plotly_chart(fig, use_container_width=True)

if trend_report["insights"]:
    st.write("**Insights:**")
    for sentence in trend_report["insights"]:
        st.write(f"- {sentence}")

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
        output_path="InsightPilot_360_Report.xlsx",
    )
    with open(output_path, "rb") as f:
        st.download_button(
            "⬇ Download Excel Report",
            data=f,
            file_name="InsightPilot_360_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )