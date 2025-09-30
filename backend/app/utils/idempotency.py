"""Idempotency key handling for preventing duplicate operations."""
from typing import Optional, Dict, Any
import hashlib
import json
import time
import logging
from fastapi import Request, HTTPException, status, Header
import redis
import os

logger = logging.getLogger(__name__)

class IdempotencyManager:
    """
    Manages idempotency keys to prevent duplicate operations.
    
    Features:
    - 24-hour idempotency window
    - Redis-based storage for scalability
    - Request content hashing for validation
    - Response caching for identical requests
    """
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_client = None
        self.ttl = 86400  # 24 hours
        self._connect()
    
    def _connect(self):
        """Connect to Redis with error handling."""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("Idempotency Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis for idempotency: {e}")
            self.redis_client = None
    
    def _generate_content_hash(self, request_data: Dict[str, Any]) -> str:
        """Generate a hash of the request content for validation."""
        # Create a stable hash of the request data
        content_str = json.dumps(request_data, sort_keys=True)
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]
    
    def _get_idempotency_key(self, key: str, user_id: str) -> str:
        """Generate Redis key for idempotency storage."""
        return f"idempotency:{user_id}:{key}"
    
    async def check_idempotency(
        self,
        idempotency_key: str,
        user_id: str,
        request_data: Dict[str, Any],
        endpoint: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if request is duplicate and return cached response if so.
        
        Args:
            idempotency_key: Client-provided idempotency key
            user_id: User identifier
            request_data: Request payload data
            endpoint: API endpoint name
        
        Returns:
            Optional[Dict]: Cached response if duplicate, None if new request
        
        Raises:
            HTTPException: If idempotency key conflict detected
        """
        if not self.redis_client:
            logger.warning("Redis not available for idempotency check, allowing request")
            return None
        
        try:
            redis_key = self._get_idempotency_key(idempotency_key, user_id)
            content_hash = self._generate_content_hash(request_data)
            
            # Check if idempotency key exists
            stored_data = self.redis_client.get(redis_key)
            
            if stored_data:
                stored = json.loads(stored_data)
                
                # Validate that the request content matches
                if stored.get("content_hash") != content_hash:
                    logger.warning(
                        f"Idempotency key conflict for user {user_id}",
                        extra={
                            "user_id": user_id,
                            "idempotency_key": idempotency_key,
                            "endpoint": endpoint,
                            "stored_hash": stored.get("content_hash"),
                            "current_hash": content_hash
                        }
                    )
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail={
                            "error": "Idempotency key conflict",
                            "message": "The same idempotency key was used with different request content.",
                            "idempotency_key": idempotency_key
                        }
                    )
                
                # Check if response is ready
                if stored.get("status") == "completed" and "response" in stored:
                    logger.info(
                        f"Returning cached response for idempotency key {idempotency_key}",
                        extra={
                            "user_id": user_id,
                            "idempotency_key": idempotency_key,
                            "endpoint": endpoint
                        }
                    )
                    return stored["response"]
                
                # Request is in progress
                elif stored.get("status") == "processing":
                    logger.info(
                        f"Request in progress for idempotency key {idempotency_key}",
                        extra={
                            "user_id": user_id,
                            "idempotency_key": idempotency_key,
                            "endpoint": endpoint
                        }
                    )
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error": "Request in progress",
                            "message": "A request with this idempotency key is currently being processed.",
                            "idempotency_key": idempotency_key,
                            "retry_after": 30
                        },
                        headers={"Retry-After": "30"}
                    )
            
            # Mark request as processing
            processing_data = {
                "content_hash": content_hash,
                "status": "processing",
                "endpoint": endpoint,
                "created_at": int(time.time()),
                "user_id": user_id
            }
            
            self.redis_client.setex(
                redis_key,
                self.ttl,
                json.dumps(processing_data)
            )
            
            logger.info(
                f"New idempotent request registered: {idempotency_key}",
                extra={
                    "user_id": user_id,
                    "idempotency_key": idempotency_key,
                    "endpoint": endpoint
                }
            )
            
            return None
            
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            logger.error(f"Error checking idempotency: {e}")
            # Allow request if Redis fails
            return None
    
    async def store_response(
        self,
        idempotency_key: str,
        user_id: str,
        response_data: Dict[str, Any]
    ):
        """Store successful response for future duplicate requests."""
        if not self.redis_client:
            return
        
        try:
            redis_key = self._get_idempotency_key(idempotency_key, user_id)
            
            # Get existing data to preserve content hash
            existing_data = self.redis_client.get(redis_key)
            if not existing_data:
                logger.warning(f"No existing idempotency data found for key {idempotency_key}")
                return
            
            stored = json.loads(existing_data)
            stored["status"] = "completed"
            stored["response"] = response_data
            stored["completed_at"] = int(time.time())
            
            self.redis_client.setex(
                redis_key,
                self.ttl,
                json.dumps(stored)
            )
            
            logger.info(
                f"Stored response for idempotency key {idempotency_key}",
                extra={
                    "user_id": user_id,
                    "idempotency_key": idempotency_key
                }
            )
            
        except Exception as e:
            logger.error(f"Error storing idempotent response: {e}")
    
    async def cleanup_failed_request(self, idempotency_key: str, user_id: str):
        """Clean up failed request to allow retry."""
        if not self.redis_client:
            return
        
        try:
            redis_key = self._get_idempotency_key(idempotency_key, user_id)
            self.redis_client.delete(redis_key)
            
            logger.info(
                f"Cleaned up failed idempotency key {idempotency_key}",
                extra={
                    "user_id": user_id,
                    "idempotency_key": idempotency_key
                }
            )
            
        except Exception as e:
            logger.error(f"Error cleaning up failed idempotency key: {e}")

# Global instance
_idempotency_manager = None

def get_idempotency_manager() -> IdempotencyManager:
    """Get or create the global idempotency manager instance."""
    global _idempotency_manager
    if _idempotency_manager is None:
        _idempotency_manager = IdempotencyManager()
    return _idempotency_manager

# Dependency for FastAPI routes
async def handle_idempotency(
    request: Request,
    user_id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency to handle idempotency for routes.
    
    Usage:
        @app.post("/expensive-operation")
        async def expensive_op(
            request: Request,
            user: User = Depends(get_current_user),
            cached_response: Optional[Dict] = Depends(handle_idempotency)
        ):
            if cached_response:
                return cached_response
            
            # Process request...
            result = await process_request()
            
            # Store result for future duplicate requests
            if idempotency_key:
                manager = get_idempotency_manager()
                await manager.store_response(idempotency_key, user.id, result)
            
            return result
    """
    if not idempotency_key:
        return None
    
    # Validate idempotency key format (UUID-like)
    if len(idempotency_key) < 16 or len(idempotency_key) > 128:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Invalid idempotency key",
                "message": "Idempotency key must be between 16 and 128 characters."
            }
        )
    
    # Get request data for content hashing
    try:
        if request.method in ["POST", "PUT", "PATCH"]:
            request_body = await request.body()
            if request_body:
                request_data = json.loads(request_body.decode()) if request_body else {}
            else:
                request_data = {}
        else:
            request_data = dict(request.query_params)
    except Exception:
        request_data = {}
    
    manager = get_idempotency_manager()
    endpoint = f"{request.method} {request.url.path}"
    
    return await manager.check_idempotency(
        idempotency_key,
        user_id,
        request_data,
        endpoint
    )
