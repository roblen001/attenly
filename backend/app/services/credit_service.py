"""
Credit Service

Handles cost-based credit tracking for rate limiting users based on actual API usage costs.
Uses Supabase RPCs for the default profile and SQLAlchemy tables for local or
enterprise profiles.
"""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.client import supabase_client
from app.config import (
    MODEL_PRICING,
    CREDITS_PER_CAD,
    DEFAULT_MONTHLY_LIMIT_CAD,
    DEFAULT_MODEL_INPUT_COST_PER_MILLION_CAD,
    DEFAULT_MODEL_OUTPUT_COST_PER_MILLION_CAD,
    DATABASE_PROVIDER,
    WARNING_THRESHOLD_PERCENT,
    CRITICAL_THRESHOLD_PERCENT,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
)

logger = logging.getLogger(__name__)


@dataclass
class CreditStatus:
    """Current credit status for a user"""
    credits_remaining: int      # User-facing credits
    credits_limit: int          # Monthly limit in credits
    credits_used: int           # Used this month in credits
    percentage_used: float      # 0-100
    warning_level: str          # 'normal', 'warning', 'critical', 'blocked'
    reset_date: date            # First of next month
    days_until_reset: int       # Days until credits reset
    cost_used_cad: float        # Actual CAD spent (for debugging)
    monthly_limit_cad: float    # Limit in CAD


@dataclass
class ConsumeResult:
    """Result of consuming credits"""
    allowed: bool               # Whether the operation was allowed
    credits_remaining: int      # Credits remaining after operation
    warning_level: str          # Warning level after operation
    message: Optional[str]      # Optional message for user


@dataclass
class UsageSummary:
    """Usage breakdown by operation type"""
    operation_type: str
    total_cost_cad: float
    total_credits: int
    total_input_tokens: int
    total_output_tokens: int
    request_count: int


class CreditLimitExceeded(Exception):
    """Exception raised when user has exceeded their credit limit"""
    def __init__(self, credit_status: CreditStatus, message: str = "Monthly credit limit reached"):
        self.credit_status = credit_status
        self.message = message
        super().__init__(self.message)


