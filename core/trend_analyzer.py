"""
trend_analyzer.py
------------------
Part of InsightPilot 360 (Sales MVP) — Phase 1.

This module compares sales performance across time periods (e.g. this
month vs last month) and highlights which segments (regions, products)
are growing or shrinking. It powers two things on the dashboard:

    Growth
    +8.4%

and the plain-English insight line:

    Region West down 14% MoM.

Everything here is deterministic math (Pandas groupby + % change) —
no AI or model is used to produce these numbers, matching the product
spec's trust principle: "AI explains, it never invents figures."

Author: Harsh
"""

import pandas as pd


def _prepare_period_column(df: pd.DataFrame, date_column: str, freq: str) -> pd.DataFrame:
    """
    Internal helper: adds a "period" column to a COPY of the dataframe,
    bucketing each row's date into a period (default: month).

    What it takes in:
        df          -> the full sales DataFrame
        date_column -> name of the date column (e.g. "order_date")
        freq        -> Pandas frequency string, "M" for month, "W" for
                        week, "D" for day. Default is "M" (month).

    What it gives out:
        A new DataFrame (original is untouched) with an extra "period"
        column, e.g. "2025-08" for a monthly bucket.
    """
    working_df = df.copy()
    working_df[date_column] = pd.to_datetime(working_df[date_column], errors="coerce")
    # Rows with unparseable dates are dropped here only for trend
    # calculations — data_quality.py already reports these separately,
    # so we don't want to double-report or crash on them here.
    working_df = working_df.dropna(subset=[date_column])
    working_df["period"] = working_df[date_column].dt.to_period(freq).astype(str)
    return working_df


def calculate_period_over_period_growth(
    df: pd.DataFrame,
    date_column: str = "order_date",
    value_column: str = "revenue",
    freq: str = "M",
) -> dict:
    """
    Compares the most recent period's total against the previous period's
    total (e.g. this month's revenue vs last month's revenue).

    What it takes in:
        df           -> the full sales DataFrame
        date_column  -> name of the date column
        value_column -> name of the column to sum and compare (e.g. "revenue")
        freq         -> "M" (month, default), "W" (week), or "D" (day)

    What it gives out:
        {
            "current_period": "2025-11",
            "previous_period": "2025-10",
            "current_value": 48200.0,
            "previous_value": 44500.0,
            "growth_percent": 8.4
        }
        If there isn't enough data to compare two periods (e.g. dataset
        only covers one month), growth_percent is returned as None
        rather than crashing or dividing by zero.
    """
    empty_result = {
        "current_period": None,
        "previous_period": None,
        "current_value": 0.0,
        "previous_value": 0.0,
        "growth_percent": None,
    }

    if df is None or df.empty or value_column not in df.columns:
        return empty_result

    period_df = _prepare_period_column(df, date_column, freq)
    if period_df.empty:
        return empty_result

    totals_by_period = period_df.groupby("period")[value_column].sum().sort_index()

    if len(totals_by_period) < 2:
        # Only one period of data exists — nothing to compare against
        return {
            "current_period": totals_by_period.index[-1],
            "previous_period": None,
            "current_value": round(float(totals_by_period.iloc[-1]), 2),
            "previous_value": 0.0,
            "growth_percent": None,
        }

    current_period = totals_by_period.index[-1]
    previous_period = totals_by_period.index[-2]
    current_value = float(totals_by_period.iloc[-1])
    previous_value = float(totals_by_period.iloc[-2])

    if previous_value == 0:
        growth_percent = None  # avoid divide-by-zero
    else:
        growth_percent = round(((current_value - previous_value) / previous_value) * 100, 2)

    return {
        "current_period": current_period,
        "previous_period": previous_period,
        "current_value": round(current_value, 2),
        "previous_value": round(previous_value, 2),
        "growth_percent": growth_percent,
    }


