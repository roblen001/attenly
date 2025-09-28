"""Authentication dependencies for Supabase integration."""
from fastapi import Depends, HTTPException, status, Header
from typing import Optional
from app.client import supabase_client
import logging

logger = logging.getLogger(__name__)

async def get_current_user(authorization: Optional[str] = Header(None, alias="Authorization")):
    """
    Dependency to get the current authenticated user from Supabase JWT token.
    
    Args:
        authorization: Authorization header containing Bearer token
        
    Returns:
        Supabase user object
        
    Raises:
        HTTPException: If token is missing, invalid, or user not found
    """
    if not authorization:
        logger.warning("Authentication attempt without authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not authorization.startswith("Bearer "):
        logger.warning(f"Invalid authorization header format: {authorization[:20]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication format. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization.split(" ")[1]
    
    try:
        # Validate token with Supabase
        user_response = supabase_client.auth.get_user(token)
        
        if not user_response.user:
            logger.warning("Token validation failed - no user returned")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.info(f"User authenticated successfully: {user_response.user.id}")
        return user_response.user
        
    except HTTPException:
        # Re-raise HTTP exceptions (already logged above)
        raise
    except Exception as e:
        logger.error(f"Unexpected error during token validation: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
