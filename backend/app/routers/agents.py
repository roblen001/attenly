import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Request, Depends
from fastapi.responses import JSONResponse
import json
from pathlib import Path
from typing import List
import hashlib
from app.schemas import Agent
from app.core.deps import get_current_user
import uuid

# Import document processing services
from app.services.document_processor import DocumentProcessor
from app.services.vector_store import vector_store_manager # In user-based storage, we use a global manager for vector store operations
from app.services.report_service import report_service
from app.services.pdf_generator import pdf_generator

router = APIRouter(prefix="/agents", tags=["agents"])

# In-memory storage for uploaded files (user-based)
uploaded_files_storage = {}

# In-memory storage for cached report data (user-based)
report_cache_storage = {}

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

def get_cached_report(user_id: str, agent_id: str) -> dict:
    """Retrieve cached report data for user and agent"""
    if user_id not in report_cache_storage:
        return None
    
    if agent_id not in report_cache_storage[user_id]:
        return None
    
    cached_data = report_cache_storage[user_id][agent_id]
    logging.info(f"Retrieved cached report for user {user_id}, agent {agent_id}")
    return cached_data

def cache_report(user_id: str, agent_id: str, report_data: dict) -> None:
    """Store report data in cache for user and agent"""
    if user_id not in report_cache_storage:
        report_cache_storage[user_id] = {}
    
    # Store the complete report data
    report_cache_storage[user_id][agent_id] = {
        "report_data": report_data,
        "cached_at": report_data.get("generated_at"),
        "agent_id": agent_id,
        "document_ids": report_data.get("document_context", {}).get("document_ids", [])
    }
    
    logging.info(f"Cached report for user {user_id}, agent {agent_id}")

def clear_report_cache(user_id: str, agent_id: str = None) -> None:
    """Clear cached report data for user (specific agent or all agents)"""
    if user_id not in report_cache_storage:
        return
    
    if agent_id:
        # Clear specific agent cache
        if agent_id in report_cache_storage[user_id]:
            del report_cache_storage[user_id][agent_id]
            logging.info(f"Cleared cached report for user {user_id}, agent {agent_id}")
    else:
        # Clear all cached reports for user
        del report_cache_storage[user_id]
        logging.info(f"Cleared all cached reports for user {user_id}")

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
async def upload_files(files: List[UploadFile] = File(...), current_user = Depends(get_current_user)):
    """Upload multiple files and process them through the document pipeline"""
    user_id = current_user.id

    # Initialize user storage if not exists
    if user_id not in uploaded_files_storage:
        uploaded_files_storage[user_id] = {}
    
    # Clear report cache when new files are uploaded (data has changed)
    clear_report_cache(user_id)
    
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

# This endpoint needs to be above file-specific delete to avoid path conflicts
@router.delete("/files/clear")
async def clear_all_files(current_user = Depends(get_current_user)):
    """Clear all uploaded files and vector store for current user"""
    user_id = current_user.id
    
    # Get counts before clearing for response
    files_count = 0
    if user_id in uploaded_files_storage:
        files_count = len(uploaded_files_storage[user_id])
    
    # Clear vector store
    try:
        vector_store_manager.cleanup_user_session(user_id)
        vector_store_cleared = True
        logging.info(f"Cleared vector store for user {user_id}")
    except Exception as e:
        logging.error(f"Failed to clear vector store for user {user_id}: {e}")
        vector_store_cleared = False
    
    # Clear uploaded files storage
    if user_id in uploaded_files_storage:
        del uploaded_files_storage[user_id]
        logging.info(f"Cleared uploaded files storage for user {user_id}")
    
    # Clear report cache when files are cleared (data has changed)
    # good safety measure but might not be strictly necessary since vector store is cleared
    clear_report_cache(user_id)
    
    return {
        "message": "All files and vector store cleared successfully",
        "user_id": user_id,
        "files_cleared": files_count,
        "vector_store_cleared": vector_store_cleared
    }

