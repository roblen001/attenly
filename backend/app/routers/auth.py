# app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import uuid

from app.db import get_db
from app.core.deps import get_current_user
from ..models import User
from ..schemas import UserCreate, UserOut
from ..security import hash_password # cant store passwords that are not hashed

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(user_in: UserCreate, request: Request, db: Session = Depends(get_db)):
    # Normalize email to lowercase to avoid duplicates like Bob@X.com vs bob@x.com
    email_norm = user_in.email.lower().strip()

    # Build model
    user = User(
        id=str(uuid.uuid4()),
        email=email_norm,
        full_name=user_in.full_name,
        hashed_password=hash_password(user_in.password),
        is_active=True,
        is_verified=False,
    )

    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Unique constraint violation on email
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    db.refresh(user)
    
    # Auto signin
    request.session.clear()
    request.session["user_id"] = user.id
    
    return user

@router.get("/me", response_model=UserOut)
def read_me(
    response: Response,
    current_user: User = Depends(get_current_user),
):
    # prevent caching of identity
    response.headers["Cache-Control"] = "no-store"
    return current_user

@router.post("/logout")
def logout(request: Request):
    # Clear the session
    request.session.clear()
    return {"message": "Successfully logged out"}
