"""Portfolio Due Diligence REST API with SSE streaming."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncGenerator
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..common.a2a_client import get_agent_endpoint, invoke_agent
from ..models import DDReport, DDSession, DDStatus
from ..schemas import DDProgressEvent, DDRequest
from ..seed_data import MANAGER_BY_PORTFOLIO, SAMPLE_PORTFOLIOS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Portfolio DD API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# In-memory session store (DynamoDB in prod)
_sessions: dict[str, DDSession] = {}
_reports: dict[str, DDReport] = {}
_progress_queues: dict[str, asyncio.Queue] = {}
_hitl_flags: dict[str, dict[str, dict]] = {}  # session_id → flag_id → flag


# ── Request/Response models ────────────────────────────────────────────────────


class StartReviewRequest(BaseModel):
    portfolio_id: str
    initiated_by: str = "system"
    criteria_ids: list[str] = []


class StartReviewResponse(BaseModel):
    session_id: str
    portfolio_id: str
    portfolio_name: str
    status: str


class SessionStatusResponse(BaseModel):
    session_id: str
    portfolio_id: str
    portfolio_name: str
    status: str
    started_at: str
    completed_at: str | None
    overall_score: float | None = None
    recommendation: str | None = None
    hitl_required: bool = False


class HITLResolveRequest(BaseModel):
    resolution: str  # "approved" | "rejected" | "escalated"
    reviewer_notes: str = ""
    reviewer: str = ""


# ── Helpers ────────────────────────────────────────────────────────────────────


def _emit(session_id: str, event: DDProgressEvent) -> None:
    q = _progress_queues.get(session_id)
    if q:
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait(event)


async def _run_pipeline(session: DDSession) -> None:
    """Background task — drives the supervisor and emits SSE progress events."""
    session_id = session.session_id

    _emit(
        session_id,
        DDProgressEvent(
            session_id=session_id,
            event_type="pipeline_started",
            message=f"Starting due diligence for {session.portfolio_name}",
        ),
    )

    mgr_name = session.manager_name

    request = DDRequest(
        session_id=session_id,
        portfolio_id=session.portfolio_id,
        portfolio_name=session.portfolio_name,
        manager_name=mgr_name,
        criteria_ids=getattr(session, "criteria_ids", []),
    )

    try:
        ep = get_agent_endpoint("supervisor")
        result = await invoke_agent(ep, request.model_dump_json())
        # supervisor returns DDAgentResult; extract the nested report dict
        report_data = result.get("report", result) if isinstance(result, dict) else result
        report = DDReport.model_validate(report_data)

        _reports[session_id] = report
        session.status = DDStatus.COMPLETE
        session.completed_at = datetime.utcnow()

        # Build HITL flags if required
        if report.hitl_required:
            flags: dict[str, dict] = {}
            for reason in report.hitl_reasons:
                flag_id = f"flag_{uuid4().hex[:8]}"
                flags[flag_id] = {
                    "flag_id": flag_id,
                    "reason": reason,
                    "status": "pending",
                    "resolved_at": None,
                    "reviewer_notes": "",
                }
                _emit(
                    session_id,
                    DDProgressEvent(
                        session_id=session_id,
                        event_type="hitl_flag",
                        message=reason,
                        data={"flag_id": flag_id},
                    ),
                )
            _hitl_flags[session_id] = flags

        _emit(
            session_id,
            DDProgressEvent(
                session_id=session_id,
                event_type="report_ready",
                message="Due diligence report is ready.",
                score=report.overall_score,
                data={
                    "recommendation": report.recommendation,
                    "overall_rag": report.overall_rag,
                    "hitl_required": report.hitl_required,
                },
            ),
        )

    except Exception as exc:
        logger.error("Pipeline failed for session %s: %s", session_id, exc)
        session.status = DDStatus.FAILED
        _emit(
            session_id,
            DDProgressEvent(
                session_id=session_id,
                event_type="error",
                message=str(exc),
            ),
        )
    finally:
        # Sentinel to close SSE stream
        q = _progress_queues.get(session_id)
        if q:
            await q.put(None)


# ── Endpoints ──────────────────────────────────────────────────────────────────


@app.get("/ping")
def ping():
    return {"status": "ok", "service": "portfolio-dd-api"}


@app.post("/dd/sessions", response_model=StartReviewResponse)
async def start_review(req: StartReviewRequest):
    """Kick off a new DD session for a portfolio."""
    pf_data = next((p for p in SAMPLE_PORTFOLIOS if p["portfolio_id"] == req.portfolio_id), None)
    if not pf_data:
        raise HTTPException(status_code=404, detail=f"Portfolio {req.portfolio_id} not found")

    pf_name = pf_data.get("name", req.portfolio_id)
    mgr_data = MANAGER_BY_PORTFOLIO.get(req.portfolio_id, {})
    mgr_name = mgr_data.get("name", "Unknown Manager")

    session = DDSession(
        portfolio_id=req.portfolio_id,
        portfolio_name=pf_name,
        manager_name=mgr_name,
        initiated_by=req.initiated_by,
        status=DDStatus.IN_PROGRESS,
    )
    _sessions[session.session_id] = session
    _progress_queues[session.session_id] = asyncio.Queue(maxsize=200)

    asyncio.create_task(_run_pipeline(session))

    return StartReviewResponse(
        session_id=session.session_id,
        portfolio_id=session.portfolio_id,
        portfolio_name=session.portfolio_name,
        status=session.status,
    )


@app.get("/dd/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session(session_id: str):
    """Return status and summary for a DD session."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    report = _reports.get(session_id)
    return SessionStatusResponse(
        session_id=session.session_id,
        portfolio_id=session.portfolio_id,
        portfolio_name=session.portfolio_name,
        status=session.status,
        started_at=session.started_at.isoformat(),
        completed_at=session.completed_at.isoformat() if session.completed_at else None,
        overall_score=report.overall_score if report else None,
        recommendation=report.recommendation if report else None,
        hitl_required=report.hitl_required if report else False,
    )


