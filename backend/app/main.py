# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.db import Base, engine
from .routers import auth
from pathlib import Path
from backend.app.config import SUPABASE_URL

app = FastAPI(title="Attenly", version="0.1.0")

# TODO: ONLLY FOR DEV MODE
Base.metadata.create_all(bind=engine)


# Add session middleware for authentication
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-change-in-production")

# CORS, some browser security shit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", SUPABASE_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)


@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
