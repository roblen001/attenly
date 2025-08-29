# app/routers/auth.py
from fastapi import APIRouter
from app.core.deps import get_current_user
from fastapi import Depends

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
