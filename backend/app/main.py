# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db import Base, engine
from app.routers import auth, agents
from pathlib import Path
from app.config import SUPABASE_URL

app = FastAPI(title="Attenly", version="0.1.0")

# TODO: ONLLY FOR DEV MODE
Base.metadata.create_all(bind=engine)


# CORS, some browser security shit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", SUPABASE_URL],
    allow_credentials=False,  # Changed to False since we're using Bearer tokens
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(agents.router)

@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
