"""
reports/excel_exporter.py
Step 7 of the pipeline: Excel Export.

Job of this module (and ONLY this module):
- Take whatever results the other modules already calculated (KPIs,
  anomaly flags, data quality, and trend results) and write them
  into a single, readable Excel workbook using openpyxl.

NOT this module's job:
- Calculating anything itself. This file never touches raw formulas —
  it only formats and writes numbers that other modules already produced.
  If a number here is wrong, the bug is in the module that calculated it,
  not here.

Design note: `quality_report` and `trend_report` are OPTIONAL parameters,
defaulting to None. This lets the exporter still work standalone even
if one of those modules isn't available in a given run.
"""

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows


HEADER_FILL = PatternFill(start_color="1F3864", end_color="1F3864", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
TITLE_FONT = Font(bold=True, size=14, color="1F3864")
LABEL_FONT = Font(bold=True, size=10)


def _style_header_row(ws, row_num: int, n_cols: int) -> None:
    """Applies the dark-blue header-row style to any sheet's first row.
    Small helper so every sheet looks consistent without repeating code."""
    for col in range(1, n_cols + 1):
        cell = ws.cell(row=row_num, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")


def _autofit_columns(ws, min_width: int = 12, max_width: int = 40) -> None:
    """openpyxl doesn't auto-size columns like Excel does natively, so we
    estimate a reasonable width from the longest value in each column.
    Uses cell coordinates rather than iterating column objects directly,
    since merged-cell sheets (like the Summary title) contain MergedCell
    objects that don't expose a column_letter attribute."""
    widths = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is None:
                continue
            col_letter = cell.column_letter if hasattr(cell, "column_letter") else None
            if col_letter is None:
                continue
            widths[col_letter] = max(widths.get(col_letter, 0), len(str(cell.value)))

    for col_letter, length in widths.items():
        ws.column_dimensions[col_letter].width = min(max(length + 2, min_width), max_width)


def _write_summary_sheet(wb: Workbook, kpis: dict) -> None:
    """
    Sheet 1: Summary — the KPI cards from the dashboard wireframe
    (Revenue, Profit, Margin, AOV, Growth), laid out as a simple label/
    value table so it reads like a management report, not raw data.
    """
    ws = wb.active
    ws.title = "Summary"

    ws["A1"] = "InsightPilot 360 — Sales Summary"
    ws["A1"].font = TITLE_FONT
    ws.merge_cells("A1:B1")

    rows = [
        ("Revenue", f"${kpis['revenue']:,.2f}"),
        ("Profit", f"${kpis['profit']:,.2f}"),
        ("Margin %", f"{kpis['margin_pct']}%"),
        ("Average Order Value", f"${kpis['aov']:,.2f}"),
        ("Revenue Growth (MoM)", f"{kpis['growth_pct']}%"),
    ]

    start_row = 3
    for i, (label, value) in enumerate(rows):
        ws.cell(row=start_row + i, column=1, value=label).font = LABEL_FONT
        ws.cell(row=start_row + i, column=2, value=value)

    _autofit_columns(ws)


def _write_ranked_sheet(wb: Workbook, sheet_name: str, ranked_list: list, label_col: str) -> None:
    """
    Used for both Top Products and Top Regions — same shape of data
    (a list of (name, revenue) tuples), so one function handles both
    instead of writing near-duplicate code twice.
    """
    ws = wb.create_sheet(sheet_name)
    ws.append([label_col, "Revenue"])
    _style_header_row(ws, 1, 2)

    for name, revenue in ranked_list:
        ws.append([name, revenue])
        ws.cell(row=ws.max_row, column=2).number_format = "$#,##0.00"

    _autofit_columns(ws)


def _write_anomaly_sheet(wb: Workbook, anomaly_report: dict) -> None:
    """
    Sheet: Anomalies — flattens the anomaly_engine's report (one entry
    per checked column, e.g. revenue/quantity) into a single readable
    table: which column, which order, what value, which method flagged it.
    """
    ws = wb.create_sheet("Anomalies")
    ws.append(["Column Checked", "Method", "Order ID", "Flagged Value"])
    _style_header_row(ws, 1, 4)

    any_rows = False
    for column, summary in anomaly_report.items():
        for row in summary["anomaly_rows"]:
            ws.append([column, summary["method"], row.get("order_id"), row.get(column)])
            any_rows = True

    if not any_rows:
        ws.append(["No anomalies detected", "", "", ""])

    _autofit_columns(ws)


def _write_quality_sheet(wb: Workbook, quality_report: dict) -> None:
    """
    Sheet: Data Quality — reads the report shape produced by
    data_quality.run_data_quality_checks(): a dict with "summary"
    (flat numbers) plus "missing_values", "duplicates", "invalid_dates"
    (each holding the detailed row-level breakdown).
    """
    ws = wb.create_sheet("Data Quality")

    ws["A1"] = "Data Quality Summary"
    ws["A1"].font = TITLE_FONT
    ws.merge_cells("A1:B1")

    summary = quality_report.get("summary", {})
    summary_rows = [
        ("Rows with missing values", summary.get("missing_values_rows", "N/A")),
        ("Duplicate rows", summary.get("duplicate_rows", "N/A")),
        ("Invalid date rows", summary.get("invalid_date_rows", "N/A")),
    ]
    start_row = 3
    for i, (label, value) in enumerate(summary_rows):
        ws.cell(row=start_row + i, column=1, value=label).font = LABEL_FONT
        ws.cell(row=start_row + i, column=2, value=value)

    # Detail: which columns have missing values
    detail_row = start_row + len(summary_rows) + 2
    ws.cell(row=detail_row, column=1, value="Missing Values by Column").font = LABEL_FONT
    missing_by_column = quality_report.get("missing_values", {}).get("missing_by_column", {})
    for i, (col, count) in enumerate(missing_by_column.items()):
        ws.cell(row=detail_row + 1 + i, column=1, value=col)
        ws.cell(row=detail_row + 1 + i, column=2, value=count)

    _autofit_columns(ws)


def _write_trend_sheet(wb: Workbook, trend_report: dict) -> None:
    """
    Sheet: Revenue Trend — reads the report shape produced by
    trend_analyzer.run_trend_analysis(): "overall_growth" (one dict),
    "segment_trends" (a list of per-region/product dicts), and
    "insights" (plain-English sentences).
    """
    ws = wb.create_sheet("Revenue Trend")

    ws["A1"] = "Revenue Trend"
    ws["A1"].font = TITLE_FONT
    ws.merge_cells("A1:B1")

    overall = trend_report.get("overall_growth", {})
    overall_rows = [
        ("Current Period", overall.get("current_period")),
        ("Previous Period", overall.get("previous_period")),
        ("Current Value", overall.get("current_value")),
        ("Previous Value", overall.get("previous_value")),
        ("Growth %", overall.get("growth_percent")),
    ]
    start_row = 3
    for i, (label, value) in enumerate(overall_rows):
        ws.cell(row=start_row + i, column=1, value=label).font = LABEL_FONT
        ws.cell(row=start_row + i, column=2, value=value)

    # Segment breakdown table
    table_start = start_row + len(overall_rows) + 2
    headers = ["Segment", "Current", "Previous", "Growth %"]
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=table_start, column=col_idx, value=header)
    _style_header_row(ws, table_start, len(headers))

    for i, seg in enumerate(trend_report.get("segment_trends", [])):
        row_num = table_start + 1 + i
        ws.cell(row=row_num, column=1, value=seg.get("segment"))
        ws.cell(row=row_num, column=2, value=seg.get("current_value"))
        ws.cell(row=row_num, column=3, value=seg.get("previous_value"))
        ws.cell(row=row_num, column=4, value=seg.get("growth_percent"))

    # Insights, as plain sentences below the table
    insights_row = table_start + len(trend_report.get("segment_trends", [])) + 3
    ws.cell(row=insights_row, column=1, value="Insights").font = LABEL_FONT
    for i, sentence in enumerate(trend_report.get("insights", [])):
        ws.cell(row=insights_row + 1 + i, column=1, value=sentence)

    _autofit_columns(ws)


def _write_raw_data_sheet(wb: Workbook, df: pd.DataFrame) -> None:
    """Sheet: Raw Data — the full original dataset, for anyone who wants
    to double-check a number against the source rows."""
    ws = wb.create_sheet("Raw Data")
    for row in dataframe_to_rows(df, index=False, header=True):
        ws.append(row)
    _style_header_row(ws, 1, len(df.columns))
    _autofit_columns(ws)


def export_to_excel(
    df: pd.DataFrame,
    kpis: dict,
    anomaly_report: dict,
    quality_report: dict = None,
    trend_report: dict = None,
    output_path: str = "InsightPilot_360_Report.xlsx",
) -> str:
    """
    Builds the full Excel workbook and saves it. This is the one function
    app.py will call — same "single wrapper function" pattern as
    calculate_kpis() and run_anomaly_checks() in the other modules.

    quality_report -> pass the dict from data_quality.run_data_quality_checks(df)
    trend_report    -> pass the dict from trend_analyzer.run_trend_analysis(df)
    Both default to None so this still works standalone if either module
    isn't available in a given run.
    """
    wb = Workbook()

    _write_summary_sheet(wb, kpis)
    _write_ranked_sheet(wb, "Top Products", kpis["top_products"], "Product")
    _write_ranked_sheet(wb, "Top Regions", kpis["top_regions"], "Region")
    _write_anomaly_sheet(wb, anomaly_report)

    if quality_report is not None:
        _write_quality_sheet(wb, quality_report)

    if trend_report is not None:
        _write_trend_sheet(wb, trend_report)

    _write_raw_data_sheet(wb, df)

    wb.save(output_path)
    return output_path


if __name__ == "__main__":
    # Manual test: run `python reports/excel_exporter.py` from the repo
    # root. Now pulls in ALL FIVE core modules, including the teammate's
    # data_quality.py and trend_analyzer.py.
    import sys
    sys.path.append("core")
    from data_loader import load_data
    from kpi_engine import calculate_kpis
    from anomaly_engine import run_anomaly_checks
    from data_quality import run_data_quality_checks
    from trend_analyzer import run_trend_analysis

    df = load_data("sample_data/demo_sales.csv")
    kpis = calculate_kpis(df)
    anomaly_report = run_anomaly_checks(df, method="iqr")
    quality_report = run_data_quality_checks(df, date_column="order_date")
    trend_report = run_trend_analysis(df, date_column="order_date", value_column="revenue", segment_column="region")

    path = export_to_excel(
        df, kpis, anomaly_report,
        quality_report=quality_report,
        trend_report=trend_report,
        output_path="sample_data/test_report.xlsx",
    )
    print(f"Excel report written to: {path}")