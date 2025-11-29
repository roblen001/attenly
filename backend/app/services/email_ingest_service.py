"""
Email Ingest Service - Business Logic for Email to Attenly Feature

Handles email endpoint management, sender verification, and rate limiting.
All database operations use supabase_service for RLS compliance.
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from app import config
from app.services.supabase_service import supabase_service
from app.services.email_service import email_service

logger = logging.getLogger(__name__)


class EmailIngestService:
    """
    Service for managing email ingest endpoints and verified senders.
    
    This service coordinates between the email service and database operations,
    ensuring proper user isolation through RLS policies.
    """
    
    def __init__(self):
        """Initialize the email ingest service."""
        logger.info("Email ingest service initialized")
    
    def enable_email_ingest(self, user_jwt: str, user_id: str) -> Dict:
        """
        Enable email ingest for a user and generate unique alias.
        
        Args:
            user_jwt: User's JWT token for RLS
            user_id: User's ID from authentication
            
        Returns:
            Dictionary with email settings including the generated alias
            
        Raises:
            ValueError: If alias generation fails or user already has endpoint
        """
        try:
            # Create user-scoped client
            user_client = supabase_service._create_user_client(user_jwt)
            
            # Check if user already has an endpoint
            result = user_client.table("email_ingest_endpoints")\
                .select("*")\
                .eq("user_id", user_id)\
                .execute()
            
            if result.data:
                # User already has an endpoint, just activate it
                endpoint = result.data[0]
                if not endpoint['is_active']:
                    # Reactivate existing endpoint
                    user_client.table("email_ingest_endpoints")\
                        .update({"is_active": True, "updated_at": datetime.utcnow().isoformat()})\
                        .eq("id", endpoint['id'])\
                        .execute()
                    logger.info(f"Reactivated email endpoint for user {user_id}")
                
                return {
                    "enabled": True,
                    "email_alias": endpoint['full_address'],
                    "default_agent_id": endpoint.get('default_agent_id'),
                    "created_at": endpoint['created_at']
                }
            
            # Generate unique local part for email alias
            # Format: u_{first 13 chars of uuid without hyphens}
            local_part = f"u_{uuid.uuid4().hex[:13]}"
            
            # Create new endpoint
            new_endpoint = {
                "user_id": user_id,
                "local_part": local_part,
                "domain": config.EMAIL_INGEST_DOMAIN,
                "is_active": True,
                "default_agent_id": None,  # Will be set later if needed
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            result = user_client.table("email_ingest_endpoints")\
                .insert(new_endpoint)\
                .execute()
            
            if not result.data:
                raise ValueError("Failed to create email endpoint")
            
            endpoint = result.data[0]
            logger.info(f"Created email endpoint for user {user_id}: {endpoint['full_address']}")
            
            return {
                "enabled": True,
                "email_alias": endpoint['full_address'],
                "default_agent_id": None,
                "created_at": endpoint['created_at']
            }
            
        except Exception as e:
            logger.error(f"Failed to enable email ingest for user {user_id}: {str(e)}")
            raise ValueError(f"Failed to enable email ingest: {str(e)}")
    
    def disable_email_ingest(self, user_jwt: str, user_id: str) -> bool:
        """
        Disable email ingest by setting is_active=false.
        
        Args:
            user_jwt: User's JWT token for RLS
            user_id: User's ID from authentication
            
        Returns:
            True if successful
        """
        try:
            # Create user-scoped client
            user_client = supabase_service._create_user_client(user_jwt)
            
            result = user_client.table("email_ingest_endpoints")\
                .update({"is_active": False, "updated_at": datetime.utcnow().isoformat()})\
                .eq("user_id", user_id)\
                .execute()
            
            logger.info(f"Disabled email endpoint for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to disable email ingest for user {user_id}: {str(e)}")
            return False
    
    def add_verified_sender(
        self,
        user_jwt: str,
        user_id: str,
        email: str
    ) -> Dict:
        """
        Add new sender and send verification email.
        
        Args:
            user_jwt: User's JWT token for RLS
            user_id: User's ID from authentication
            email: Email address to verify
            
        Returns:
            Dictionary with sender record (id, email, status)
            
        Raises:
            ValueError: If email is invalid or already exists
        """
        try:
            # Create user-scoped client
            user_client = supabase_service._create_user_client(user_jwt)
            
            # Normalize email to lowercase for comparison
            email_lower = email.lower().strip()
            
            # Validate email format (basic check)
            if '@' not in email_lower or '.' not in email_lower.split('@')[1]:
                raise ValueError("Invalid email format")
            
            # Check for duplicates (case-insensitive)
            result = user_client.table("verified_senders")\
                .select("*")\
                .eq("user_id", user_id)\
                .execute()
            
            if result.data:
                for sender in result.data:
                    if sender['email'].lower() == email_lower:
                        raise ValueError("Email address already added")
            
            # Generate verification token
            token = str(uuid.uuid4())
            expires_at = datetime.utcnow() + timedelta(hours=config.EMAIL_VERIFICATION_EXPIRY_HOURS)
            
            # Create verified_senders record
            new_sender = {
                "user_id": user_id,
                "email": email_lower,
                "status": "pending",
                "verification_token": token,
                "token_expires_at": expires_at.isoformat(),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            result = user_client.table("verified_senders")\
                .insert(new_sender)\
                .execute()
            
            if not result.data:
                raise ValueError("Failed to create sender record")
            
            sender = result.data[0]
            
            # Get user's email alias for the verification email
            endpoint_result = user_client.table("email_ingest_endpoints")\
                .select("full_address")\
                .eq("user_id", user_id)\
                .execute()
            
            user_alias = endpoint_result.data[0]['full_address'] if endpoint_result.data else "your alias"
            
            # Send verification email
            email_sent = email_service.send_verification_email(
                to=email_lower,
                token=token,
                user_alias=user_alias
            )
            
            if not email_sent:
                logger.warning(f"Verification email failed to send to {email_lower}")
            
            logger.info(f"Added sender {email_lower} for user {user_id}, status: pending")
            
            return {
                "id": sender['id'],
                "email": sender['email'],
                "status": sender['status'],
                "created_at": sender['created_at']
            }
            
        except ValueError as e:
            raise e
        except Exception as e:
            logger.error(f"Failed to add verified sender for user {user_id}: {str(e)}")
            raise ValueError(f"Failed to add sender: {str(e)}")
    
    def verify_sender(self, token: str) -> Tuple[bool, str]:
        """
        Verify sender using token from email link.
        
        This is a system-level operation that uses the service role key to bypass RLS,
        since users click verification links before they're logged in.
        
        Args:
            token: Verification token from email (UUID format)
            
        Returns:
            Tuple of (success: bool, message: str)
            
        Security:
            - Uses service role key to bypass RLS (appropriate for system operation)
            - Tokens are random UUIDs (unguessable)
            - Tokens expire after 24 hours
            - Tokens are single-use (cleared after verification)
        """
        try:
            # Use SERVICE ROLE key to bypass RLS (this is a system-level operation)
            from supabase import create_client
            client = create_client(
                supabase_service.supabase_url,
                supabase_service.supabase_service_key  # Service role key, not anon key
            )
            
            # Look up token
            result = client.table("verified_senders")\
                .select("*")\
                .eq("verification_token", token)\
                .execute()
            
            if not result.data:
                logger.warning(f"Verification failed: token not found - {token[:8]}...")
                return (False, "Invalid or expired verification link")
            
            sender = result.data[0]
            sender_email = sender['email']
            user_id = sender['user_id']
            
            # Check if already verified
            if sender['status'] == 'verified':
                logger.info(f"Token already used for sender {sender_email} (user: {user_id})")
                return (True, "Email address already verified")
            
            # Check expiry with timezone-aware comparison
            token_expires_at = sender.get('token_expires_at')
            if not token_expires_at:
                logger.error(f"Token missing expiry for sender {sender_email}")
                return (False, "Invalid verification link")
            
            # Parse expiry time (handle both Z and +00:00 formats)
            expires_at = datetime.fromisoformat(token_expires_at.replace('Z', '+00:00'))
            
            # Create timezone-aware UTC now for comparison
            from datetime import timezone
            now_utc = datetime.now(timezone.utc)
            
            if now_utc > expires_at:
                logger.warning(
                    f"Verification failed: token expired for {sender_email} "
                    f"(expired: {expires_at.isoformat()}, now: {now_utc.isoformat()})"
                )
                return (False, "Verification link has expired. Please request a new one.")
            
            # Mark as verified and clear token (single-use)
            update_result = client.table("verified_senders")\
                .update({
                    "status": "verified",
                    "verification_token": None,  # Clear token for single-use
                    "token_expires_at": None,    # Clear expiry
                    "verified_at": now_utc.isoformat(),
                    "updated_at": now_utc.isoformat()
                })\
                .eq("id", sender['id'])\
                .execute()
            
            if not update_result.data:
                logger.error(f"Failed to update verification status for sender {sender_email}")
                return (False, "Verification failed. Please try again.")
            
            logger.info(
                f"Successfully verified sender {sender_email} for user {user_id} "
                f"(token: {token[:8]}...)"
            )
            
            return (True, "Email address verified successfully!")
            
        except Exception as e:
            logger.error(f"Verification failed with exception: {str(e)}", exc_info=True)
            return (False, "Verification failed. Please try again.")
    
    def check_rate_limit(self, user_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if user is within rate limits for job creation.
        
        Args:
            user_id: User's ID
            
        Returns:
            Tuple of (allowed: bool, error_message: Optional[str])
        """
        try:
            # Count jobs created in last 24 hours (exclude discarded)
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            
            result = supabase_service.supabase.table("email_jobs")\
                .select("id", count="exact")\
                .eq("user_id", user_id)\
                .gte("created_at", cutoff_time.isoformat())\
                .neq("status", "discarded")\
                .execute()
            
            job_count = result.count if hasattr(result, 'count') else len(result.data)
            
            if job_count >= config.EMAIL_RATE_LIMIT_JOBS_PER_DAY:
                error_msg = f"Rate limit exceeded. Maximum {config.EMAIL_RATE_LIMIT_JOBS_PER_DAY} jobs per 24 hours."
                logger.warning(f"Rate limit exceeded for user {user_id}: {job_count} jobs")
                return (False, error_msg)
            
            return (True, None)
            
        except Exception as e:
            logger.error(f"Failed to check rate limit for user {user_id}: {str(e)}")
            # On error, allow the request (fail open for better UX)
            return (True, None)
    
    def get_user_settings(self, user_jwt: str, user_id: str) -> Dict:
        """
        Get complete email ingest settings for a user.
        
        Args:
            user_jwt: User's JWT token for RLS
            user_id: User's ID from authentication
            
        Returns:
            Dictionary with all email settings matching frontend EmailIngestSettings type
        """
        try:
            # Create user-scoped client
            user_client = supabase_service._create_user_client(user_jwt)
            
            # Get endpoint
            endpoint_result = user_client.table("email_ingest_endpoints")\
                .select("*")\
                .eq("user_id", user_id)\
                .execute()
            
            # Get verified senders (full list, not just count)
            senders_result = user_client.table("verified_senders")\
                .select("id, email, status, created_at, verified_at")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .execute()
            
            # Format senders for frontend
            verified_senders = []
            for sender in (senders_result.data or []):
                verified_senders.append({
                    "id": sender["id"],
                    "email": sender["email"],
                    "is_verified": sender["status"] == "verified",
                    "created_at": sender["created_at"]
                })
            
            # Get usage stats (jobs in last 24 hours)
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            jobs_result = user_client.table("email_jobs")\
                .select("id", count="exact")\
                .eq("user_id", user_id)\
                .gte("created_at", cutoff_time.isoformat())\
                .neq("status", "discarded")\
                .execute()
            
            jobs_count = jobs_result.count if hasattr(jobs_result, 'count') else len(jobs_result.data)
            
            # Build response matching frontend EmailIngestSettings type
            if endpoint_result.data:
                endpoint = endpoint_result.data[0]
                return {
                    "endpoint": {
                        "id": endpoint["id"],
                        "full_address": endpoint["full_address"],
                        "is_active": endpoint["is_active"],
                        "default_agent_id": endpoint.get("default_agent_id")
                    },
                    "verified_senders": verified_senders,
                    "usage_summary": {
                        "jobs_last_24h": jobs_count,
                        "rate_limit": config.EMAIL_RATE_LIMIT_JOBS_PER_DAY
                    }
                }
            else:
                # No endpoint created yet
                return {
                    "endpoint": None,
                    "verified_senders": [],
                    "usage_summary": {
                        "jobs_last_24h": 0,
                        "rate_limit": config.EMAIL_RATE_LIMIT_JOBS_PER_DAY
                    }
                }
                
        except Exception as e:
            logger.error(f"Failed to get settings for user {user_id}: {str(e)}")
            # Return safe default matching frontend type
            return {
                "endpoint": None,
                "verified_senders": [],
                "usage_summary": {
                    "jobs_last_24h": 0,
                    "rate_limit": config.EMAIL_RATE_LIMIT_JOBS_PER_DAY
                }
            }
    
    def get_verified_senders(self, user_jwt: str, user_id: str) -> List[Dict]:
        """
        Get list of verified senders for a user.
        
        Args:
            user_jwt: User's JWT token for RLS
            user_id: User's ID from authentication
            
        Returns:
            List of sender dictionaries
        """
        try:
            # Create user-scoped client
            user_client = supabase_service._create_user_client(user_jwt)
            
            result = user_client.table("verified_senders")\
                .select("id, email, status, created_at, verified_at")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"Failed to get verified senders for user {user_id}: {str(e)}")
            return []
    
    def remove_verified_sender(self, user_jwt: str, user_id: str, sender_id: str) -> bool:
        """
        Remove a verified sender.
        
        Args:
            user_jwt: User's JWT token for RLS
            user_id: User's ID from authentication
            sender_id: ID of sender to remove
            
        Returns:
            True if successful
        """
        try:
            # Create user-scoped client
            user_client = supabase_service._create_user_client(user_jwt)
            
            result = user_client.table("verified_senders")\
                .delete()\
                .eq("id", sender_id)\
                .eq("user_id", user_id)\
                .execute()
            
            logger.info(f"Removed sender {sender_id} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove sender {sender_id} for user {user_id}: {str(e)}")
            return False
    
    def update_default_agent(
        self,
        user_jwt: str,
        user_id: str,
        agent_id: Optional[str]
    ) -> bool:
        """
        Update the default agent for email-submitted documents.
        
        Args:
            user_jwt: User's JWT token for RLS
            user_id: User's ID from authentication
            agent_id: Agent ID to set as default (None to clear)
            
        Returns:
            True if successful
        """
        try:
            # Create user-scoped client
            user_client = supabase_service._create_user_client(user_jwt)
            
            result = user_client.table("email_ingest_endpoints")\
                .update({
                    "default_agent_id": agent_id,
                    "updated_at": datetime.utcnow().isoformat()
                })\
                .eq("user_id", user_id)\
                .execute()
            
            logger.info(f"Updated default agent to {agent_id} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update default agent for user {user_id}: {str(e)}")
            return False


# Global instance for easy import
email_ingest_service = EmailIngestService()
