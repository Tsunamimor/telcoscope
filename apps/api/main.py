"""telcoscope HTTP API — programmatic access to incidents and anomalies.

Run locally:

    uvicorn apps.api.main:app --reload --port 8000

Endpoints (v0):
    GET  /health              health probe
    GET  /version             package version
    GET  /incidents/{uid}     incident detail (stub)
    GET  /anomalies?since=... list recent anomalies (stub)

Full implementation lands in Week 5–6.
"""
from __future__ import annotations

from fastapi import FastAPI

from telcoscope import __version__

app = FastAPI(
    title="telcoscope",
    version=__version__,
    description="3GPP KPI observability and RCA for mobile networks.",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    """Return the running package version."""
    return {"version": __version__}


@app.get("/incidents/{incident_uid}")
def get_incident(incident_uid: int) -> dict:
    """Return the full incident record (stub)."""
    return {
        "incident_uid": incident_uid,
        "status": "not_yet_implemented",
        "todo": "Wire up to analytics.incidents in Week 5",
    }


@app.get("/anomalies")
def list_anomalies(since: str | None = None, limit: int = 50) -> dict:
    """List recent anomalies (stub)."""
    return {
        "since": since,
        "limit": limit,
        "items": [],
        "todo": "Wire up to analytics.anomalies in Week 5",
    }
