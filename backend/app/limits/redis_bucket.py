"""Redis-based token bucket for user quota management."""
from typing import Optional
import redis
import json
import time
import logging
from fastapi import HTTPException, status
import os

logger = logging.getLogger(__name__)

class RedisTokenBucket:
    """
    Redis-based token bucket implementation for user quota management.
    
    Features:
    - Per-user rate limiting based on subscription plans
    - Credit consumption tracking
    - Sliding window implementation
    - Automatic bucket refill
    """
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_client = None
        self._connect()
    
    def _connect(self):
        """Connect to Redis with error handling."""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            # Test connection
            self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None
    
    def _get_bucket_key(self, user_id: str, bucket_type: str = "general") -> str:
        """Generate Redis key for user bucket."""
        return f"bucket:{user_id}:{bucket_type}"
    
    def _get_user_plan_limits(self, user_id: str) -> dict:
        """
        Get user plan limits. In production, this would query the database.
        For now, returns default limits.
        """
        # TODO: Query actual user plan from database
        return {
            "requests_per_hour": 100,
            "llm_credits_per_hour": 10,
            "upload_limit_per_hour": 20
        }
    
    async def check_and_consume_quota(
        self, 
        user_id: str, 
        cost: int = 1, 
        bucket_type: str = "general"
    ) -> bool:
        """
        Check if user has quota available and consume if possible.
        
        Args:
            user_id: User identifier
            cost: Number of tokens/credits to consume
            bucket_type: Type of operation (general, llm, upload)
        
        Returns:
            bool: True if quota was available and consumed, False otherwise
        
        Raises:
            HTTPException: If quota exceeded or Redis unavailable
        """
        if not self.redis_client:
            logger.warning("Redis not available, allowing request")
            return True
        
        try:
            bucket_key = self._get_bucket_key(user_id, bucket_type)
            current_time = int(time.time())
            window_start = current_time - 3600  # 1 hour window
            
            # Get user limits
            limits = self._get_user_plan_limits(user_id)
            limit_key = f"{bucket_type}_per_hour" if f"{bucket_type}_per_hour" in limits else "requests_per_hour"
            max_tokens = limits.get(limit_key, 100)
            
            # Use Redis pipeline for atomic operations
            pipe = self.redis_client.pipeline()
            
            # Remove old entries outside the window
            pipe.zremrangebyscore(bucket_key, 0, window_start)
            
            # Count current tokens in the window
            pipe.zcard(bucket_key)
            
            # Execute pipeline
            results = pipe.execute()
            current_count = results[1]
            
            # Check if adding the cost would exceed limit
            if current_count + cost > max_tokens:
                logger.warning(
                    f"Quota exceeded for user {user_id}",
                    extra={
                        "user_id": user_id,
                        "bucket_type": bucket_type,
                        "current_count": current_count,
                        "cost": cost,
                        "limit": max_tokens
                    }
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "Quota exceeded",
                        "message": f"You have exceeded your {bucket_type} quota for this hour.",
                        "current_usage": current_count,
                        "limit": max_tokens,
                        "retry_after": 3600
                    },
                    headers={"Retry-After": "3600"}
                )
            
            # Consume tokens by adding entries to the sorted set
            pipe = self.redis_client.pipeline()
            for i in range(cost):
                # Use unique timestamp + counter for each token
                timestamp = current_time + (i * 0.001)  # Microsecond precision
                pipe.zadd(bucket_key, {f"{timestamp}:{i}": timestamp})
            
            # Set expiration for cleanup
            pipe.expire(bucket_key, 3600)
            
            # Execute consumption
            pipe.execute()
            
            logger.info(
                f"Quota consumed for user {user_id}",
                extra={
                    "user_id": user_id,
                    "bucket_type": bucket_type,
                    "cost": cost,
                    "remaining": max_tokens - (current_count + cost)
                }
            )
            
            return True
            
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            logger.error(f"Error checking quota for user {user_id}: {e}")
            # Allow request if Redis fails (fail open)
            return True
    
    async def get_quota_status(self, user_id: str, bucket_type: str = "general") -> dict:
        """
        Get current quota status for a user.
        
        Returns:
            dict: Current usage, limit, and remaining quota
        """
        if not self.redis_client:
            return {"error": "Redis not available"}
        
        try:
            bucket_key = self._get_bucket_key(user_id, bucket_type)
            current_time = int(time.time())
            window_start = current_time - 3600
            
            # Clean up old entries and get current count
            pipe = self.redis_client.pipeline()
            pipe.zremrangebyscore(bucket_key, 0, window_start)
            pipe.zcard(bucket_key)
            results = pipe.execute()
            
            current_count = results[1]
            limits = self._get_user_plan_limits(user_id)
            limit_key = f"{bucket_type}_per_hour" if f"{bucket_type}_per_hour" in limits else "requests_per_hour"
            max_tokens = limits.get(limit_key, 100)
            
            return {
                "current_usage": current_count,
                "limit": max_tokens,
                "remaining": max_tokens - current_count,
                "window_reset_at": current_time + 3600
            }
            
        except Exception as e:
            logger.error(f"Error getting quota status for user {user_id}: {e}")
            return {"error": str(e)}
    
    async def reset_user_quota(self, user_id: str, bucket_type: str = "general"):
        """Reset quota for a user (admin function)."""
        if not self.redis_client:
            return
        
        try:
            bucket_key = self._get_bucket_key(user_id, bucket_type)
            self.redis_client.delete(bucket_key)
            logger.info(f"Reset quota for user {user_id}, bucket {bucket_type}")
        except Exception as e:
            logger.error(f"Error resetting quota for user {user_id}: {e}")

# Global instance
_token_bucket = None

def get_token_bucket() -> RedisTokenBucket:
    """Get or create the global token bucket instance."""
    global _token_bucket
    if _token_bucket is None:
        _token_bucket = RedisTokenBucket()
    return _token_bucket

async def check_user_quota(user_id: str, cost: int = 1, bucket_type: str = "general") -> bool:
    """Convenience function to check user quota."""
    bucket = get_token_bucket()
    return await bucket.check_and_consume_quota(user_id, cost, bucket_type)

async def get_user_quota_status(user_id: str, bucket_type: str = "general") -> dict:
    """Convenience function to get user quota status."""
    bucket = get_token_bucket()
    return await bucket.get_quota_status(user_id, bucket_type)
