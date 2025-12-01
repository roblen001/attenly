"""
Agent loading service for centralized agent configuration retrieval.

Handles both prebuilt agents (from JSON) and custom agents (from database).
Used by both web endpoints (with user JWT) and background jobs (with service role).
"""
import logging
import json
from pathlib import Path
from typing import Optional
from app.schemas import Agent


logger = logging.getLogger(__name__)


def load_agent_by_id(agent_id: str, user_id: Optional[str] = None) -> Agent:
    """
    Load agent configuration by ID from prebuilt JSON or custom agents table.
    
    This function provides unified agent loading for both web requests (with user context)
    and background jobs (system-level access). It searches prebuilt agents first, then
    falls back to custom agents if user context is provided.
    
    Args:
        agent_id: Agent identifier (slug for prebuilt, UUID for custom)
        user_id: Optional user ID for custom agent access verification.
                 If provided, custom agents will be queried. If None, only
                 prebuilt agents are accessible (used in background jobs).
        
    Returns:
        Agent object with full configuration including questions
        
    Raises:
        ValueError: If agent not found or user lacks access
        
    Examples:
        # Web request with user context
        agent = load_agent_by_id("due-diligence", user_id="...")
        
        # Background job (prebuilt only)
        agent = load_agent_by_id("due-diligence")
        
        # Background job with user context (uses service role)
        agent = load_agent_by_id("custom-uuid", user_id="...")
    """
    # Step 1: Try prebuilt agents from JSON
    prebuilt_path = Path(__file__).parent.parent / "seeds" / "prebuilt_agents.json"
    
    if prebuilt_path.exists():
        try:
            items = json.loads(prebuilt_path.read_text(encoding="utf-8"))
            
            # Find the specific agent in prebuilt
            for item in items:
                if item["slug"] == agent_id:
                    # Found prebuilt agent - convert to Agent schema
                    agent_dict = {
                        "id": item["slug"],
                        "name": item["name"],
                        "description": item.get("description"),
                        "reportTemplate": item.get("reportTemplate"),
                        "questions": item.get("questions", [])
                    }
                    
                    logger.info(f"Loaded prebuilt agent: {agent_id}")
                    return Agent(**agent_dict)
                    
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse prebuilt agents JSON: {e}")
            raise ValueError("Invalid prebuilt agents configuration")
        except Exception as e:
            logger.error(f"Error reading prebuilt agents: {e}")
            # Continue to custom agent lookup
    
    # Step 2: Try custom agents from database (requires user_id)
    if user_id:
        try:
            from app.services.supabase_service import supabase_service
            
            # Use service role client to bypass RLS for background jobs
            # The get_agent_by_id_system method uses service role access
            agent_data = supabase_service.get_agent_by_id_system(agent_id, user_id)
            
            if agent_data:
                # Transform custom agent data to match Agent schema
                questions_out = []
                for q in agent_data.get("agent_questions", []):
                    questions_out.append({
                        "id": str(q["id"]),
                        "placeholder": q["placeholder"],
                        "prompt": q["prompt"]
                    })
                
                agent_dict = {
                    "id": str(agent_data["id"]),
                    "name": agent_data["name"],
                    "description": agent_data.get("description", ""),
                    "reportTemplate": agent_data["report_template"],
                    "questions": questions_out
                }
                
                logger.info(f"Loaded custom agent: {agent_id} for user {user_id}")
                return Agent(**agent_dict)
                
        except Exception as e:
            logger.warning(f"Failed to lookup custom agent {agent_id}: {e}")
            # Continue to not found error below
    
    # Step 3: Agent not found in either prebuilt or database
    if user_id:
        error_msg = f"Agent '{agent_id}' not found or you don't have access to it"
    else:
        error_msg = f"Agent '{agent_id}' not found in prebuilt agents"
    
    logger.error(f"Agent not found: {agent_id} (user_id: {user_id})")
    raise ValueError(error_msg)
