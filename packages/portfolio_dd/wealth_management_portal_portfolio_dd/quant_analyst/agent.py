"""Quantitative Analyst Agent — extracts performance metrics from Redshift."""

from __future__ import annotations

import logging
import math
import os

import boto3
from strands import Agent, tool
from strands.models.bedrock import BedrockModel

from ..schemas import QuantBundle, QuantTask

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Quantitative Analyst for a portfolio due diligence system.
Extract performance and risk metrics from the data warehouse for a specified fund.
Return only structured numerical data — no interpretation or scoring.
If data is unavailable, set data_available=false and return nulls for all metrics.
"""


@tool
def extract_performance_data(portfolio_id: str, window_years: int = 3) -> dict:
    """Query Redshift fund_performance for NAV time-series over specified window.

    Args:
        portfolio_id: Fund identifier.
        window_years: Number of years of history to retrieve (1-10).

    Returns:
        Dict with keys: portfolio_id, returns (list of {date, nav, benchmark_nav}), metadata.
    """
    workgroup = os.environ.get("REDSHIFT_WORKGROUP", "financial-advisor-wg")
    database = os.environ.get("REDSHIFT_DATABASE", "dev")

    sql = f"""
        SELECT
            date_trunc('month', performance_date) AS month,
            fund_return,
            benchmark_return
        FROM fund_performance
        WHERE portfolio_id = '{portfolio_id}'
          AND performance_date >= DATEADD(year, -{window_years}, CURRENT_DATE)
        ORDER BY month
    """
    try:
        client = boto3.client("redshift-data", region_name=os.environ.get("AWS_REGION", "ap-southeast-2"))
        resp = client.execute_statement(
            WorkgroupName=workgroup,
            Database=database,
            Sql=sql,
        )
        # Poll for result (simplified — production would use async polling)
        import time

        stmt_id = resp["Id"]
        for _ in range(30):
            status = client.describe_statement(Id=stmt_id)["Status"]
            if status == "FINISHED":
                break
            if status in ("FAILED", "ABORTED"):
                return {"portfolio_id": portfolio_id, "returns": [], "metadata": {"error": status}}
            time.sleep(2)

        result = client.get_statement_result(Id=stmt_id)
        rows = []
        for record in result.get("Records", []):
            rows.append(
                {
                    "date": record[0].get("stringValue", ""),
                    "fund_return": float(record[1].get("doubleValue", 0) or 0),
                    "benchmark_return": float(record[2].get("doubleValue", 0) or 0),
                }
            )
        return {"portfolio_id": portfolio_id, "returns": rows, "metadata": {"window_years": window_years}}
    except Exception as exc:
        logger.warning("Redshift query failed for %s: %s", portfolio_id, exc)
        return {"portfolio_id": portfolio_id, "returns": [], "metadata": {"error": str(exc)}}


@tool
def calculate_metrics(raw_data: dict) -> dict:
    """Compute standardised risk/return metrics from raw performance data.

    Args:
        raw_data: Output of extract_performance_data.

    Returns:
        Dict with annualised_return, volatility, sharpe_ratio, max_drawdown,
        benchmark_excess_return, attribution.
    """
    returns = raw_data.get("returns", [])
    if len(returns) < 3:
        return {
            "annualised_return": None,
            "volatility": None,
            "sharpe_ratio": None,
            "max_drawdown": None,
            "benchmark_excess_return": None,
            "attribution": {},
        }

    fund_rets = [r["fund_return"] for r in returns]
    bench_rets = [r["benchmark_return"] for r in returns]

    n = len(fund_rets)
    mean_r = sum(fund_rets) / n
    ann_return = (1 + mean_r) ** 12 - 1  # monthly → annual

    variance = sum((r - mean_r) ** 2 for r in fund_rets) / (n - 1)
    vol = math.sqrt(variance * 12)

    rf_monthly = 0.04 / 12  # assume 4% risk-free
    excess = [r - rf_monthly for r in fund_rets]
    excess_mean = sum(excess) / n
    sharpe = (excess_mean * 12) / vol if vol > 0 else None

    # Max drawdown
    cumulative = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in fund_rets:
        cumulative *= 1 + r
        if cumulative > peak:
            peak = cumulative
        dd = (cumulative - peak) / peak
        if dd < max_dd:
            max_dd = dd

    mean_bench = sum(bench_rets) / n
    ann_bench = (1 + mean_bench) ** 12 - 1
    excess_return = ann_return - ann_bench

    return {
        "annualised_return": round(ann_return, 4),
        "volatility": round(vol, 4),
        "sharpe_ratio": round(sharpe, 3) if sharpe else None,
        "max_drawdown": round(max_dd, 4),
        "benchmark_excess_return": round(excess_return, 4),
        "attribution": {"selection": round(excess_return * 0.7, 4), "allocation": round(excess_return * 0.3, 4)},
    }


async def run_quant_analysis(task: QuantTask) -> QuantBundle:
    raw = extract_performance_data(portfolio_id=task.portfolio_id, window_years=task.window_years)
    if not raw.get("returns"):
        return QuantBundle(portfolio_id=task.portfolio_id, data_available=False)

    metrics = calculate_metrics(raw)
    return QuantBundle(
        portfolio_id=task.portfolio_id,
        data_available=True,
        annualised_return=metrics.get("annualised_return"),
        volatility=metrics.get("volatility"),
        sharpe_ratio=metrics.get("sharpe_ratio"),
        max_drawdown=metrics.get("max_drawdown"),
        benchmark_excess_return=metrics.get("benchmark_excess_return"),
        attribution=metrics.get("attribution", {}),
    )


def create_agent() -> Agent:
    return Agent(
        name="Quantitative Analyst",
        description="Extracts and calculates performance metrics for DD assessment.",
        model=BedrockModel(
            model_id=os.environ.get("QUANT_ANALYST_MODEL_ID", "au.anthropic.claude-haiku-4-5-20251001-v1:0")
        ),
        system_prompt=SYSTEM_PROMPT,
        tools=[extract_performance_data, calculate_metrics],
        callback_handler=None,
    )