@router.delete("/files/{file_id}")
async def delete_file(file_id: str, current_user = Depends(get_current_user)):
    """Delete a specific file and its associated chunks from vector store"""
    user_id = current_user.id
    
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
async def list_files(current_user = Depends(get_current_user)):
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

@router.get("/documents/{document_id}/content")
async def get_document_content(document_id: str, current_user = Depends(get_current_user)):
    """Get the full content of a document for viewing"""
    user_id = current_user.id
    
    # Check if user has uploaded files
    if user_id not in uploaded_files_storage:
        raise HTTPException(status_code=404, detail="No documents found for this user")
    
    # Check if document exists
    if document_id not in uploaded_files_storage[user_id]:
        raise HTTPException(status_code=404, detail="Document not found")
    
    file_record = uploaded_files_storage[user_id][document_id]
    
    # Check if document was successfully processed
    if file_record["status"] != "uploaded":
        raise HTTPException(status_code=400, detail=f"Document not available for viewing. Status: {file_record['status']}")
    
    try:
        # Get the raw content
        content = file_record["content"]
        filename = file_record["name"]
        
        from app.services.pdf_parser import PDFProcessor
        pdf_processor = PDFProcessor()
        pdf_data = pdf_processor.process_pdf(content, filename)

        
        if not pdf_data or not pdf_data.get("pages"):
            raise HTTPException(status_code=500, detail="Failed to extract readable content from document")
        
        # Build full document text with page markers
        full_text = ""
        pages_info = []
        
        for page in pdf_data["pages"]:
            page_number = page["page_number"]
            page_content = page["markdown"]
            
            # Add page marker and content
            page_text = f"\n--- PAGE {page_number} ---\n{page_content}\n"
            full_text += page_text
            
            # Track page info for navigation
            pages_info.append({
                "page_number": page_number,
                "start_position": len(full_text) - len(page_text),
                "end_position": len(full_text),
                "content_length": len(page_content)
            })
        
        return {
            "document_id": document_id,
            "filename": filename,
            "full_text": full_text,
            "pages": pages_info,
            "total_pages": len(pdf_data["pages"]),
            "total_characters": len(full_text),
            "metadata": {
                "size": file_record["size"],
                "type": file_record["type"],
                "processing_stats": file_record.get("processing_stats", {})
            }
        }
        
    except Exception as e:
        logging.error(f"Failed to get content for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve document content: {str(e)}")

@router.post("/{agent_id}/process")
async def process_agent_documents(agent_id: str, current_user = Depends(get_current_user)):
    """Process uploaded documents with specific agent for data extraction and cache results"""
    user_id = current_user.id
    
    # Get agent configuration
    try:
        agent_dict = get_agent_by_id(agent_id)
        # Convert dictionary to Agent object for type safety
        agent = Agent(**agent_dict)
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
    successfully_uploaded_files = [
        file_record for file_record in uploaded_files_storage[user_id].values()
        if file_record["status"] == "uploaded"
    ]
    
    if not successfully_uploaded_files:
        raise HTTPException(status_code=400, detail="No successfully uploaded documents available for agent processing")
    
    try:
        # Generate report using report service (LLM processing happens here)
        document_ids = [file_record["id"] for file_record in successfully_uploaded_files]
        
        report_result = report_service.generate_report(
            agent=agent,
            vector_store=vector_store,
            document_ids=document_ids
        )
        
        if not report_result["success"]:
            raise HTTPException(status_code=500, detail=f"Document processing failed: {report_result.get('error', 'Unknown error')}")
        
        # Cache the report data immediately after generation
        cache_report(user_id, agent_id, report_result["report_data"])
        logging.info(f"Report generated and cached for user {user_id}, agent {agent_id}")
        
        return {
            "success": True,
            "agent_id": agent_id,
            "agent_name": agent.name,
            "processed_documents": len(successfully_uploaded_files),
            "document_ids": document_ids,
            "processing_stats": report_result["processing_stats"],
            "status": "completed",
            "message": "Document processing completed successfully with real LLM inference and cached for preview"
        }
        
    except ValueError as e:
        # Handle service-level errors (including LLM unavailability)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Failed to process documents with agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Document processing failed: {str(e)}")


