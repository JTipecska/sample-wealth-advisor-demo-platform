"""Report handler — client report status and download."""

import os

import boto3
from aws_lambda_powertools import Logger
from fastapi import HTTPException
from pydantic import BaseModel

logger = Logger()

REPORT_S3_BUCKET = os.environ.get("REPORT_S3_BUCKET", "")


class ReportStatusResponse(BaseModel):
    """Response model for client report status."""

    report_id: str | None
    status: str
    presigned_url: str | None = None
    next_best_action: str | None = None


def get_client_report(client_id: str) -> ReportStatusResponse:
    """Get latest report status and presigned download URL for a client."""
    logger.info("Fetching report for client", client_id=client_id)

    if os.environ.get("DATA_ENGINE", "redshift").lower() == "athena":
        return _get_report_athena(client_id)

    return _get_report_redshift(client_id)


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

    if report.get("status") == "complete" and report.get("s3_path"):
        try:
            s3_client = boto3.client("s3")
            presigned_url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": REPORT_S3_BUCKET, "Key": report["s3_path"]},
                ExpiresIn=3600,
            )
        except Exception as e:
            logger.error("Failed to generate presigned URL", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to generate download URL") from e

    return ReportStatusResponse(
        report_id=report.get("report_id"),
        status=report.get("status", "unknown"),
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
