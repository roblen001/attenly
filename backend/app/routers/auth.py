# app/routers/auth.py
from fastapi import APIRouter, HTTPException
from app.core.deps import get_current_user
from fastapi import Depends
from app.client import supabase_client

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.get("/me")
async def get_current_user_info(current_user = Depends(get_current_user)):
    """Get current authenticated user information from Supabase"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "user_metadata": current_user.user_metadata,
        "created_at": current_user.created_at
    }

@router.get("/users")
async def get_users():
    if supabase_client is None:
        raise HTTPException(status_code=503, detail="Supabase client is not configured")

    response = supabase_client.table("users").select("*").execute()
    return response.data
