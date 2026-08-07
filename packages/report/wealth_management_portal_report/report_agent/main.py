import logging
import os
import time
import uuid

import boto3
import uvicorn
from bedrock_agentcore.runtime.models import PingStatus
from fastapi import HTTPException
from pydantic import BaseModel

from .init import app
from .tools import fetch_report_data, generate_next_best_action

logger = logging.getLogger(__name__)


class InvokeInput(BaseModel):
    client_id: str


@app.post("/invocations")
async def invoke(input: InvokeInput) -> dict:
    """Entry point for synchronous report generation"""
    t_start = time.time()
    import sys

    print(f"[REPORT-AGENT] /invocations called: client_id={input.client_id}", file=sys.stderr, flush=True)
    try:
        logger.info("Request received: client_id=%s", input.client_id)

        # Generate report ID
        report_id = f"RPT-{uuid.uuid4().hex[:10].upper()}"

        # Fetch report data directly via Athena (no MCP Gateway — avoids 120s timeout)
        logger.info("fetch_report_data started: client_id=%s", input.client_id)
        report_data = fetch_report_data(input.client_id)
        logger.info("fetch_report_data completed: keys=%s", list(report_data.components.keys()))

        # Generate Next Best Action via a direct Bedrock call
        next_best_action = None
        try:
            next_best_action = generate_next_best_action(report_data)
            logger.info("NBA generated: length=%d", len(next_best_action) if next_best_action else 0)
        except Exception:
            logger.exception("NBA generation failed; continuing without NBA")

        # Generate narratives via Bedrock Converse tool use (lazy imports to avoid slow startup)
        from .agent import assemble_markdown, invoke_narrative_generator

        logger.info("Narrative generation started")
        narratives = invoke_narrative_generator(report_data.components)
        logger.info("Narrative generation completed: sections=%d", len(narratives))
        markdown = assemble_markdown(report_data.components["deterministic_sections"], narratives)
        logger.info("Markdown assembled: length=%d", len(markdown))

        # Convert markdown to PDF (lazy import — WeasyPrint is heavy)
        from ..pdf import html_to_pdf, markdown_to_html

        logger.info("PDF generation started")
        html = markdown_to_html(markdown, report_data.components["chart_svgs"])
        pdf_bytes = html_to_pdf(html)
        logger.info("PDF generation completed: pdf_size_bytes=%d", len(pdf_bytes))

        # Upload PDF to S3
        s3_client = boto3.client("s3")
        bucket_name = os.environ["REPORT_S3_BUCKET"]
        s3_key = f"reports/{input.client_id}/{report_id}.pdf"

        logger.info("S3 upload started: s3_path=%s", s3_key)
        s3_client.put_object(Bucket=bucket_name, Key=s3_key, Body=pdf_bytes, ContentType="application/pdf")
        logger.info("S3 upload completed: s3_path=%s", s3_key)

        # Save report record directly to Athena
        logger.info("save_report started: report_id=%s", report_id)
        from wealth_management_portal_portfolio_data_access.repositories.data_api_base_repository import (
            DataApiBaseRepository,
        )

        _repo = DataApiBaseRepository()
        _nba = (next_best_action or "").replace("'", "''")[:500]
        _repo._execute_and_wait(
            f"INSERT INTO client_reports (report_id, client_id, s3_path, status, generated_date, next_best_action) "
            f"VALUES ('{report_id}', '{input.client_id}', '{s3_key}', 'complete', current_timestamp, '{_nba}')"
        )
        logger.info("save_report completed: report_id=%s", report_id)

        duration = time.time() - t_start
        logger.info(
            "Report generation succeeded: client_id=%s report_id=%s duration=%.2fs",
            input.client_id,
            report_id,
            duration,
        )
        return {"report_id": report_id, "s3_path": s3_key, "status": "complete"}

    except Exception as e:
        logger.exception("Report generation failed for %s", input.client_id)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/ping")
def ping() -> str:
    return PingStatus.HEALTHY


if __name__ == "__main__":
    uvicorn.run("wealth_management_portal_report.report_agent.main:app", host="0.0.0.0", port=8080)
