"""Home to resuable dependencies files that are used with Depends(...) FastApi.

Depends() basically means: “FastAPI, before running this endpoint, call this function and give me its return value.”
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.db import get_db
from app import models

def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    uid = request.session.get("user_id")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = db.get(models.User, uid)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user")

    return user