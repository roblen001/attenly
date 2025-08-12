# used in web applications to organize and manage user-related functionalities,
# such as registration, login, and profile management.
# They handle routing for user-specific URLs and actions,
# often interacting with a database to manage user data.

from fastapi import APIRouter, Request, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from backend.supabase.client import supabase
from ..models import User, UserCreate, UserUpdate


@router.post("/users")
async def create_user(user: UserCreate):
    response = supabase.table("users").insert(user.dict()).execute()
    return response.data


@router.get("/users")
async def get_users():
    response = supabase.table("users").select("*").execute()
    return response.data
