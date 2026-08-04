"""Report handler — client report status, download, and on-demand generation."""

import json
import os
import uuid

import boto3
from aws_lambda_powertools import Logger
from fastapi import HTTPException
from pydantic import BaseModel

logger = Logger()

REPORT_S3_BUCKET = os.environ.get("REPORT_S3_BUCKET", "")
REPORT_AGENT_ARN = os.environ.get("REPORT_AGENT_ARN", "")


class ReportStatusResponse(BaseModel):
    """Response model for client report status."""

    report_id: str | None
    status: str
    presigned_url: str | None = None
    next_best_action: str | None = None


class ReportsSummaryResponse(BaseModel):
    """Summary of which clients have reports available."""

    clients_with_reports: list[str]


def get_reports_summary() -> ReportsSummaryResponse:
    """Return list of client IDs that have completed reports."""
    logger.info("Fetching reports summary")

    if os.environ.get("DATA_ENGINE", "athena").lower() == "athena":
        return _get_reports_summary_athena()

    return _get_reports_summary_redshift()


def _get_reports_summary_athena() -> ReportsSummaryResponse:
    from wealth_management_portal_portfolio_data_access.repositories.data_api_base_repository import (
        DataApiBaseRepository,
    )

    repo = DataApiBaseRepository()
    sql = """
        SELECT DISTINCT client_id
        FROM client_reports
        WHERE status = 'complete' AND s3_path IS NOT NULL AND s3_path != ''
    """
    results = repo._execute_and_wait(sql)
    client_ids = [r["client_id"] for r in results] if results else []
    return ReportsSummaryResponse(clients_with_reports=client_ids)


def _get_reports_summary_redshift() -> ReportsSummaryResponse:
    from wealth_management_portal_portfolio_data_access.engine import iam_connection_factory

    factory = iam_connection_factory()
    with factory() as conn:
        cursor = conn.execute(
            "SELECT DISTINCT client_id FROM public.client_reports WHERE status = 'complete' AND s3_path IS NOT NULL"
        )
        client_ids = [row[0] for row in cursor.fetchall()]
    return ReportsSummaryResponse(clients_with_reports=client_ids)


def get_client_report(client_id: str) -> ReportStatusResponse:
    """Get latest report status and presigned download URL for a client."""
    logger.info("Fetching report for client", client_id=client_id)

    if os.environ.get("DATA_ENGINE", "athena").lower() == "athena":
        return _get_report_athena(client_id)

    return _get_report_redshift(client_id)


def generate_client_report(client_id: str) -> ReportStatusResponse:
    """Trigger on-demand report generation via the Report Agent."""
    logger.info("Generating report for client", client_id=client_id)

    if not REPORT_AGENT_ARN:
        logger.warning("REPORT_AGENT_ARN not configured")
        return ReportStatusResponse(
            report_id=None,
            status="error",
            next_best_action="Report generation not configured",
        )

    try:
        agentcore = boto3.client("bedrock-agentcore")
        session_id = f"report-{uuid.uuid4().hex}"

        response = agentcore.invoke_agent_runtime(
            agentRuntimeArn=REPORT_AGENT_ARN,
            input=json.dumps({"client_id": client_id}),
            runtimeSessionId=session_id,
        )
        result_body = response["response"].read()
        result = json.loads(result_body)

        report_id = result.get("report_id", f"RPT-{uuid.uuid4().hex[:10].upper()}")
        s3_path = result.get("s3_path", "")
        next_best_action = result.get("next_best_action", "")

        if s3_path and os.environ.get("DATA_ENGINE", "athena").lower() == "athena":
            _save_report_to_athena(report_id, client_id, s3_path, next_best_action)

        presigned_url = None
        if s3_path and REPORT_S3_BUCKET:
            s3_client = boto3.client("s3")
            presigned_url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": REPORT_S3_BUCKET, "Key": s3_path},
                ExpiresIn=3600,
            )

        return ReportStatusResponse(
            report_id=report_id,
            status="complete",
            presigned_url=presigned_url,
            next_best_action=next_best_action,
        )

    except Exception as e:
        logger.exception("Error generating report", client_id=client_id)
        return ReportStatusResponse(
            report_id=None,
            status="error",
            next_best_action=f"Generation failed: {str(e)[:100]}",
        )


