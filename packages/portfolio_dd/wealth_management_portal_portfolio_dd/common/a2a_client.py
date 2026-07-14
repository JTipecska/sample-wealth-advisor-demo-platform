"""A2A client — calls agent endpoints, falling back to localhost in dev."""

from __future__ import annotations

import os
from typing import Any

import httpx

_LOCAL_PORTS: dict[str, int] = {
    "dd-supervisor": 8086,
    "evidence-gatherer": 8087,
    "framework-assessor": 8088,
    "quant-analyst": 8089,
    "report-drafter": 8090,
    "qa-agent": 8091,
}

_ENV_KEYS: dict[str, str] = {
    "dd-supervisor": "DD_SUPERVISOR_ENDPOINT",
    "evidence-gatherer": "EVIDENCE_GATHERER_ENDPOINT",
    "framework-assessor": "FRAMEWORK_ASSESSOR_ENDPOINT",
    "quant-analyst": "QUANT_ANALYST_ENDPOINT",
    "report-drafter": "REPORT_DRAFTER_ENDPOINT",
    "qa-agent": "QA_AGENT_ENDPOINT",
}


def get_agent_endpoint(agent_name: str) -> str:
    env_key = _ENV_KEYS.get(agent_name)
    if env_key:
        override = os.environ.get(env_key)
        if override:
            return override
    port = _LOCAL_PORTS[agent_name]
    return f"http://localhost:{port}"


async def invoke_agent(endpoint: str, payload_json: str, timeout: float = 120.0) -> Any:
    """POST payload to agent /invocations, return parsed JSON."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{endpoint}/invocations",
            content=payload_json,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()
