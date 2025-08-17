import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse
import json
from pathlib import Path
from typing import List
from app.schemas import Agent
import uuid

router = APIRouter(prefix="/agents", tags=["agents"])

# In-memory storage for uploaded files (session-based)
uploaded_files_storage = {}

@router.get("/prebuilt", response_model=list[Agent])
def list_prebuilt_agents():
    """Get all prebuilt agents from JSON file"""
    try:
        # Path to the prebuilt agents JSON file
        data_path = Path(__file__).parent.parent / "seeds" / "prebuilt_agents.json"
        
        if not data_path.exists():
            raise HTTPException(status_code=404, detail="Prebuilt agents file not found")
        
        # Load and parse JSON
        items = json.loads(data_path.read_text(encoding="utf-8"))
        
        # Transform data to match schema (convert snake_case to camelCase if needed)
        agents = []
        for item in items:
            agent = {
                "id": item["slug"],  # Use slug as ID for prebuilt agents
                "name": item["name"],
                "description": item.get("description"),
                "reportTemplate": item.get("reportTemplate"),
                "questions": item.get("questions", [])
            }
            agents.append(agent)
        
        return agents
        
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse prebuilt agents JSON: {e}")
        raise HTTPException(status_code=500, detail="Invalid JSON format in prebuilt agents file")
    except Exception as e:
        logging.error(f"Error loading prebuilt agents: {e}")
        raise HTTPException(status_code=500, detail="Failed to load prebuilt agents")

# TODO: Modify this later with supabase
def get_session_id(request: Request) -> str:
    """Get or create session ID for file storage"""
    session_id = request.session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        request.session["session_id"] = session_id
    return session_id

@router.post("/files/upload")
async def upload_files(request: Request, files: List[UploadFile] = File(...)):
    """Upload multiple PDF files"""
    session_id = get_session_id(request)
    
    # Initialize session storage if not exists
    if session_id not in uploaded_files_storage:
        uploaded_files_storage[session_id] = {}
    
    uploaded_files = []
    max_file_size = 10 * 1024 * 1024  # 10MB in bytes
    
    for file in files:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail=f"Only PDF files are allowed. {file.filename} is not a PDF.")
        
        # Read file content to check size
        content = await file.read()
        if len(content) > max_file_size:
            raise HTTPException(status_code=400, detail=f"File {file.filename} exceeds 10MB limit.")
        
        # Create file record
        file_id = str(uuid.uuid4())
        file_record = {
            "id": file_id,
            "name": file.filename,
            "size": len(content),
            "type": file.content_type,
            "content": content,
            "status": "uploaded"
        }
        
        # Store file
        uploaded_files_storage[session_id][file_id] = file_record
        
        # Add to response (without content)
        uploaded_files.append({
            "id": file_id,
            "name": file.filename,
            "size": len(content),
            "type": file.content_type or "application/pdf",
            "status": "uploaded"
        })
    
    return {"files": uploaded_files, "message": f"Successfully uploaded {len(uploaded_files)} files"}

@router.delete("/files/{file_id}")
async def delete_file(request: Request, file_id: str):
    """Delete a specific file"""
    session_id = get_session_id(request)
    
    if session_id not in uploaded_files_storage:
        raise HTTPException(status_code=404, detail="No files found for this session")
    
    if file_id not in uploaded_files_storage[session_id]:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Remove file from storage
    deleted_file = uploaded_files_storage[session_id].pop(file_id)
    
    return {"message": f"File {deleted_file['name']} deleted successfully"}

@router.get("/files")
async def list_files(request: Request):
    """List all uploaded files for the current session"""
    session_id = get_session_id(request)
    
    if session_id not in uploaded_files_storage:
        return {"files": []}
    
    files = []
    for file_id, file_record in uploaded_files_storage[session_id].items():
        files.append({
            "id": file_record["id"],
            "name": file_record["name"],
            "size": file_record["size"],
            "type": file_record["type"],
            "status": file_record["status"]
        })
    
    return {"files": files}

@router.get("/{agent_id}", response_model=Agent)
def get_agent_by_id(agent_id: str):
    """Get a specific agent by ID (handles both prebuilt and custom agents)"""
    try:
        # Check if it's a prebuilt agent (you can modify this logic later)
        # For now, assume prebuilt agents are in the JSON file
        # Later you can add logic like: if agent_id.startswith('prebuilt-') or check database first
        
        # Try prebuilt agents first
        data_path = Path(__file__).parent.parent / "seeds" / "prebuilt_agents.json"
        
        if data_path.exists():
            items = json.loads(data_path.read_text(encoding="utf-8"))
            
            # Find the specific agent in prebuilt
            for item in items:
                if item["slug"] == agent_id:
                    agent = {
                        "id": item["slug"],
                        "name": item["name"],
                        "description": item.get("description"),
                        "reportTemplate": item.get("reportTemplate"),
                        "questions": item.get("questions", [])
                    }
                    return agent
        
        # TODO: Add database lookup for custom agents here
        # Example:
        # db_agent = get_custom_agent_from_db(agent_id)
        # if db_agent:
        #     return db_agent
        
        # Agent not found in either prebuilt or database
        raise HTTPException(status_code=404, detail=f"Agent with ID '{agent_id}' not found")
        
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse prebuilt agents JSON: {e}")
        raise HTTPException(status_code=500, detail="Invalid JSON format in prebuilt agents file")
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logging.error(f"Error loading agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load agent")