def _save_report_to_athena(report_id: str, client_id: str, s3_path: str, next_best_action: str):
    """Write report record to S3 Tables via Athena INSERT INTO."""
    from wealth_management_portal_portfolio_data_access.repositories.data_api_base_repository import (
        DataApiBaseRepository,
    )

    repo = DataApiBaseRepository()
    safe_nba = next_best_action.replace("'", "''")[:500] if next_best_action else ""
    sql = f"""
        INSERT INTO client_reports (report_id, client_id, s3_path, status, generated_date, next_best_action)
        VALUES ('{report_id}', '{client_id}', '{s3_path}', 'complete', current_timestamp, '{safe_nba}')
    """
    try:
        repo._execute_and_wait(sql)
    except Exception:
        logger.warning("Failed to save report to Athena", exc_info=True)


def _get_report_athena(client_id: str) -> ReportStatusResponse:
    """Fetch report status via Athena (S3 Tables)."""
    from wealth_management_portal_portfolio_data_access.repositories.data_api_base_repository import (
        DataApiBaseRepository,
    )

    repo = DataApiBaseRepository()
    sql = """
        SELECT report_id, client_id, s3_path, status, next_best_action,
               CAST(generated_date AS varchar) AS generated_date
        FROM client_reports
        WHERE client_id = :client_id
        ORDER BY generated_date DESC
        LIMIT 1
    """
    results = repo._execute_and_wait(sql, [{"name": "client_id", "value": client_id}])

    if not results:
        return ReportStatusResponse(report_id=None, status="not_found")

    report = results[0]
    presigned_url = None

    if report.get("status") == "complete" and report.get("s3_path") and REPORT_S3_BUCKET:
        try:
            s3_client = boto3.client("s3")
            s3_client.head_object(Bucket=REPORT_S3_BUCKET, Key=report["s3_path"])
            presigned_url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": REPORT_S3_BUCKET, "Key": report["s3_path"]},
                ExpiresIn=3600,
            )
        except s3_client.exceptions.NoSuchKey:
            logger.info("Report file not found in S3", s3_path=report["s3_path"])
        except Exception as e:
            if "404" in str(e) or "Not Found" in str(e):
                logger.info("Report file not found in S3", s3_path=report["s3_path"])
            else:
                logger.error("Failed to generate presigned URL", error=str(e))
                raise HTTPException(status_code=500, detail="Failed to generate download URL") from e

    effective_status = report.get("status", "unknown")
    if effective_status == "complete" and presigned_url is None:
        effective_status = "file_missing"

    return ReportStatusResponse(
        report_id=report.get("report_id"),
        status=effective_status,
        presigned_url=presigned_url,
        next_best_action=report.get("next_best_action"),
    )


def _get_report_redshift(client_id: str) -> ReportStatusResponse:
    """Fetch report status via direct Redshift connection."""
    from wealth_management_portal_portfolio_data_access.engine import iam_connection_factory
    from wealth_management_portal_portfolio_data_access.repositories.report_repository import (
        ReportRepository,
    )

    repo = ReportRepository(iam_connection_factory())
    report = repo.get_latest_by_client(client_id)

    if not report:
        return ReportStatusResponse(report_id=None, status="not_found")

    presigned_url = None
    if report.status == "complete" and report.s3_path:
        try:
            s3_client = boto3.client("s3")
            presigned_url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": REPORT_S3_BUCKET, "Key": report.s3_path},
                ExpiresIn=3600,
            )
        except Exception as e:
            logger.error("Failed to generate presigned URL", report_id=report.report_id, error=str(e))
            raise HTTPException(status_code=500, detail="Failed to generate download URL") from e

    return ReportStatusResponse(
        report_id=report.report_id,
        status=report.status,
        presigned_url=presigned_url,
        next_best_action=report.next_best_action,
    )
