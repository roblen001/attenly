"""
Credits Router

API endpoints for managing user credits and viewing usage information.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.services.credit_service import get_credit_service, CreditStatus as CreditStatusData

router = APIRouter(prefix="/api/credits", tags=["credits"])


class CreditStatusResponse(BaseModel):
    """Response model for credit status"""
    credits_remaining: int
    credits_limit: int
    credits_used: int
    percentage_used: float
    warning_level: str
    reset_date: str
    days_until_reset: int


class UsageSummaryItem(BaseModel):
    """Single usage summary item"""
    operation_type: str
    total_credits: int
    total_cost_cad: float
    total_input_tokens: int
    total_output_tokens: int
    request_count: int


class UsageHistoryItem(BaseModel):
    """Single usage history item"""
    date: str
    total_credits: int
    total_cost_cad: float
    request_count: int


@router.get("", response_model=CreditStatusResponse)
async def get_credit_status(current_user=Depends(get_current_user)):
    """
    Get current credit status for the authenticated user.

    Returns:
        - credits_remaining: Number of credits available
        - credits_limit: Monthly credit limit
        - credits_used: Credits used this billing period
        - percentage_used: Percentage of limit used (0-100)
        - warning_level: 'normal', 'warning', 'critical', or 'blocked'
        - reset_date: Date when credits will reset
        - days_until_reset: Days until the reset date
    """
    credit_service = get_credit_service()
    status = await credit_service.check_credits(str(current_user.id))

    return CreditStatusResponse(
        credits_remaining=status.credits_remaining,
        credits_limit=status.credits_limit,
        credits_used=status.credits_used,
        percentage_used=round(status.percentage_used, 2),
        warning_level=status.warning_level,
        reset_date=status.reset_date.isoformat(),
        days_until_reset=status.days_until_reset
    )


@router.get("/usage", response_model=list[UsageSummaryItem])
async def get_usage_breakdown(
    current_user=Depends(get_current_user),
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back")
):
    """
    Get detailed usage breakdown by operation type.

    Args:
        days: Number of days to include in the summary (default: 30)

    Returns:
        List of usage summaries grouped by operation type (llm_extraction, embedding, etc.)
    """
    credit_service = get_credit_service()
    summaries = await credit_service.get_usage_summary(str(current_user.id), days)

    return [
        UsageSummaryItem(
            operation_type=s.operation_type,
            total_credits=s.total_credits,
            total_cost_cad=round(s.total_cost_cad, 4),
            total_input_tokens=s.total_input_tokens,
            total_output_tokens=s.total_output_tokens,
            request_count=s.request_count
        )
        for s in summaries
    ]


@router.get("/history", response_model=list[UsageHistoryItem])
async def get_usage_history(
    current_user=Depends(get_current_user),
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back")
):
    """
    Get daily usage history for graphing/charts.

    Args:
        days: Number of days to include in the history (default: 30)

    Returns:
        List of daily usage records with date, credits used, and request count
    """
    credit_service = get_credit_service()
    history = await credit_service.get_usage_history(str(current_user.id), days)

    return [
        UsageHistoryItem(
            date=h["date"],
            total_credits=h["total_credits"],
            total_cost_cad=round(h["total_cost_cad"], 4),
            request_count=h["request_count"]
        )
        for h in history
    ]
