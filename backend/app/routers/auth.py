# app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import uuid

from app.db import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas import UserCreate, UserOut
from app.security import hash_password  # cant store passwords that are not hashed

# TODO revise
from fastapi import APIRouter, Request, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse

from app.client import supabase_client

import supabase
from app.schemas import UserCreate

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup")
async def create_user(user: UserCreate):
    response = supabase_client.table("users").insert(user.dict()).execute()
    return response.data


@router.get("/me", response_model=UserOut)
async def get_users():
    response = supabase_client.table("users").select("*").execute()
    return response.data


@router.post("/logout")
def logout(request: Request):
    # Clear the session
    request.session.clear()
    return {"message": "Successfully logged out"}