def calculate_segment_trends(
    df: pd.DataFrame,
    date_column: str = "order_date",
    value_column: str = "revenue",
    segment_column: str = "region",
    freq: str = "M",
) -> list:
    """
    Compares each segment (e.g. each region, or each product) between
    the current and previous period, so we can spot which ones are
    growing and which are shrinking.

    What it takes in:
        df             -> the full sales DataFrame
        date_column    -> name of the date column
        value_column   -> column to sum (e.g. "revenue")
        segment_column -> column to group by (e.g. "region" or "product")
        freq           -> "M" (month, default), "W", or "D"

    What it gives out:
        A list of dicts, one per segment, sorted worst-growth-first
        (so the biggest drops show up on top — useful for flagging
        problems):
        [
            {"segment": "West", "current_value": 8200.0, "previous_value": 9500.0, "growth_percent": -13.68},
            {"segment": "North", "current_value": 15000.0, "previous_value": 12000.0, "growth_percent": 25.0},
            ...
        ]
        A segment with no data in the previous period gets
        growth_percent = None (can't compute % change from zero).
    """
    if df is None or df.empty or value_column not in df.columns or segment_column not in df.columns:
        return []

    period_df = _prepare_period_column(df, date_column, freq)
    if period_df.empty:
        return []

    all_periods = sorted(period_df["period"].unique())
    if len(all_periods) < 2:
        return []  # need at least 2 periods to compute a trend

    current_period = all_periods[-1]
    previous_period = all_periods[-2]

    current_totals = (
        period_df[period_df["period"] == current_period]
        .groupby(segment_column)[value_column]
        .sum()
    )
    previous_totals = (
        period_df[period_df["period"] == previous_period]
        .groupby(segment_column)[value_column]
        .sum()
    )

    all_segments = set(current_totals.index) | set(previous_totals.index)
    results = []

    for segment in all_segments:
        current_value = float(current_totals.get(segment, 0.0))
        previous_value = float(previous_totals.get(segment, 0.0))

        if previous_value == 0:
            growth_percent = None
        else:
            growth_percent = round(((current_value - previous_value) / previous_value) * 100, 2)

        results.append({
            "segment": segment,
            "current_value": round(current_value, 2),
            "previous_value": round(previous_value, 2),
            "growth_percent": growth_percent,
        })

    # Worst performers first (None/no-comparison segments go last)
    results.sort(key=lambda r: (r["growth_percent"] is None, r["growth_percent"]))
    return results


def generate_trend_insights(segment_trends: list, top_n: int = 1) -> list:
    """
    Turns segment_trends (from calculate_segment_trends) into short,
    plain-English sentences for the dashboard's "Insights" panel —
    matching the wireframe style: "Region West down 14% MoM."

    What it takes in:
        segment_trends -> the list returned by calculate_segment_trends()
        top_n           -> how many biggest drops AND biggest gains to
                            turn into sentences (default 1 of each)

    What it gives out:
        A list of strings, e.g.:
        ["Region West down 13.7% MoM.", "Region North up 25.0% MoM."]
        Segments with growth_percent = None are ignored (nothing
        meaningful to say about them).
    """
    valid_trends = [t for t in segment_trends if t["growth_percent"] is not None]
    if not valid_trends:
        return []

    sorted_by_growth = sorted(valid_trends, key=lambda t: t["growth_percent"])
    biggest_drops = sorted_by_growth[:top_n]
    biggest_gains = sorted_by_growth[-top_n:] if len(sorted_by_growth) > top_n else []

    insights = []
    for trend in biggest_drops:
        if trend["growth_percent"] < 0:
            insights.append(
                f"{trend['segment']} down {abs(trend['growth_percent'])}% MoM."
            )
    for trend in biggest_gains:
        if trend["growth_percent"] > 0:
            insights.append(
                f"{trend['segment']} up {trend['growth_percent']}% MoM."
            )

    return insights


def run_trend_analysis(
    df: pd.DataFrame,
    date_column: str = "order_date",
    value_column: str = "revenue",
    segment_column: str = "region",
    freq: str = "M",
) -> dict:
    """
    Main entry point — runs the overall growth calculation, the
    per-segment breakdown, and the plain-English insights together.
    This is the function app.py / the Streamlit dashboard should call
    directly.

    What it takes in:
        df             -> the full sales DataFrame
        date_column    -> name of the date column (default "order_date")
        value_column   -> column to analyze (default "revenue")
        segment_column -> column to break down by (default "region")
        freq           -> "M" (month, default), "W", or "D"

    What it gives out:
        {
            "overall_growth": {...},     # output of calculate_period_over_period_growth()
            "segment_trends": [...],     # output of calculate_segment_trends()
            "insights": [...]            # output of generate_trend_insights()
        }
        app.py can plug "overall_growth.growth_percent" straight into
        the "Growth" KPI card, and "insights" straight into the
        Insights panel.
    """
    overall_growth = calculate_period_over_period_growth(
        df, date_column=date_column, value_column=value_column, freq=freq
    )
    segment_trends = calculate_segment_trends(
        df, date_column=date_column, value_column=value_column,
        segment_column=segment_column, freq=freq,
    )
    insights = generate_trend_insights(segment_trends)

    return {
        "overall_growth": overall_growth,
        "segment_trends": segment_trends,
        "insights": insights,
    }


if __name__ == "__main__":
    # Quick manual test using the demo dataset — run this file directly
    # with: python core/trend_analyzer.py
    sample_df = pd.read_csv("sample_data/demo_sales.csv")
    result = run_trend_analysis(sample_df, date_column="order_date", value_column="revenue", segment_column="region")
    print("Overall growth:", result["overall_growth"])
    print("Segment trends:", result["segment_trends"])
    print("Insights:", result["insights"])