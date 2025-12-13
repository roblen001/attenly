"""
Credit Service

Handles cost-based credit tracking for rate limiting users based on actual API usage costs.
Integrates with Supabase for persistent storage and provides real-time credit status.
"""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from app.client import supabase_client
from app.config import (
    MODEL_PRICING,
    CREDITS_PER_CAD,
    DEFAULT_MONTHLY_LIMIT_CAD,
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
            logger.warning(f"No pricing found for model {model}, using default")
            # Default to cheapest model pricing
            pricing = MODEL_PRICING.get("gemini-2.5-flash-lite", {
                "input_per_million": 0.10,
                "output_per_million": 0.40,
            })

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

    async def check_credits(self, user_id: str) -> CreditStatus:
        """
        Check user's credit status without consuming any credits

        Args:
            user_id: The user's UUID

        Returns:
            CreditStatus with current usage information
        """
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
            logger.error(f"Failed to check credits for user {user_id}: {e}")
            # Fail open - allow operation but log error
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
            logger.error(f"Failed to consume credits for user {user_id}: {e}")
            # Fail open - allow the operation but log the error
            # Still try to log usage
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
            logger.error(f"Failed to check credits for user {user_id}: {e}")
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
            logger.error(f"Failed to consume credits for user {user_id}: {e}")
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