class CreditService:
    """Service for tracking and consuming user credits based on API costs"""

    def __init__(self):
        self.supabase = supabase_client
        if DATABASE_PROVIDER == "sqlalchemy":
            self.service_client = None
            logger.info("Credit service initialized with SQLAlchemy persistence")
            return

        # Create a service role client for inserting usage logs
        try:
            from supabase import create_client
            if SUPABASE_SERVICE_ROLE_KEY and SUPABASE_URL:
                self.service_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
            else:
                self.service_client = supabase_client
                logger.warning("Using regular client - service role key not available")
        except Exception as e:
            logger.warning(f"Failed to create service client: {e}")
            self.service_client = supabase_client

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int = 0) -> float:
        """
        Calculate cost in CAD for a given operation

        Args:
            model: The model name (e.g., 'gemini-2.5-flash-lite')
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated

        Returns:
            Cost in CAD
        """
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            logger.warning("No pricing found for model %s; using configured default pricing", model)
            pricing = {
                "input_per_million": DEFAULT_MODEL_INPUT_COST_PER_MILLION_CAD,
                "output_per_million": DEFAULT_MODEL_OUTPUT_COST_PER_MILLION_CAD,
            }

        input_cost = (input_tokens / 1_000_000) * pricing["input_per_million"]
        output_cost = (output_tokens / 1_000_000) * pricing["output_per_million"]

        total_cost = input_cost + output_cost

        # Round to 6 decimal places
        return round(total_cost, 6)

    def cad_to_credits(self, cad: float) -> int:
        """Convert CAD to user-facing credits"""
        return int(round(cad * CREDITS_PER_CAD))

    def credits_to_cad(self, credits: int) -> float:
        """Convert credits back to CAD"""
        return credits / CREDITS_PER_CAD

    def _warning_level_to_string(self, level: int) -> str:
        """Convert numeric warning level to string"""
        if level >= 3:
            return "blocked"
        elif level >= 2:
            return "critical"
        elif level >= 1:
            return "warning"
        return "normal"

    def _reset_date(self, today: date | None = None) -> date:
        today = today or date.today()
        if today.month == 12:
            return date(today.year + 1, 1, 1)
        return date(today.year, today.month + 1, 1)

    def _billing_period_start(self, today: date | None = None) -> date:
        today = today or date.today()
        return date(today.year, today.month, 1)

    def _warning_level_for_percentage(self, percentage: float) -> int:
        if percentage >= 100:
            return 3
        if percentage >= CRITICAL_THRESHOLD_PERCENT:
            return 2
        if percentage >= WARNING_THRESHOLD_PERCENT:
            return 1
        return 0

    def _message_for_warning(self, warning_level: str) -> Optional[str]:
        if warning_level == "blocked":
            return "You've reached your monthly credit limit. Credits will reset on the 1st of next month."
        if warning_level == "critical":
            return f"Warning: You've used over {CRITICAL_THRESHOLD_PERCENT}% of your monthly credits."
        if warning_level == "warning":
            return f"Note: You've used over {WARNING_THRESHOLD_PERCENT}% of your monthly credits."
        return None

    def _status_from_usage(
        self,
        cost_used_cad: float,
        monthly_limit_cad: float,
        days_until_reset: Optional[int] = None,
    ) -> CreditStatus:
        reset_date = self._reset_date()
        if days_until_reset is None:
            days_until_reset = (reset_date - date.today()).days

        if monthly_limit_cad <= 0:
            percentage = 100.0
            warning_level = "blocked"
        else:
            percentage = (cost_used_cad / monthly_limit_cad) * 100
            warning_level = self._warning_level_to_string(
                self._warning_level_for_percentage(percentage)
            )

        credits_used = self.cad_to_credits(cost_used_cad)
        credits_limit = self.cad_to_credits(monthly_limit_cad)
        credits_remaining = max(0, credits_limit - credits_used)

        return CreditStatus(
            credits_remaining=credits_remaining,
            credits_limit=credits_limit,
            credits_used=credits_used,
            percentage_used=min(percentage, 100.0),
            warning_level=warning_level,
            reset_date=reset_date,
            days_until_reset=days_until_reset,
            cost_used_cad=cost_used_cad,
            monthly_limit_cad=monthly_limit_cad,
        )

    def _blocked_status(self) -> CreditStatus:
        return self._status_from_usage(
            cost_used_cad=DEFAULT_MONTHLY_LIMIT_CAD,
            monthly_limit_cad=DEFAULT_MONTHLY_LIMIT_CAD,
            days_until_reset=(self._reset_date() - date.today()).days,
        )

    def _uses_sqlalchemy(self) -> bool:
        return DATABASE_PROVIDER == "sqlalchemy"

    def _ensure_sqlalchemy_quota(self, session, user_id: str):
        from app.models import UserQuota

        period_start = self._billing_period_start()
        quota = (
            session.query(UserQuota)
            .filter(UserQuota.user_id == str(user_id))
            .with_for_update()
            .first()
        )

        if not quota:
            quota = UserQuota(
                user_id=str(user_id),
                monthly_limit_cad=DEFAULT_MONTHLY_LIMIT_CAD,
                cost_used_cad=0,
                billing_period_start=period_start,
                plan="free",
                last_warning_level=0,
            )
            session.add(quota)
            session.flush()
            return quota

        if quota.billing_period_start < period_start:
            quota.cost_used_cad = 0
            quota.billing_period_start = period_start
            quota.last_warning_level = 0
            quota.updated_at = datetime.now(timezone.utc)
            session.flush()

        return quota

    def _sqlalchemy_check_credits(self, user_id: str) -> CreditStatus:
        try:
            from app.db import SessionLocal

            with SessionLocal() as session:
                quota = self._ensure_sqlalchemy_quota(session, user_id)
                status = self._status_from_usage(
                    cost_used_cad=float(quota.cost_used_cad or 0),
                    monthly_limit_cad=float(quota.monthly_limit_cad or 0),
                )
                session.commit()
                return status
        except Exception as exc:
            logger.critical(
                "SECURITY_ALERT: SQLAlchemy credit check failed closed for user %s. Error: %s",
                user_id,
                exc,
            )
            return self._blocked_status()

    def _sqlalchemy_consume_credits(
        self,
        user_id: str,
        cost_cad: float,
        operation_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConsumeResult:
        try:
            from app.db import SessionLocal
            from app.models import UsageLog

            cost_cad = max(0.0, float(cost_cad or 0))
            with SessionLocal() as session:
                quota = self._ensure_sqlalchemy_quota(session, user_id)
                new_cost = float(quota.cost_used_cad or 0) + cost_cad
                monthly_limit = float(quota.monthly_limit_cad or 0)
                percentage = 100.0 if monthly_limit <= 0 else (new_cost / monthly_limit) * 100
                warning_level = self._warning_level_for_percentage(percentage)

                quota.cost_used_cad = new_cost
                quota.updated_at = datetime.now(timezone.utc)
                if warning_level > int(quota.last_warning_level or 0):
                    quota.last_warning_level = warning_level

                session.add(
                    UsageLog(
                        user_id=str(user_id),
                        operation_type=operation_type,
                        model_name=model,
                        input_tokens=int(input_tokens or 0),
                        output_tokens=int(output_tokens or 0),
                        cost_cad=cost_cad,
                        usage_metadata=metadata or {},
                    )
                )
                session.commit()

                warning_str = self._warning_level_to_string(warning_level)
                status = self._status_from_usage(new_cost, monthly_limit)
                return ConsumeResult(
                    allowed=percentage < 100,
                    credits_remaining=status.credits_remaining,
                    warning_level=warning_str,
                    message=self._message_for_warning(warning_str),
                )
        except Exception as exc:
            logger.critical(
                "SECURITY_ALERT: SQLAlchemy credit consumption failed closed for user %s. "
                "Operation: %s, Cost: $%.6f CAD. Error: %s",
                user_id,
                operation_type,
                cost_cad,
                exc,
            )
            return ConsumeResult(
                allowed=False,
                credits_remaining=0,
                warning_level="blocked",
                message=self._message_for_warning("blocked"),
            )

    def _sqlalchemy_log_usage(
        self,
        user_id: str,
        operation_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_cad: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        from app.db import SessionLocal
        from app.models import UsageLog

        with SessionLocal() as session:
            session.add(
                UsageLog(
                    user_id=str(user_id),
                    operation_type=operation_type,
                    model_name=model,
                    input_tokens=int(input_tokens or 0),
                    output_tokens=int(output_tokens or 0),
                    cost_cad=max(0.0, float(cost_cad or 0)),
                    usage_metadata=metadata or {},
                )
            )
            session.commit()

    def _sqlalchemy_usage_summary(self, user_id: str, days: int = 30) -> list[UsageSummary]:
        try:
            from sqlalchemy import func
            from app.db import SessionLocal
            from app.models import UsageLog

            start_at = datetime.now(timezone.utc) - timedelta(days=days)
            with SessionLocal() as session:
                rows = (
                    session.query(
                        UsageLog.operation_type,
                        func.sum(UsageLog.cost_cad).label("total_cost_cad"),
                        func.sum(UsageLog.input_tokens).label("total_input_tokens"),
                        func.sum(UsageLog.output_tokens).label("total_output_tokens"),
                        func.count(UsageLog.id).label("request_count"),
                    )
                    .filter(
                        UsageLog.user_id == str(user_id),
                        UsageLog.created_at >= start_at,
                    )
                    .group_by(UsageLog.operation_type)
                    .order_by(UsageLog.operation_type)
                    .all()
                )

            return [
                UsageSummary(
                    operation_type=row.operation_type,
                    total_cost_cad=float(row.total_cost_cad or 0),
                    total_credits=self.cad_to_credits(float(row.total_cost_cad or 0)),
                    total_input_tokens=int(row.total_input_tokens or 0),
                    total_output_tokens=int(row.total_output_tokens or 0),
                    request_count=int(row.request_count or 0),
                )
                for row in rows
            ]
        except Exception as exc:
            logger.error("Failed to get SQLAlchemy usage summary for user %s: %s", user_id, exc)
            return []

    def _sqlalchemy_usage_history(self, user_id: str, days: int = 30) -> list[Dict[str, Any]]:
        try:
            from sqlalchemy import func
            from app.db import SessionLocal
            from app.models import UsageLog

            start_at = datetime.now(timezone.utc) - timedelta(days=days)
            usage_day = func.date(UsageLog.created_at)
            with SessionLocal() as session:
                rows = (
                    session.query(
                        usage_day.label("date"),
                        func.sum(UsageLog.cost_cad).label("total_cost_cad"),
                        func.count(UsageLog.id).label("request_count"),
                    )
                    .filter(
                        UsageLog.user_id == str(user_id),
                        UsageLog.created_at >= start_at,
                    )
                    .group_by(usage_day)
                    .order_by(usage_day)
                    .all()
                )

            return [
                {
                    "date": str(row.date),
                    "total_cost_cad": float(row.total_cost_cad or 0),
                    "total_credits": self.cad_to_credits(float(row.total_cost_cad or 0)),
                    "request_count": int(row.request_count or 0),
                }
                for row in rows
            ]
        except Exception as exc:
            logger.error("Failed to get SQLAlchemy usage history for user %s: %s", user_id, exc)
            return []

    async def check_credits(self, user_id: str) -> CreditStatus:
        """
        Check user's credit status without consuming any credits

        Args:
            user_id: The user's UUID

        Returns:
            CreditStatus with current usage information
        """
        if self._uses_sqlalchemy():
            return self._sqlalchemy_check_credits(user_id)

        try:
            # Call the get_user_credits database function
            result = self.supabase.rpc(
                "get_user_credits",
                {"p_user_id": user_id}
            ).execute()

            if result.data and len(result.data) > 0:
                row = result.data[0]
                cost_used = float(row.get("cost_used_cad", 0))
                monthly_limit = float(row.get("monthly_limit_cad", DEFAULT_MONTHLY_LIMIT_CAD))
                percentage = float(row.get("percentage_used", 0))
                warning_level = int(row.get("warning_level", 0))
                days_until = int(row.get("days_until_reset", 30))

                credits_used = self.cad_to_credits(cost_used)
                credits_limit = self.cad_to_credits(monthly_limit)
                credits_remaining = max(0, credits_limit - credits_used)

                # Calculate reset date (first of next month)
                today = date.today()
                if today.month == 12:
                    reset_date = date(today.year + 1, 1, 1)
                else:
                    reset_date = date(today.year, today.month + 1, 1)

                return CreditStatus(
                    credits_remaining=credits_remaining,
                    credits_limit=credits_limit,
                    credits_used=credits_used,
                    percentage_used=min(percentage, 100.0),
                    warning_level=self._warning_level_to_string(warning_level),
                    reset_date=reset_date,
                    days_until_reset=days_until,
                    cost_used_cad=cost_used,
                    monthly_limit_cad=monthly_limit
                )
            else:
                # No record found - user has full credits
                credits_limit = self.cad_to_credits(DEFAULT_MONTHLY_LIMIT_CAD)
                today = date.today()
                if today.month == 12:
                    reset_date = date(today.year + 1, 1, 1)
                else:
                    reset_date = date(today.year, today.month + 1, 1)
                days_until = (reset_date - today).days

                return CreditStatus(
                    credits_remaining=credits_limit,
                    credits_limit=credits_limit,
                    credits_used=0,
                    percentage_used=0.0,
                    warning_level="normal",
                    reset_date=reset_date,
                    days_until_reset=days_until,
                    cost_used_cad=0.0,
                    monthly_limit_cad=DEFAULT_MONTHLY_LIMIT_CAD
                )

        except Exception as e:
            # SECURITY ALERT: Fail-open on credit check error - operation allowed without verification
            logger.critical(
                f"SECURITY_ALERT: Credit check failed open for user {user_id}. "
                f"Error: {e}. User granted default credits without verification."
            )
            credits_limit = self.cad_to_credits(DEFAULT_MONTHLY_LIMIT_CAD)
            today = date.today()
            if today.month == 12:
                reset_date = date(today.year + 1, 1, 1)
            else:
                reset_date = date(today.year, today.month + 1, 1)

            return CreditStatus(
                credits_remaining=credits_limit,
                credits_limit=credits_limit,
                credits_used=0,
                percentage_used=0.0,
                warning_level="normal",
                reset_date=reset_date,
                days_until_reset=(reset_date - today).days,
                cost_used_cad=0.0,
                monthly_limit_cad=DEFAULT_MONTHLY_LIMIT_CAD
            )

    async def consume_credits(
        self,
        user_id: str,
        cost_cad: float,
        operation_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ConsumeResult:
        """
        Consume credits and log usage

        Args:
            user_id: The user's UUID
            cost_cad: Cost in CAD to deduct
            operation_type: Type of operation (e.g., 'llm_extraction', 'embedding')
            model: Model name used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            metadata: Optional additional metadata to log

        Returns:
            ConsumeResult with status and remaining credits
        """
        if self._uses_sqlalchemy():
            return self._sqlalchemy_consume_credits(
                user_id=user_id,
                cost_cad=cost_cad,
                operation_type=operation_type,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                metadata=metadata,
            )

        try:
            # Call the consume_cost database function
            result = self.supabase.rpc(
                "consume_cost",
                {"p_user_id": user_id, "p_cost_cad": cost_cad}
            ).execute()

            if result.data and len(result.data) > 0:
                row = result.data[0]
                allowed = row.get("allowed", True)
                credits_remaining_cad = float(row.get("credits_remaining", 0))
                warning_level = int(row.get("warning_level", 0))

                credits_remaining = self.cad_to_credits(max(0, credits_remaining_cad))
                warning_str = self._warning_level_to_string(warning_level)

                # Log the usage to usage_logs table
                await self._log_usage(
                    user_id=user_id,
                    operation_type=operation_type,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_cad=cost_cad,
                    metadata=metadata
                )

                # Determine message based on warning level
                message = None
                if warning_str == "blocked":
                    message = "You've reached your monthly credit limit. Credits will reset on the 1st of next month."
                elif warning_str == "critical":
                    message = f"Warning: You've used over {CRITICAL_THRESHOLD_PERCENT}% of your monthly credits."
                elif warning_str == "warning":
                    message = f"Note: You've used over {WARNING_THRESHOLD_PERCENT}% of your monthly credits."

                return ConsumeResult(
                    allowed=allowed,
                    credits_remaining=credits_remaining,
                    warning_level=warning_str,
                    message=message
                )
            else:
                # Function returned no data - assume success
                logger.warning(f"consume_cost returned no data for user {user_id}")
                return ConsumeResult(
                    allowed=True,
                    credits_remaining=0,
                    warning_level="normal",
                    message=None
                )

        except Exception as e:
            # SECURITY ALERT: Fail-open on consume credits error - operation allowed without deduction
            logger.critical(
                f"SECURITY_ALERT: Consume credits failed open for user {user_id}. "
                f"Operation: {operation_type}, Cost: ${cost_cad:.6f} CAD. "
                f"Error: {e}. Credits not deducted but operation allowed."
            )
            # Still try to log usage for auditing
            try:
                await self._log_usage(
                    user_id=user_id,
                    operation_type=operation_type,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_cad=cost_cad,
                    metadata=metadata
                )
            except Exception as log_error:
                logger.error(f"Failed to log usage: {log_error}")

            return ConsumeResult(
                allowed=True,
                credits_remaining=0,
                warning_level="normal",
                message=None
            )

    async def _log_usage(
        self,
        user_id: str,
        operation_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_cad: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log usage to the usage_logs table"""
        if self._uses_sqlalchemy():
            self._sqlalchemy_log_usage(
                user_id=user_id,
                operation_type=operation_type,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_cad=cost_cad,
                metadata=metadata,
            )
            return

        try:
            self.service_client.table("usage_logs").insert({
                "user_id": user_id,
                "operation_type": operation_type,
                "model_name": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_cad": cost_cad,
                "metadata": metadata or {}
            }).execute()
        except Exception as e:
            logger.error(f"Failed to insert usage log: {e}")

    async def get_usage_summary(self, user_id: str, days: int = 30) -> list[UsageSummary]:
        """
        Get usage breakdown by operation type

        Args:
            user_id: The user's UUID
            days: Number of days to look back

        Returns:
            List of UsageSummary objects
        """
        if self._uses_sqlalchemy():
            return self._sqlalchemy_usage_summary(user_id, days)

        try:
            result = self.supabase.rpc(
                "get_usage_summary",
                {"p_user_id": user_id, "p_days": days}
            ).execute()

            summaries = []
            if result.data:
                for row in result.data:
                    cost_cad = float(row.get("total_cost_cad", 0))
                    summaries.append(UsageSummary(
                        operation_type=row.get("operation_type", "unknown"),
                        total_cost_cad=cost_cad,
                        total_credits=self.cad_to_credits(cost_cad),
                        total_input_tokens=int(row.get("total_input_tokens", 0)),
                        total_output_tokens=int(row.get("total_output_tokens", 0)),
                        request_count=int(row.get("request_count", 0))
                    ))

            return summaries

        except Exception as e:
            logger.error(f"Failed to get usage summary for user {user_id}: {e}")
            return []

    async def get_usage_history(self, user_id: str, days: int = 30) -> list[Dict[str, Any]]:
        """
        Get daily usage history

        Args:
            user_id: The user's UUID
            days: Number of days to look back

        Returns:
            List of daily usage records
        """
        if self._uses_sqlalchemy():
            return self._sqlalchemy_usage_history(user_id, days)

        try:
            result = self.supabase.rpc(
                "get_usage_history",
                {"p_user_id": user_id, "p_days": days}
            ).execute()

            history = []
            if result.data:
                for row in result.data:
                    cost_cad = float(row.get("total_cost_cad", 0))
                    history.append({
                        "date": row.get("date"),
                        "total_cost_cad": cost_cad,
                        "total_credits": self.cad_to_credits(cost_cad),
                        "request_count": int(row.get("request_count", 0))
                    })

            return history

        except Exception as e:
            logger.error(f"Failed to get usage history for user {user_id}: {e}")
            return []


    # =========================================================================
    # SYNCHRONOUS METHODS (for use in sync code like LLM service)
    # =========================================================================

    def check_credits_sync(self, user_id: str) -> CreditStatus:
        """
        Synchronous version of check_credits for use in sync code.
        """
        if self._uses_sqlalchemy():
            return self._sqlalchemy_check_credits(user_id)

        try:
            result = self.supabase.rpc(
                "get_user_credits",
                {"p_user_id": user_id}
            ).execute()

            if result.data and len(result.data) > 0:
                row = result.data[0]
                cost_used = float(row.get("cost_used_cad", 0))
                monthly_limit = float(row.get("monthly_limit_cad", DEFAULT_MONTHLY_LIMIT_CAD))
                percentage = float(row.get("percentage_used", 0))
                warning_level = int(row.get("warning_level", 0))
                days_until = int(row.get("days_until_reset", 30))

                credits_used = self.cad_to_credits(cost_used)
                credits_limit = self.cad_to_credits(monthly_limit)
                credits_remaining = max(0, credits_limit - credits_used)

                today = date.today()
                if today.month == 12:
                    reset_date = date(today.year + 1, 1, 1)
                else:
                    reset_date = date(today.year, today.month + 1, 1)

                return CreditStatus(
                    credits_remaining=credits_remaining,
                    credits_limit=credits_limit,
                    credits_used=credits_used,
                    percentage_used=min(percentage, 100.0),
                    warning_level=self._warning_level_to_string(warning_level),
                    reset_date=reset_date,
                    days_until_reset=days_until,
                    cost_used_cad=cost_used,
                    monthly_limit_cad=monthly_limit
                )
            else:
                credits_limit = self.cad_to_credits(DEFAULT_MONTHLY_LIMIT_CAD)
                today = date.today()
                if today.month == 12:
                    reset_date = date(today.year + 1, 1, 1)
                else:
                    reset_date = date(today.year, today.month + 1, 1)
                days_until = (reset_date - today).days

                return CreditStatus(
                    credits_remaining=credits_limit,
                    credits_limit=credits_limit,
                    credits_used=0,
                    percentage_used=0.0,
                    warning_level="normal",
                    reset_date=reset_date,
                    days_until_reset=days_until,
                    cost_used_cad=0.0,
                    monthly_limit_cad=DEFAULT_MONTHLY_LIMIT_CAD
                )

        except Exception as e:
            # SECURITY ALERT: Fail-open on credit check error - operation allowed without verification
            logger.critical(
                f"SECURITY_ALERT: Credit check failed open for user {user_id}. "
                f"Error: {e}. User granted default credits without verification."
            )
            credits_limit = self.cad_to_credits(DEFAULT_MONTHLY_LIMIT_CAD)
            today = date.today()
            if today.month == 12:
                reset_date = date(today.year + 1, 1, 1)
            else:
                reset_date = date(today.year, today.month + 1, 1)

            return CreditStatus(
                credits_remaining=credits_limit,
                credits_limit=credits_limit,
                credits_used=0,
                percentage_used=0.0,
                warning_level="normal",
                reset_date=reset_date,
                days_until_reset=(reset_date - today).days,
                cost_used_cad=0.0,
                monthly_limit_cad=DEFAULT_MONTHLY_LIMIT_CAD
            )

    def consume_credits_sync(
        self,
        user_id: str,
        cost_cad: float,
        operation_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ConsumeResult:
        """
        Synchronous version of consume_credits for use in sync code.
        """
        if self._uses_sqlalchemy():
            return self._sqlalchemy_consume_credits(
                user_id=user_id,
                cost_cad=cost_cad,
                operation_type=operation_type,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                metadata=metadata,
            )

        try:
            result = self.supabase.rpc(
                "consume_cost",
                {"p_user_id": user_id, "p_cost_cad": cost_cad}
            ).execute()

            if result.data and len(result.data) > 0:
                row = result.data[0]
                allowed = row.get("allowed", True)
                credits_remaining_cad = float(row.get("credits_remaining", 0))
                warning_level = int(row.get("warning_level", 0))

                credits_remaining = self.cad_to_credits(max(0, credits_remaining_cad))
                warning_str = self._warning_level_to_string(warning_level)

                # Log the usage
                self._log_usage_sync(
                    user_id=user_id,
                    operation_type=operation_type,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_cad=cost_cad,
                    metadata=metadata
                )

                message = None
                if warning_str == "blocked":
                    message = "You've reached your monthly credit limit. Credits will reset on the 1st of next month."
                elif warning_str == "critical":
                    message = f"Warning: You've used over {CRITICAL_THRESHOLD_PERCENT}% of your monthly credits."
                elif warning_str == "warning":
                    message = f"Note: You've used over {WARNING_THRESHOLD_PERCENT}% of your monthly credits."

                return ConsumeResult(
                    allowed=allowed,
                    credits_remaining=credits_remaining,
                    warning_level=warning_str,
                    message=message
                )
            else:
                logger.warning(f"consume_cost returned no data for user {user_id}")
                return ConsumeResult(
                    allowed=True,
                    credits_remaining=0,
                    warning_level="normal",
                    message=None
                )

        except Exception as e:
            # SECURITY ALERT: Fail-open on consume credits error - operation allowed without deduction
            logger.critical(
                f"SECURITY_ALERT: Consume credits failed open for user {user_id}. "
                f"Operation: {operation_type}, Cost: ${cost_cad:.6f} CAD. "
                f"Error: {e}. Credits not deducted but operation allowed."
            )
            # Still try to log usage for auditing
            try:
                self._log_usage_sync(
                    user_id=user_id,
                    operation_type=operation_type,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_cad=cost_cad,
                    metadata=metadata
                )
            except Exception as log_error:
                logger.error(f"Failed to log usage: {log_error}")

            return ConsumeResult(
                allowed=True,
                credits_remaining=0,
                warning_level="normal",
                message=None
            )

    def _log_usage_sync(
        self,
        user_id: str,
        operation_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_cad: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Synchronous version of _log_usage"""
        if self._uses_sqlalchemy():
            self._sqlalchemy_log_usage(
                user_id=user_id,
                operation_type=operation_type,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_cad=cost_cad,
                metadata=metadata,
            )
            return

        try:
            self.service_client.table("usage_logs").insert({
                "user_id": user_id,
                "operation_type": operation_type,
                "model_name": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_cad": cost_cad,
                "metadata": metadata or {}
            }).execute()
        except Exception as e:
            logger.error(f"Failed to insert usage log: {e}")


# Global singleton instance
credit_service = CreditService()


def get_credit_service() -> CreditService:
    """Get the global credit service instance"""
    return credit_service
