"""Privacy-preserving access to process-global performance diagnostics."""

import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Response

from app import config
from app.core.deps import get_current_user
from app.services.performance_monitor import get_performance_monitor


router = APIRouter(prefix="/agents/performance", tags=["agents"])


def _is_oidc_user(current_user) -> bool:
    return (
        config.AUTH_PROVIDER == "oidc"
        or str(getattr(current_user, "provider", "")).strip().lower() == "oidc"
    )


def require_performance_metrics_access(current_user) -> None:
    """Allow only a local singleton or a verified OIDC organization admin."""

    role = str(getattr(current_user, "organization_role", "")).strip().lower()
    if _is_oidc_user(current_user) and role == "admin":
        return
    if (
        config.AUTH_PROVIDER == "local"
        and str(getattr(current_user, "provider", "")).strip().lower() == "local"
    ):
        return
    raise HTTPException(
        status_code=403,
        detail="Performance diagnostics are unavailable for this account",
    )


@router.get("/report")
async def get_performance_report(current_user=Depends(get_current_user)):
    """Return aggregate process metrics without per-user diagnostic details."""

    require_performance_metrics_access(current_user)
    monitor = get_performance_monitor()
    try:
        summary = monitor.get_performance_summary(last_n_files=50)
        if "error" in summary:
            return {"available": False, "message": summary["error"]}
        # Errors can contain filenames, paths, and provider text. Every auth
        # mode receives aggregate diagnostics only because these metrics are
        # process-global and may cover more than the requesting user.
        summary = dict(summary)
        summary.pop("recent_errors", None)
        return {
            "available": True,
            "user_id": current_user.id,
            "performance_data": summary,
            "report_generated_at": time.time(),
        }
    except Exception:
        logging.exception("Failed to generate performance report")
        return {"available": False, "error": "Failed to generate performance report"}


@router.post("/export")
async def export_performance_metrics(current_user=Depends(get_current_user)):
    """Download aggregate metrics without a cross-user server-side artifact."""

    require_performance_metrics_access(current_user)
    try:
        monitor = get_performance_monitor()
        summary = dict(monitor.get_performance_summary(last_n_files=1000))
        summary.pop("recent_errors", None)
        payload = {
            "privacy_scope": "aggregate_only",
            "summary": summary,
        }
        timestamp = int(time.time())
        return Response(
            content=json.dumps(payload, indent=2, default=str),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="performance_export_{timestamp}.json"'
                ),
                "Cache-Control": "no-store",
            },
        )
    except Exception as exc:
        logging.exception("Failed to export performance metrics")
        raise HTTPException(status_code=500, detail="Failed to export metrics") from exc