@app.get("/dd/sessions/{session_id}/stream")
async def stream_progress(session_id: str):
    """SSE stream for live pipeline progress."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    queue = _progress_queues.get(session_id)
    if queue is None:
        raise HTTPException(status_code=410, detail="Stream no longer available")

    async def event_generator() -> AsyncGenerator[str, None]:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue

            if event is None:  # sentinel — pipeline done
                yield "event: done\ndata: {}\n\n"
                break

            yield f"event: {event.event_type}\ndata: {event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/dd/sessions/{session_id}/report")
async def get_report(session_id: str):
    """Return the completed DD report."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    report = _reports.get(session_id)
    if not report:
        session = _sessions[session_id]
        if session.status == DDStatus.IN_PROGRESS:
            raise HTTPException(status_code=202, detail="Report not yet ready")
        raise HTTPException(status_code=404, detail="Report not found")

    return report.model_dump()


@app.get("/dd/sessions/{session_id}/hitl")
async def list_hitl_flags(session_id: str):
    """List all HITL flags for a session."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"flags": list(_hitl_flags.get(session_id, {}).values())}


@app.post("/dd/sessions/{session_id}/hitl/{flag_id}/resolve")
async def resolve_hitl_flag(session_id: str, flag_id: str, req: HITLResolveRequest):
    """Record a human reviewer's decision on a HITL flag."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    flags = _hitl_flags.get(session_id)
    if not flags or flag_id not in flags:
        raise HTTPException(status_code=404, detail="Flag not found")

    valid_resolutions = {"approved", "rejected", "escalated"}
    if req.resolution not in valid_resolutions:
        raise HTTPException(status_code=400, detail=f"resolution must be one of {valid_resolutions}")

    flag = flags[flag_id]
    flag["status"] = req.resolution
    flag["resolved_at"] = datetime.utcnow().isoformat()
    flag["reviewer_notes"] = req.reviewer_notes
    flag["reviewer"] = req.reviewer

    return {"flag_id": flag_id, "status": req.resolution, "message": "Resolution recorded"}


@app.get("/dd/portfolios")
async def list_portfolios():
    """Return the list of sample portfolios available for DD."""
    return {"portfolios": SAMPLE_PORTFOLIOS}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8092)))
