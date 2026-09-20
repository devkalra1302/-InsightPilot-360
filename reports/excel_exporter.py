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
- Knowing which domain it's exporting. It used to assume Sales's exact
  KPI names (revenue, profit, top_products, ...) — that broke the moment
  Finance/Inventory/Customer/Operations tried to export, since they don't
  have those keys. PHASE 2 FIX: this file now takes plain, already-built
  (label, value) rows and (sheet_name, columns, rows) list-sheets, built
  by app.py from DOMAIN_CONFIG. This file just writes what it's handed —
  it doesn't need to know a single domain-specific column name.

Design note: `quality_report`, `trend_report`, and `anomaly_report` are
OPTIONAL parameters, defaulting to None. Some domains (Operations) have
nothing to put in one or more of these sheets, and this file must not
crash just because a section is empty for that domain.
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


def _write_summary_sheet(wb: Workbook, domain_name: str, summary_rows: list) -> None:
    """
    Sheet 1: Summary — a simple label/value table so it reads like a
    management report, not raw data.

    summary_rows: a list of (label, already-formatted value string)
    tuples, e.g. [("Revenue", "$251,320.24"), ("Margin", "30.82%")].
    Built by app.py from that domain's DOMAIN_CONFIG metrics + kpis dict
    — this function has no idea what domain it's looking at, on purpose.
    """
    ws = wb.active
    ws.title = "Summary"

    ws["A1"] = f"InsightPilot 360 — {domain_name} Summary"
    ws["A1"].font = TITLE_FONT
    ws.merge_cells("A1:B1")

    start_row = 3
    for i, (label, value) in enumerate(summary_rows):
        ws.cell(row=start_row + i, column=1, value=label).font = LABEL_FONT
        ws.cell(row=start_row + i, column=2, value=value)

    _autofit_columns(ws)


def _write_list_sheet(wb: Workbook, sheet_name: str, columns: list, rows) -> None:
    """
    Writes any list-shaped KPI as its own sheet — used for Top Products,
    Top Regions, Reorder Flag, Dead Stock, or any future domain's list
    KPIs. Handles both shapes app.py's render_lists() already handles:
    - 2 columns: (name, value) pairs, e.g. Top Products
    - 1 column: plain names, e.g. Reorder Flag
    Also handles the two "nothing to show" cases gracefully: the KPI
    came back as NOT_AVAILABLE (a string), or as a genuinely empty list.
    """
    ws = wb.create_sheet(sheet_name)

    if isinstance(rows, str):
        # NOT_AVAILABLE message — required columns weren't in this file.
        ws.append([rows])
        _autofit_columns(ws)
        return

    ws.append(columns)
    _style_header_row(ws, 1, len(columns))

    if len(rows) == 0:
        ws.append(["None"] + [""] * (len(columns) - 1))
    else:
        for item in rows:
            if len(columns) == 2:
                name, value = item
                ws.append([name, value])
                ws.cell(row=ws.max_row, column=2).number_format = "$#,##0.00"
            else:
                ws.append([item])

    _autofit_columns(ws)


def _write_anomaly_sheet(wb: Workbook, anomaly_report: dict) -> None:
    """
    Sheet: Anomalies — flattens the anomaly_engine's report (one entry
    per checked column) into a single readable table. Columns that came
    back as NOT_AVAILABLE (missing from this domain's file) are noted,
    not skipped silently, so it's clear why a column isn't in the sheet.
    """
    ws = wb.create_sheet("Anomalies")
    ws.append(["Column Checked", "Method", "Order ID", "Flagged Value"])
    _style_header_row(ws, 1, 4)

    any_rows = False
    for column, summary in anomaly_report.items():
        if not summary.get("available", True):
            ws.append([column, "—", "", summary.get("note", "Not available")])
            any_rows = True
            continue
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
    Sheet: Trend — reads the report shape produced by
    trend_analyzer.run_trend_analysis(): "overall_growth" (one dict),
    "segment_trends" (a list of per-segment dicts), and "insights"
    (plain-English sentences).
    """
    ws = wb.create_sheet("Trend")

    ws["A1"] = "Trend"
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
    domain_name: str,
    summary_rows: list,
    list_sheets: list = None,
    anomaly_report: dict = None,
    quality_report: dict = None,
    trend_report: dict = None,
    output_path: str = "InsightPilot_360_Report.xlsx",
) -> str:
    """
    Builds the full Excel workbook and saves it. This is the one function
    app.py calls, regardless of which domain is selected.

    domain_name    -> plain display name, e.g. "Finance", used in the
                       Summary sheet's title only.
    summary_rows   -> [(label, formatted_value_string), ...] — built by
                       app.py from that domain's DOMAIN_CONFIG metrics.
    list_sheets    -> [(sheet_name, columns, rows), ...] — one entry per
                       list-shaped KPI (Top Products, Reorder Flag, ...).
                       Pass an empty list (or None) for domains with none.
    anomaly_report, quality_report, trend_report -> each optional, since
                       not every domain has all three (e.g. Operations
                       has neither a trend-comparable value nor a numeric
                       column to check for anomalies).
    """
    wb = Workbook()

    _write_summary_sheet(wb, domain_name, summary_rows)

    for sheet_name, columns, rows in (list_sheets or []):
        _write_list_sheet(wb, sheet_name, columns, rows)

    if anomaly_report is not None:
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
    # root. FIXED: this used to import from the now-deleted
    # core/kpi_engine.py (left over from before the Step 1 move to
    # domains/sales.py) — updated to import from its new home, and
    # updated to build summary_rows/list_sheets the same way app.py does.
    import sys
    sys.path.append("core")
    sys.path.append("domains")
    from data_loader import load_data
    from sales import calculate_kpis
    from anomaly_engine import run_anomaly_checks
    from data_quality import run_data_quality_checks
    from trend_analyzer import run_trend_analysis

    df = load_data("sample_data/demo_sales.csv")
    kpis = calculate_kpis(df)
    anomaly_report = run_anomaly_checks(df, columns=["revenue", "quantity"], method="iqr")
    quality_report = run_data_quality_checks(df, date_column="order_date")
    trend_report = run_trend_analysis(df, date_column="order_date", value_column="revenue", segment_column="region")

    summary_rows = [
        ("Revenue", f"${kpis['revenue']:,.2f}"),
        ("Profit", f"${kpis['profit']:,.2f}"),
        ("Margin %", f"{kpis['margin_pct']}%"),
        ("Average Order Value", f"${kpis['aov']:,.2f}"),
        ("Revenue Growth (MoM)", f"{kpis['growth_pct']}%"),
    ]
    list_sheets = [
        ("Top Products", ["Product", "Revenue"], kpis["top_products"]),
        ("Top Regions", ["Region", "Revenue"], kpis["top_regions"]),
    ]

    path = export_to_excel(
        df, "Sales", summary_rows, list_sheets,
        anomaly_report=anomaly_report,
        quality_report=quality_report,
        trend_report=trend_report,
        output_path="sample_data/test_report.xlsx",
    )
    print(f"Excel report written to: {path}")