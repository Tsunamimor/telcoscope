"""Send incident notifications to a configurable webhook."""
from __future__ import annotations

import os
from typing import Any

import httpx
from loguru import logger

_WEBHOOK_URL = os.getenv("INCIDENT_WEBHOOK_URL")


def notify(incident: dict[str, Any]) -> bool:
    """POST an incident to the configured webhook. Returns True on success.

    If no webhook URL is set (common in CI and local dev), skip silently
    and return False — the caller can treat that as 'not yet notified'
    and the row stays available for re-notification once a URL is set.
    """
    if not _WEBHOOK_URL:
        logger.debug("notifier.skipped (no INCIDENT_WEBHOOK_URL)")
        return False

    payload = {
        "incident_id":     str(incident["incident_id"]),
        "cell_id":         incident["cell_id"],
        "severity":        incident["severity"],
        "ts_start":        incident["ts_start"].isoformat(),
        "ts_end":          incident["ts_end"].isoformat(),
        "detection_count": incident["detection_count"],
        "methods":         incident["methods"],
        "dominant_kpi":    incident.get("dominant_kpi"),
    }

    try:
        resp = httpx.post(_WEBHOOK_URL, json=payload, timeout=5.0)
        resp.raise_for_status()
        logger.info("notifier.sent incident_id={}", payload["incident_id"])
        return True
    except Exception as e:
        logger.warning("notifier.failed incident_id={} error={}", payload["incident_id"], e)
        return False