@router.get("/{agent_id}/report")
async def get_agent_report(agent_id: str, current_user = Depends(get_current_user)):
    """Retrieve cached report data for an agent (no LLM processing)"""
    user_id = current_user.id
    
    # Get agent configuration
    try:
        agent_dict = get_agent_by_id(agent_id)
        # Convert dictionary to Agent object for type safety
        agent = Agent(**agent_dict)
    except HTTPException as e:
        raise e
    
    # Check for cached report data - this is the key change!
    cached_report = get_cached_report(user_id, agent_id)
    if not cached_report:
        raise HTTPException(
            status_code=400, 
            detail="No cached report data found. Please generate the report first by clicking 'Generate Report' button."
        )

    try:
        # Use cached report data directly - NO LLM calls
        report_data = cached_report["report_data"]
        
        logging.info(f"Retrieved cached report data for preview - user {user_id}, agent {agent_id}")
        
        return {
            "success": True,
            "report_id": f"cached_{agent_id}_{cached_report['cached_at']}",
            "agent_id": agent_id,
            "agent_name": agent.name,
            "report_data": report_data,
            "processing_stats": {
                "cached_at": cached_report["cached_at"],
                "document_ids": cached_report["document_ids"],
                "source": "cache"
            },
            "message": "Report retrieved from cache successfully"
        }
        
    except Exception as e:
        logging.error(f"Failed to retrieve cached report for agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve cached report: {str(e)}")


@router.get("/{agent_id}/pdf")
async def download_agent_report_pdf(
    agent_id: str,
    with_references: bool = False,
    current_user = Depends(get_current_user)
):
    """Download PDF report for an agent using cached data (no LLM regeneration)"""
    from fastapi.responses import StreamingResponse
    import io

    user_id = current_user.id

    # Get agent configuration
    try:
        agent_dict = get_agent_by_id(agent_id)
        # Convert dictionary to Agent object for type safety
        agent = Agent(**agent_dict)
    except HTTPException as e:
        raise e

    # Check for cached report data - this is the key change!
    cached_report = get_cached_report(user_id, agent_id)
    if not cached_report:
        raise HTTPException(
            status_code=400, 
            detail="No cached report data found. Please preview the report first before downloading PDF."
        )

    try:
        # Use cached report data directly - NO LLM calls
        report_data = cached_report["report_data"]
        
        logging.info(f"Using cached report data for PDF generation - user {user_id}, agent {agent_id}")

        # Generate PDF from cached data
        pdf_content = pdf_generator.generate_pdf_report(
            agent=agent,
            report_data=report_data,
            with_references=with_references
        )

        # Create streaming response
        pdf_buffer = io.BytesIO(pdf_content)

        # Generate filename
        references_suffix = "_with_references" if with_references else ""
        filename = f"{agent.name.replace(' ', '_')}_report{references_suffix}.pdf"

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logging.error(f"Failed to generate PDF from cached data for agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


@router.delete("/reports/{agent_id}/cache")
async def clear_report_cache_for_agent(agent_id: str, current_user = Depends(get_current_user)):
    """Clear cached report data for specific agent when user leaves preview"""
    user_id = current_user.id
    
    # Clear the specific agent's cached report
    clear_report_cache(user_id, agent_id)
    
    return {
        "message": f"Cached report data cleared for agent {agent_id}",
        "user_id": user_id,
        "agent_id": agent_id
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
                    agent_dict = {
                        "id": item["slug"],
                        "name": item["name"],
                        "description": item.get("description"),
                        "reportTemplate": item.get("reportTemplate"),
                        "questions": item.get("questions", [])
                    }
                    return agent_dict
        
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
