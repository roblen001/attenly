import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Request, Depends
from fastapi.responses import JSONResponse
import json
from pathlib import Path
from typing import List
import hashlib
from app.schemas import Agent
from app.models import User
from app.core.deps import get_current_user
import uuid

# Import document processing services
from app.services.document_processor import DocumentProcessor
from app.services.vector_store import vector_store_manager # In user-based storage, we use a global manager for vector store operations

router = APIRouter(prefix="/agents", tags=["agents"])

# In-memory storage for uploaded files (user-based)
uploaded_files_storage = {}

# Initialize document processor
document_processor = DocumentProcessor()

def calculate_content_hash(content: bytes) -> str:
    """Calculate SHA-256 hash of file content for duplicate detection"""
    return hashlib.sha256(content).hexdigest()

def find_duplicate_file(user_id: str, content_hash: str) -> dict:
    """Find existing file with same content hash in user's session"""
    if user_id not in uploaded_files_storage:
        return None
    
    for file_id, file_record in uploaded_files_storage[user_id].items():
        if file_record.get("content_hash") == content_hash:
            return file_record
    
    return None

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

@router.post("/files/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """Upload multiple files and process them through the document pipeline"""
    from app.routers.auth import user_is  # Temporary import for user_ variable
    
    user_id = user_is
    # print(current_user)
    # user_id = current_user.id

    # Initialize user storage if not exists
    if user_id not in uploaded_files_storage:
        uploaded_files_storage[user_id] = {}
    
    # Get vector store for this user
    vector_store = vector_store_manager.get_store(user_id)
    uploaded_files = []
    processing_results = []
    
    for file in files:
        file_result = None
        try:
            # Read file content
            content = await file.read()
            
            # Calculate content hash for duplicate detection
            content_hash = calculate_content_hash(content)
            
            # Check for duplicate file
            duplicate_file = find_duplicate_file(user_id, content_hash)
            if duplicate_file:
                logging.info(f"Duplicate file detected: {file.filename} matches existing file {duplicate_file['name']}")
                print(f"Duplicate file detected: {file.filename} matches existing file {duplicate_file['name']}")
                
                # Create a unique ID for the duplicate file entry
                duplicate_file_id = str(uuid.uuid4())
                
                # Create a separate file record for the duplicate (without storing content again)
                duplicate_file_record = {
                    "id": duplicate_file_id,
                    "name": file.filename,
                    "content_hash": content_hash,
                    "size": len(content),
                    "type": file.content_type,
                    "status": "duplicate",
                    "original_file_id": duplicate_file["id"],  # Reference to original file
                    "error": f"Duplicate of existing file '{duplicate_file['name']}'"
                }
                
                # Store the duplicate file record (but don't store content or process)
                uploaded_files_storage[user_id][duplicate_file_id] = duplicate_file_record
                
                # Add duplicate file info to results
                file_result = {
                    "id": duplicate_file_id,
                    "name": file.filename,
                    "size": len(content),
                    "type": file.content_type or "application/pdf",
                    "status": "duplicate",
                    "error": f"Duplicate of existing file '{duplicate_file['name']}'"
                }
                uploaded_files.append(file_result)
                continue  # Skip to next file instead of raising exception
            
            # Validate document using document processor
            validation_result = document_processor.validate_document(content, file.filename)
            
            if not validation_result["valid"]:
                # Handle validation failure gracefully
                file_result = {
                    "id": str(uuid.uuid4()),
                    "name": file.filename,
                    "size": len(content),
                    "type": file.content_type or "application/pdf",
                    "status": "failed",
                    "error": f"Validation failed: {', '.join(validation_result['errors'])}"
                }
                uploaded_files.append(file_result)
                continue  # Skip to next file instead of raising exception
            
            # Create file record with initial processing status
            file_id = str(uuid.uuid4())
            file_record = {
                "id": file_id,
                "name": file.filename,
                "content_hash": content_hash,  # Store content hash
                "size": len(content),
                "type": file.content_type,
                "content": content,
                "status": "processing"  # Changed from "uploaded" to "processing"
            }
            
            # Store file
            uploaded_files_storage[user_id][file_id] = file_record
            
            # Process document through pipeline
            try:
                processing_result = await document_processor.process_document(
                    file_id=file_id,
                    content=content,
                    filename=file.filename,
                    vector_store=vector_store
                )
                print(f"Processing result for {file.filename}: {processing_result}")
                
                if processing_result["success"]:
                    file_record["status"] = "uploaded"
                    file_record["processing_stats"] = processing_result["processing_stats"]
                    file_record["chunk_statistics"] = processing_result["chunk_statistics"]
                else:
                    file_record["status"] = "failed"
                    file_record["error"] = processing_result["error"]
                
                processing_results.append(processing_result)
                
            except Exception as e:
                logging.error(f"Failed to process document {file.filename}: {e}")
                file_record["status"] = "failed"
                file_record["error"] = str(e)
                processing_results.append({
                    "success": False,
                    "document_id": file_id,
                    "filename": file.filename,
                    "error": str(e)
                })
            
            # Add to response (without content)
            file_result = {
                "id": file_id,
                "name": file.filename,
                "size": len(content),
                "type": file.content_type or "application/pdf",
                "status": file_record["status"],
                "error": file_record.get("error")
            }
            uploaded_files.append(file_result)
            
        except Exception as e:
            # Handle any unexpected errors gracefully
            logging.error(f"Unexpected error processing file {file.filename}: {e}")
            file_result = {
                "id": str(uuid.uuid4()),
                "name": file.filename,
                "size": 0,
                "type": file.content_type or "application/pdf",
                "status": "failed",
                "error": f"Unexpected error: {str(e)}"
            }
            uploaded_files.append(file_result)
    
    # Compile response
    successful_uploads = [f for f in uploaded_files if f["status"] == "uploaded"]
    failed_uploads = [f for f in uploaded_files if f["status"] == "failed"]
    duplicate_uploads = [f for f in uploaded_files if f["status"] == "duplicate"]
    
    # Create detailed response message
    message_parts = [f"Processed {len(uploaded_files)} files"]
    if successful_uploads:
        message_parts.append(f"{len(successful_uploads)} successful")
    if failed_uploads:
        message_parts.append(f"{len(failed_uploads)} failed")
    if duplicate_uploads:
        message_parts.append(f"{len(duplicate_uploads)} duplicates")
    
    response_message = ": ".join([message_parts[0], ", ".join(message_parts[1:])])
    
    return {
        "files": uploaded_files,
        "message": response_message,
        "processing_summary": {
            "total_files": len(uploaded_files),
            "successful": len(successful_uploads),
            "failed": len(failed_uploads),
            "duplicates": len(duplicate_uploads),
            "newly_processed": len(successful_uploads),
            "total_chunks": sum(f.get("processing_stats", {}).get("l2_chunks", 0) for f in uploaded_files),
            "vector_store_available": vector_store.available
        }
    }

@router.delete("/files/{file_id}")
async def delete_file(file_id: str, current_user: User = Depends(get_current_user)):
    """Delete a specific file and its associated chunks from vector store"""
    #TODO: Temporary import for user_ variable
    from app.routers.auth import user_is  # Temporary import for user_ variable
    
    user_id = user_is
    
    if user_id not in uploaded_files_storage:
        raise HTTPException(status_code=404, detail="No files found for this user")
    
    if file_id not in uploaded_files_storage[user_id]:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get the file record to check if it's a duplicate
    file_record = uploaded_files_storage[user_id][file_id]
    
    # Get vector store for this user
    vector_store = vector_store_manager.get_store(user_id)
    
    chunks_removed = False
    
    # Only remove chunks if this is NOT a duplicate file
    if file_record.get("status") != "duplicate":
        # This is an original file, remove its chunks from vector store
        try:
            vector_store.delete_document_chunks(file_id)
            logging.info(f"Deleted chunks for document {file_id} from vector store")
            chunks_removed = True
        except Exception as e:
            logging.error(f"Failed to delete chunks for document {file_id}: {e}")
            # Continue with file deletion even if vector store cleanup fails
    else:
        # This is a duplicate file, no chunks to remove (they belong to the original)
        logging.info(f"Skipping chunk deletion for duplicate file {file_id}")
    
    # Remove file from storage
    deleted_file = uploaded_files_storage[user_id].pop(file_id)
    
    return {
        "message": f"File {deleted_file['name']} deleted successfully",
        "file_id": file_id,
        "chunks_removed": chunks_removed
    }

@router.get("/files")
async def list_files(current_user: User = Depends(get_current_user)):
    """List all uploaded files for the current user"""
    user_id = current_user.id
    
    if user_id not in uploaded_files_storage:
        return {"files": []}
    
    files = []
    for file_id, file_record in uploaded_files_storage[user_id].items():
        files.append({
            "id": file_record["id"],
            "name": file_record["name"],
            "size": file_record["size"],
            "type": file_record["type"],
            "status": file_record["status"]
        })
    
    return {"files": files}

@router.post("/{agent_id}/process")
async def process_agent_documents(agent_id: str, current_user: User = Depends(get_current_user)):
    """Process uploaded documents with specific agent for data extraction"""
    user_id = current_user.id
    
    # Get agent configuration
    try:
        agent = get_agent_by_id(agent_id)
    except HTTPException as e:
        raise e
    
    # Check if there are uploaded files for this user
    if user_id not in uploaded_files_storage or not uploaded_files_storage[user_id]:
        raise HTTPException(status_code=400, detail="No documents uploaded for processing")
    
    # Get vector store for this user
    vector_store = vector_store_manager.get_store(user_id)
    
    if not vector_store.available:
        raise HTTPException(status_code=503, detail="Vector search not available - please ensure ChromaDB is installed")
    
    # Get list of successfully processed documents
    succesfully_uploaded_files = [
        file_record for file_record in uploaded_files_storage[user_id].values()
        if file_record["status"] == "uploaded"
    ]
    
    if not succesfully_uploaded_files:
        raise HTTPException(status_code=400, detail="No successfully uploaded documents available for agent processing")
    
    try:
        # TODO: For now, return a placeholder response since we haven't implemented LLM integration yet
        # This will be replaced with actual LLM processing in the next step
        
        document_ids = [file_record["id"] for file_record in succesfully_uploaded_files]
        
        # Get vector store statistics
        vector_stats = vector_store.get_session_statistics()
        
        # Placeholder for extracted data - will be replaced with actual LLM extraction
        # TODO: Batch processing of prompts
        extracted_data = {}
        for question in agent["questions"]:
            # Simulate data extraction for each question
            extracted_data[question["placeholder"]] = f"[Extracted data for: {question['prompt']}]"
        
        return {
            "success": True,
            "agent_id": agent_id,
            "agent_name": agent["name"],
            "processed_documents": len(succesfully_uploaded_files),
            "document_ids": document_ids,
            "vector_store_stats": vector_stats,
            "extracted_data": extracted_data,
            "questions_processed": len(agent["questions"]),
            "status": "completed",
            "message": "Document processing completed successfully (using placeholder data - LLM integration pending)"
        }
        
    except Exception as e:
        logging.error(f"Failed to process documents with agent {agent_id}: {e}")
        return {
            "success": False,
            "agent_id": agent_id,
            "error": str(e),
            "status": "failed"
        }


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
