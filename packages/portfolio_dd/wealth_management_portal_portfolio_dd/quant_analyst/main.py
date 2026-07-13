"""FastAPI entry point for Quantitative Analyst agent."""
from __future__ import annotations
import logging, os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from ..schemas import QuantBundle, QuantTask
from .agent import run_quant_analysis

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Quantitative Analyst Agent", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/ping")
def ping():
    return {"status": "ok", "agent": "quant-analyst"}

@app.post("/invocations")
async def invocations(task: QuantTask) -> QuantBundle:
    try:
        return await run_quant_analysis(task)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8089)))
