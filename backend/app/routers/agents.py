import logging
import time
import re
from fastapi import APIRouter, HTTPException, UploadFile, File, Request, Depends, Header
from fastapi.responses import JSONResponse, Response
import json
from pathlib import Path
from typing import List, Optional
import hashlib
from app.schemas import Agent, SaveReportRequest, SavedReportOut, SavedReportDetailOut, UpdateSavedReportRequest, UpdateCachedReportRequest, CustomAgentOut, CreateCustomAgentRequest, UpdateCustomAgentRequest
from app.core.deps import get_current_user
from app.services.supabase_service import supabase_service
import uuid

# Import document processing services
from app.services.document_processor import DocumentProcessor
from app.services.vector_store import vector_store_manager # In user-based storage, we use a global manager for vector store operations
from app.services.report_service import report_service
from app.services.pdf_generator import pdf_generator

# Import performance monitoring
from app.services.performance_monitor import get_performance_monitor, time_operation, timed_operation

router = APIRouter(prefix="/agents", tags=["agents"])

# In-memory storage for uploaded files (user-based)
uploaded_files_storage = {}

# In-memory storage for cached report data (user-based)
report_cache_storage = {}

# In-memory storage for preloaded PDFs from saved reports (user-based)
# Structure: {user_id: {report_id: {document_id: {"content": bytes, "filename": str, "size": int, "loaded_at": float}}}}
preloaded_reports_cache = {}

# Initialize document processor
document_processor = DocumentProcessor()

def extract_jwt_token(authorization: Optional[str] = Header(None, alias="Authorization")) -> str:
    """Extract JWT access token from Authorization header"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return authorization.split(" ")[1]

def extract_auth_tokens(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_refresh_token: Optional[str] = Header(None, alias="X-Refresh-Token")
) -> tuple[str, str]:
    """
    Extract both access and refresh tokens from headers.
    
    Returns:
        Tuple of (access_token, refresh_token). Refresh token may be empty string.
    """
    access_token = extract_jwt_token(authorization)
    refresh_token = x_refresh_token or ""
    
    if not refresh_token:
        logging.warning("No refresh token provided - some Storage operations may fail")
    
    return access_token, refresh_token

def calculate_content_hash(content: bytes) -> str:
    """Calculate SHA-256 hash of file content for duplicate detection"""
    return hashlib.sha256(content).hexdigest()

def find_duplicate_file(user_id: str, content_hash: str) -> dict:
    """Find existing file with same content hash in user's session (excluding failed files)"""
    if user_id not in uploaded_files_storage:
        return None
    
    for file_id, file_record in uploaded_files_storage[user_id].items():
        if file_record.get("content_hash") == content_hash:
            # Allow reprocessing of files that failed - don't treat them as duplicates
            if file_record.get("status") == "failed":
                continue
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

def cache_report(user_id: str, agent_id: str, report_data: dict, ai_baseline_answers: dict = None) -> None:
    """Store report data AND AI baseline in cache for user and agent"""
    if user_id not in report_cache_storage:
        report_cache_storage[user_id] = {}
    
    # Store the complete report data with AI baseline
    report_cache_storage[user_id][agent_id] = {
        "report_data": report_data,
        "ai_baseline_answers": ai_baseline_answers,  # NEW: Store AI baseline for audit trail
        "cached_at": report_data.get("generated_at"),
        "agent_id": agent_id,
        "document_ids": report_data.get("document_context", {}).get("document_ids", [])
    }
    
    logging.info(f"Cached report for user {user_id}, agent {agent_id} with AI baseline: {ai_baseline_answers is not None}")

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

def get_pdf_document_content(file_record: dict, document_id: str) -> dict:
    """Extract content using PDFProcessor (reuses existing logic)"""
    from app.services.pdf_parser import PDFProcessor
    
    content = file_record["content"]
    filename = file_record["name"]
    
    pdf_processor = PDFProcessor()
    pdf_data = pdf_processor.process_pdf(content, filename)
    
    if not pdf_data or not pdf_data.get("pages"):
        raise HTTPException(status_code=500, detail="Failed to extract readable content from document")
    
    # Build full document text with page markers (same as existing logic)
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

def get_ocr_document_content(file_record: dict, document_id: str) -> dict:
    """Use stored OCR document data to avoid re-extraction"""
    
    filename = file_record["name"]
    
    # Use stored extracted data if available (avoids dual OCR processing)
    if "extracted_document_data" in file_record:
        logging.info(f"Using stored OCR document data for {document_id} (avoiding re-extraction)")
        ocr_data = file_record["extracted_document_data"]
    else:
        # No stored data available - this shouldn't happen for new uploads
        logging.error(f"No stored OCR document data found for {document_id}")
        raise HTTPException(status_code=500, detail="OCR document data not available - please re-upload the document")
    
    if not ocr_data or not ocr_data.get("pages"):
        raise HTTPException(status_code=500, detail="Failed to extract readable content from OCR document")
    
    # Build full document text with page markers (same format as PDF)
    full_text = ""
    pages_info = []
    
    for page in ocr_data["pages"]:
        page_number = page["page_number"]
        page_content = page["markdown"]
        
        # Add page marker and content (same format as PDF)
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
        "total_pages": len(ocr_data["pages"]),
        "total_characters": len(full_text),
        "metadata": {
            "size": file_record["size"],
            "type": file_record["type"],
            "processing_stats": file_record.get("processing_stats", {})
        }
    }

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
    performance_monitor = get_performance_monitor()

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
        # Start monitoring individual file processing
        file_metrics = None
        
        try:
            # Read file content with timing
            with time_operation("file_upload_read", {"filename": file.filename}):
                content = await file.read()
            
            # Start performance monitoring for this file
            file_metrics = performance_monitor.start_file_processing(
                file_id=str(uuid.uuid4()),
                filename=file.filename,
                file_size_bytes=len(content)
            )
            
            # Calculate content hash for duplicate detection
            with time_operation("hash_calculation", {"file_size_bytes": len(content)}) as timer:
                content_hash = calculate_content_hash(content)
                performance_monitor.update_file_metric(file_metrics.file_id, "hash_calculation_time", timer.stop().duration)
            
            # Check for duplicate file
            with time_operation("duplicate_check", {"hash": content_hash[:8]}) as timer:
                duplicate_file = find_duplicate_file(user_id, content_hash)
                performance_monitor.update_file_metric(file_metrics.file_id, "duplicate_check_time", timer.stop().duration)
            
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
                
                # Finish monitoring with duplicate status
                if file_metrics:
                    performance_monitor.finish_file_processing(file_metrics.file_id, success=True, error_message="Duplicate file")
                continue  # Skip to next file instead of raising exception
            
            # Validate document using document processor
            with time_operation("document_validation", {"filename": file.filename}) as timer:
                validation_result = document_processor.validate_document(content, file.filename)
                performance_monitor.update_file_metric(file_metrics.file_id, "validation_time", timer.stop().duration)
            
            if not validation_result["valid"]:
                # Handle validation failure gracefully
                error_message = f"Validation failed: {', '.join(validation_result['errors'])}"
                
                file_result = {
                    "id": str(uuid.uuid4()),
                    "name": file.filename,
                    "size": len(content),
                    "type": file.content_type or "application/pdf",
                    "status": "failed",
                    "error": error_message
                }
                uploaded_files.append(file_result)
                
                # Finish monitoring with failure
                if file_metrics:
                    performance_monitor.finish_file_processing(file_metrics.file_id, success=False, error_message=error_message)
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
            
            # Update file metrics with actual file ID
            if file_metrics:
                file_metrics.file_id = file_id
            
            # Process document through pipeline
            try:
                with time_operation("document_processing_pipeline", {"file_id": file_id, "filename": file.filename}) as timer:
                    processing_result = await document_processor.process_document(
                        file_id=file_id,
                        content=content,
                        filename=file.filename,
                        vector_store=vector_store
                    )
                    
                    # Update metrics with processing stats
                    if file_metrics and processing_result.get("processing_stats"):
                        stats = processing_result["processing_stats"]
                        performance_monitor.update_file_metric(file_metrics.file_id, "total_pages", stats.get("total_pages", 0))
                        performance_monitor.update_file_metric(file_metrics.file_id, "l1_chunks_created", stats.get("l1_chunks", 0))
                        performance_monitor.update_file_metric(file_metrics.file_id, "l2_chunks_created", stats.get("l2_chunks", 0))
                        performance_monitor.update_file_metric(file_metrics.file_id, "chunks_stored", stats.get("stored_chunks", 0))
                
                print(f"Processing result for {file.filename}: {processing_result}")
                
                if processing_result["success"]:
                    file_record["status"] = "uploaded"
                    
                    # Enhanced processing_stats to include content_type and processor_used
                    enhanced_processing_stats = processing_result["processing_stats"].copy()
                    enhanced_processing_stats["content_type"] = processing_result.get("content_type")
                    enhanced_processing_stats["processor_used"] = processing_result.get("processor_used")
                    
                    file_record["processing_stats"] = enhanced_processing_stats
                    file_record["chunk_statistics"] = processing_result["chunk_statistics"]
                    
                    # Store extracted document data to avoid re-extraction during content retrieval
                    if "document_data" in processing_result:
                        file_record["extracted_document_data"] = processing_result["document_data"]
                        processor_used = processing_result.get("processor_used", "")
                        logging.info(f"Stored extracted document data for {processor_used} file {file_id}")
                        
                        # Remove document_data from response to save memory - it's already stored server-side
                        # Frontend doesn't need this data; DocumentViewer makes a separate API call to retrieve it
                        del processing_result["document_data"]
                    
                    # Finish monitoring with success
                    if file_metrics:
                        performance_monitor.finish_file_processing(file_metrics.file_id, success=True)
                else:
                    error_message = processing_result["error"]
                    file_record["status"] = "failed"
                    file_record["error"] = error_message
                    
                    # Finish monitoring with failure
                    if file_metrics:
                        performance_monitor.finish_file_processing(file_metrics.file_id, success=False, error_message=error_message)
                
                processing_results.append(processing_result)
                
            except Exception as e:
                error_message = str(e)
                logging.error(f"Failed to process document {file.filename}: {e}")
                file_record["status"] = "failed"
                file_record["error"] = error_message
                
                # Finish monitoring with failure
                if file_metrics:
                    performance_monitor.finish_file_processing(file_metrics.file_id, success=False, error_message=error_message)
                
                processing_results.append({
                    "success": False,
                    "document_id": file_id,
                    "filename": file.filename,
                    "error": error_message
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
            error_message = f"Unexpected error: {str(e)}"
            logging.error(f"Unexpected error processing file {file.filename}: {e}")
            
            file_result = {
                "id": str(uuid.uuid4()),
                "name": file.filename,
                "size": 0,
                "type": file.content_type or "application/pdf",
                "status": "failed",
                "error": error_message
            }
            uploaded_files.append(file_result)
            
            # Finish monitoring with failure
            if file_metrics:
                performance_monitor.finish_file_processing(file_metrics.file_id, success=False, error_message=error_message)
    
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
    
    # Log performance summary for this batch
    if successful_uploads or failed_uploads:
        logging.info(f"🚀 Upload batch completed: {len(successful_uploads)} successful, {len(failed_uploads)} failed")
        if len(uploaded_files) >= 5:  # Log performance report for larger batches
            performance_monitor.log_performance_report(level=logging.INFO, last_n_files=10)
    
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
    """Get the full content of a document for viewing (processor-aware)"""
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
        # NEW: Detect which processor was used during original processing
        processing_stats = file_record.get("processing_stats", {})
        content_type = processing_stats.get("content_type", "pdf")
        processor_used = processing_stats.get("processor_used", "PDF Processor")
        
        logging.info(f"Retrieving content for document {document_id}: processor='{processor_used}', content_type='{content_type}'")
        
        # Route to appropriate processor-specific content retrieval
        if content_type == "pdf_ocr" or processor_used == "OCR Processor":
            # Use OCR content retrieval (reuses existing OCR logic)
            return get_ocr_document_content(file_record, document_id)
        if content_type == "pdf" or processor_used == "PDF Processor":
            return get_pdf_document_content(file_record, document_id)
        
    except HTTPException:
        # Re-raise HTTP exceptions (from helper functions)
        raise
    except Exception as e:
        logging.error(f"Failed to get content for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve document content: {str(e)}")

@router.get("/documents/{document_id}/file")
async def get_document_file(document_id: str, request: Request, current_user = Depends(get_current_user)):
    """Stream original PDF file for current session documents"""
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
        raise HTTPException(
            status_code=400,
            detail=f"Document not available. Status: {file_record['status']}"
        )
    
    # Check if this is an OCR document (no original PDF available)
    processing_stats = file_record.get("processing_stats", {})
    processor_used = processing_stats.get("processor_used", "")
    
    if "OCR" in processor_used:
        raise HTTPException(
            status_code=415,
            detail="This document was processed via OCR. Original PDF not available. Please use the text content viewer instead."
        )
    
    # Get PDF bytes
    pdf_bytes = file_record.get("content")
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="PDF content not found")
    
    # Prepare response with Range support for PDF seeking
    total_size = len(pdf_bytes)
    range_header = request.headers.get("Range")
    
    headers = {
        "Content-Type": "application/pdf",
        "Accept-Ranges": "bytes",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges"
    }
    
    # Handle Range requests for PDF seeking (used by PDF.js for navigation)
    if range_header and (match := re.match(r"bytes=(\d+)-(\d*)", range_header)):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else total_size - 1
        end = min(end, total_size - 1)
        
        return Response(
            content=pdf_bytes[start:end+1],
            status_code=206,  # Partial Content
            media_type="application/pdf",
            headers={
                **headers,
                "Content-Range": f"bytes {start}-{end}/{total_size}",
                "Content-Length": str(end - start + 1)
            }
        )
    
    # Return full PDF
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={**headers, "Content-Length": str(total_size)}
    )

@router.post("/{agent_id}/process")
async def process_agent_documents(agent_id: str, request: Request, current_user = Depends(get_current_user)):
    """Process uploaded documents with specific agent for data extraction and cache results"""
    user_id = current_user.id
    
    # Get agent configuration using internal helper (no dependency injection)
    try:
        # Extract JWT token from request headers
        auth_header = request.headers.get("Authorization")
        jwt_token = extract_jwt_token(auth_header)
        agent_dict = _get_agent_by_id_internal(agent_id, user_id, jwt_token)
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
        
        report_result = await report_service.generate_report(
            agent=agent,
            vector_store=vector_store,
            document_ids=document_ids
        )
        
        if not report_result["success"]:
            raise HTTPException(status_code=500, detail=f"Document processing failed: {report_result.get('error', 'Unknown error')}")
        
        # Extract AI baseline IMMEDIATELY after generation (before any user edits)
        ai_baseline_answers = supabase_service._extract_baseline_answers(report_result["report_data"])
        logging.info(f"Extracted AI baseline with {len(ai_baseline_answers)} answers for audit trail")
        
        # Cache the report data AND baseline immediately after generation
        cache_report(user_id, agent_id, report_result["report_data"], ai_baseline_answers)
        logging.info(f"Report generated and cached with AI baseline for user {user_id}, agent {agent_id}")
        
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


@router.post("/{agent_id}/test-question")
async def test_single_question(
    agent_id: str,
    request: dict,
    current_user = Depends(get_current_user)
):
    """Test a single question against uploaded documents for agent creation"""
    user_id = current_user.id
    
    # Extract question from request
    question_text = request.get("question", "").strip()
    if not question_text:
        raise HTTPException(status_code=400, detail="Question text is required")
    
    # Check if there are uploaded files for this user
    if user_id not in uploaded_files_storage or not uploaded_files_storage[user_id]:
        raise HTTPException(status_code=400, detail="No documents uploaded for testing")
    
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
        raise HTTPException(status_code=400, detail="No successfully uploaded documents available for testing")
    
    try:
        # Import LLM service
        from app.services.llm_service import llm_service
        from app.schemas import QuestionOut
        
        # Create a temporary question object for testing
        test_question = QuestionOut(
            id="test_question",
            placeholder="{{Test Question}}",
            prompt=question_text
        )
        
        # Get document IDs
        document_ids = [file_record["id"] for file_record in successfully_uploaded_files]
        
        # Search for relevant chunks for this question
        relevant_chunks = await vector_store.search_chunks(
            query=question_text,
            document_ids=document_ids,
            top_k=10  # Get more chunks for testing
        )
        
        if not relevant_chunks:
            return {
                "success": True,
                "question": question_text,
                "answer": "No relevant information found in the uploaded documents.",
                "quotes": [],
                "document_context": {
                    "total_documents": len(successfully_uploaded_files),
                    "document_ids": document_ids,
                    "chunks_searched": 0
                }
            }
        
        # Prepare question with chunks for LLM processing
        questions_with_chunks = [{
            "question": test_question,
            "relevant_chunks": relevant_chunks
        }]
        
        # Create document context
        document_context = {
            "total_documents": len(successfully_uploaded_files),
            "document_ids": document_ids,
            "filenames": [f["name"] for f in successfully_uploaded_files]
        }
        
        # Process with LLM service
        llm_result = llm_service.process_agent_questions(questions_with_chunks, document_context)
        
        if not llm_result["success"]:
            raise HTTPException(status_code=500, detail=f"LLM processing failed: {llm_result.get('error', 'Unknown error')}")
        
        # Extract result for the test question
        question_result = llm_result["results"].get("{{Test Question}}")
        if not question_result:
            raise HTTPException(status_code=500, detail="No result returned for test question")
        
        # Format quotes for frontend (same format as report preview)
        formatted_quotes = []
        for i, source_chunk in enumerate(question_result.get("source_chunks", [])):
            formatted_quotes.append({
                "chunk_id": source_chunk["chunk_id"],
                "document_id": source_chunk.get("document_id", ""),
                "text": source_chunk["text"],
                "exact_text": source_chunk.get("exact_text", source_chunk["text"]),
                "page_range": source_chunk["page_range"],
                "precise_page": source_chunk.get("precise_page"),
                "relevance_score": source_chunk.get("relevance_score", 0.0),
                "quote_index": i + 1
            })
        
        return {
            "success": True,
            "question": question_text,
            "answer": question_result["answer"],
            "quotes": formatted_quotes,
            "document_context": {
                "total_documents": len(successfully_uploaded_files),
                "document_ids": document_ids,
                "chunks_searched": len(relevant_chunks),
                "filenames": [f["name"] for f in successfully_uploaded_files]
            },
            "processing_stats": {
                "model_used": llm_result.get("model_used"),
                "processing_method": llm_result.get("processing_method"),
                "total_chunks": llm_result.get("processed_chunks", 0)
            }
        }
        
    except ValueError as e:
        # Handle LLM service errors
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Failed to test question: {e}")
        raise HTTPException(status_code=500, detail=f"Question testing failed: {str(e)}")


@router.get("/{agent_id}/report")
async def get_agent_report(agent_id: str, request: Request, current_user = Depends(get_current_user)):
    """Retrieve cached report data for an agent (no LLM processing)"""
    user_id = current_user.id
    
    # Get agent configuration using internal helper with proper auth
    try:
        # Extract JWT token from request headers for custom agent access
        auth_header = request.headers.get("Authorization")
        jwt_token = extract_jwt_token(auth_header) if auth_header else None
        agent_dict = _get_agent_by_id_internal(agent_id, user_id, jwt_token)
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
    request: Request,
    with_references: bool = False,
    current_user = Depends(get_current_user)
):
    """Download PDF report for an agent using cached data (no LLM regeneration)"""
    from fastapi.responses import StreamingResponse
    import io

    user_id = current_user.id

    # Get agent configuration using internal helper with proper auth
    try:
        # Extract JWT token from request headers for custom agent access
        auth_header = request.headers.get("Authorization")
        jwt_token = extract_jwt_token(auth_header) if auth_header else None
        agent_dict = _get_agent_by_id_internal(agent_id, user_id, jwt_token)
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


@router.put("/reports/{agent_id}/cache")
async def update_report_cache_for_agent(
    agent_id: str,
    payload: UpdateCachedReportRequest,
    current_user = Depends(get_current_user)
):
    """Update cached report data for specific agent (persist UI edits before saving)"""
    user_id = current_user.id

    # Validate there is an existing cached report
    if user_id not in report_cache_storage or agent_id not in report_cache_storage[user_id]:
        raise HTTPException(status_code=404, detail="No cached report found to update")

    try:
        report_cache_storage[user_id][agent_id]["report_data"] = payload.report_data
        logging.info(f"Updated cached report data for user {user_id}, agent {agent_id}")
        return {
            "success": True,
            "message": "Cached report data updated successfully"
        }
    except Exception as e:
        logging.error(f"Failed to update cached report for user {user_id}, agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update cached report data")

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

@router.post("/{agent_id}/reports/save")
async def save_current_report(
    agent_id: str, 
    request: SaveReportRequest,
    http_request: Request,
    current_user = Depends(get_current_user),
    auth_tokens: tuple[str, str] = Depends(extract_auth_tokens)
):
    """Save currently cached report to Supabase with PDF binaries"""
    user_id = current_user.id
    access_token, refresh_token = auth_tokens
    
    # Get agent configuration using internal helper with proper auth
    try:
        agent_dict = _get_agent_by_id_internal(agent_id, user_id, access_token)
        agent = Agent(**agent_dict)
    except HTTPException as e:
        raise e
    
    # Get cached report data
    cached_report = get_cached_report(user_id, agent_id)
    if not cached_report:
        raise HTTPException(status_code=400, detail="No cached report to save. Please generate a report first.")
    
    # Build minimal document contents and collect PDF binaries
    document_contents = {}
    pdf_binaries = {}
    
    for doc_id in cached_report["document_ids"]:
        if user_id in uploaded_files_storage and doc_id in uploaded_files_storage[user_id]:
            file_record = uploaded_files_storage[user_id][doc_id]
            
            # Build minimal document content (no full_text extraction)
            document_contents[doc_id] = {
                "filename": file_record["name"],
                "metadata": {
                    "size": file_record["size"],
                    "type": file_record["type"],
                    "processing_stats": file_record.get("processing_stats", {})
                }
            }
            
            # Collect PDF binary only for non-OCR documents
            processing_stats = file_record.get("processing_stats", {})
            processor_used = processing_stats.get("processor_used", "")
            
            if "OCR" not in processor_used and file_record.get("content"):
                pdf_binaries[doc_id] = file_record["content"]
                logging.info(f"Collected PDF binary for {doc_id} ({len(file_record['content'])} bytes)")
    
    if not document_contents:
        raise HTTPException(status_code=400, detail="No document content available to save with report")
    
    # Extract cached AI baseline for audit trail
    cached_ai_baseline = cached_report.get("ai_baseline_answers")
    if cached_ai_baseline:
        logging.info(f"Using cached AI baseline for save (first save scenario)")
    else:
        logging.warning(f"No cached AI baseline found - audit trail may not work correctly")
    
    try:
        # Save to Supabase with PDF binaries AND cached baseline
        report_id = supabase_service.save_report(
            user_jwt=access_token,
            user_id=user_id,
            agent_id=agent_id,
            agent_name=agent.name,
            report_name=request.report_name,
            report_data=cached_report["report_data"],
            document_contents=document_contents,
            pdf_binaries=pdf_binaries,
            refresh_token=refresh_token,
            cached_ai_baseline=cached_ai_baseline  # NEW: Pass cached baseline
        )
        
        logging.info(f"Successfully saved report {report_id} for user {user_id} with {len(pdf_binaries)} PDF binaries")
        
        return {
            "success": True,
            "report_id": report_id,
            "message": f"Report '{request.report_name}' saved successfully"
        }
        
    except Exception as e:
        logging.error(f"Failed to save report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save report: {str(e)}")

@router.get("/reports/saved", response_model=List[SavedReportOut])
async def list_saved_reports(
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """List user's saved reports"""
    user_id = current_user.id
    
    try:
        reports_data = supabase_service.get_user_reports(jwt_token, user_id)
        
        # Convert to response format
        saved_reports = []
        for report in reports_data:
            saved_reports.append(SavedReportOut(
                id=report["id"],
                report_name=report["report_name"],
                agent_name=report["agent_name"],
                agent_id=report["agent_id"],
                saved_at=report["saved_at"],
                generated_at=report["generated_at"]
            ))
        
        return saved_reports
        
    except Exception as e:
        logging.error(f"Failed to fetch saved reports for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch saved reports")

@router.get("/reports/saved/{report_id}", response_model=SavedReportDetailOut)
async def get_saved_report(
    report_id: str, 
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """Get a specific saved report with full data for viewing"""
    user_id = current_user.id
    
    try:
        report_data = supabase_service.get_saved_report(jwt_token, user_id, report_id)
        
        if not report_data:
            raise HTTPException(status_code=404, detail="Saved report not found")
        
        return SavedReportDetailOut(
            id=report_data["id"],
            report_name=report_data["report_name"],
            agent_name=report_data["agent_name"],
            agent_id=report_data["agent_id"],
            report_data=report_data["report_data"],
            saved_at=report_data["saved_at"],
            generated_at=report_data["generated_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to fetch saved report {report_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch saved report")

@router.get("/reports/saved/{report_id}/with-audit")
async def get_report_with_audit(
    report_id: str,
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """
    Get saved report with audit trail changes for track changes view.
    
    Returns the report data along with all changes from the AI baseline,
    formatted for frontend audit trail visualization.
    """
    user_id = current_user.id
    
    try:
        audit_data = supabase_service.get_report_with_audit_changes(
            jwt_token,
            user_id,
            report_id
        )
        
        if not audit_data:
            raise HTTPException(status_code=404, detail="Saved report not found")
        
        return {
            "success": True,
            "report_id": audit_data["report_id"],
            "report_name": audit_data["report_name"],
            "agent_name": audit_data["agent_name"],
            "report_data": audit_data["report_data"],
            "changes": audit_data["changes"],
            "has_changes": audit_data["has_changes"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to fetch audit data for report {report_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch audit trail data")

@router.get("/reports/saved/{report_id}/documents/{document_id}/content")
async def get_saved_document_content(
    report_id: str, 
    document_id: str, 
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """Get document content for saved report (for DocumentViewer)"""
    user_id = current_user.id
    
    try:
        document_content = supabase_service.get_saved_document_content(jwt_token, user_id, report_id, document_id)
        
        if not document_content:
            raise HTTPException(status_code=404, detail="Document content not found for saved report")
        
        return document_content
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to fetch document content for saved report: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch document content")

@router.post("/reports/saved/{report_id}/preload-documents")
async def preload_saved_report_documents(
    report_id: str,
    current_user = Depends(get_current_user),
    auth_tokens: tuple[str, str] = Depends(extract_auth_tokens)
):
    """Preload all PDFs for a saved report into memory for fast quote viewing"""
    user_id = current_user.id
    access_token, refresh_token = auth_tokens
    
    try:
        # Get document IDs from the report
        user_client = supabase_service._create_user_client(access_token)
        
        # Verify report ownership
        report_result = user_client.table("saved_reports")\
            .select("id")\
            .eq("id", report_id)\
            .eq("user_id", user_id)\
            .single()\
            .execute()
        
        if not report_result.data:
            raise HTTPException(status_code=404, detail="Report not found")
        
        # Get all documents for this report that have PDF storage paths
        docs_result = user_client.table("saved_report_documents")\
            .select("document_id, storage_path, filename, metadata")\
            .eq("report_id", report_id)\
            .execute()
        
        if not docs_result.data:
            return {
                "success": True,
                "documents_loaded": 0,
                "total_size_mb": 0,
                "message": "No documents to preload"
            }
        
        # Initialize user cache if needed
        if user_id not in preloaded_reports_cache:
            preloaded_reports_cache[user_id] = {}
        
        if report_id not in preloaded_reports_cache[user_id]:
            preloaded_reports_cache[user_id][report_id] = {}
        
        # Fetch PDFs from Storage
        from app.services.supabase_storage_service import get_storage_service
        storage_service = get_storage_service()
        
        loaded_count = 0
        total_size = 0
        skipped_count = 0
        
        for doc in docs_result.data:
            document_id = doc["document_id"]
            storage_path = doc.get("storage_path")
            
            # Skip if no storage path (OCR documents)
            if not storage_path:
                logging.info(f"Skipping document {document_id} - no storage path (OCR document)")
                skipped_count += 1
                continue
            
            # Skip if already cached
            if document_id in preloaded_reports_cache[user_id][report_id]:
                logging.info(f"Document {document_id} already cached, skipping")
                continue
            
            try:
                # Download PDF from Storage
                pdf_bytes = storage_service.download_file(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    user_id=user_id,
                    storage_path=storage_path
                )
                
                if pdf_bytes:
                    # Cache the PDF in memory
                    preloaded_reports_cache[user_id][report_id][document_id] = {
                        "content": pdf_bytes,
                        "filename": doc.get("filename", "unknown.pdf"),
                        "size": len(pdf_bytes),
                        "loaded_at": time.time(),
                        "storage_path": storage_path
                    }
                    
                    loaded_count += 1
                    total_size += len(pdf_bytes)
                    
                    logging.info(f"Preloaded PDF {document_id}: {doc.get('filename')} ({len(pdf_bytes)} bytes)")
                
            except Exception as e:
                logging.error(f"Failed to preload document {document_id}: {e}")
                # Continue with other documents even if one fails
                continue
        
        # Log summary
        total_size_mb = total_size / (1024 * 1024)
        logging.info(f"Preload complete for report {report_id}: {loaded_count} documents, {total_size_mb:.2f} MB, {skipped_count} skipped")
        
        return {
            "success": True,
            "documents_loaded": loaded_count,
            "documents_skipped": skipped_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size_mb, 2),
            "message": f"Preloaded {loaded_count} PDFs for fast quote viewing"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to preload documents for report {report_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to preload documents: {str(e)}")


@router.delete("/reports/saved/{report_id}/unload-documents")
async def unload_saved_report_documents(
    report_id: str,
    current_user = Depends(get_current_user)
):
    """Unload preloaded PDFs for a saved report from memory"""
    user_id = current_user.id
    
    # Check if user has preloaded reports
    if user_id not in preloaded_reports_cache:
        return {
            "success": True,
            "documents_unloaded": 0,
            "memory_freed_mb": 0,
            "message": "No preloaded documents for this user"
        }
    
    # Check if report has preloaded documents
    if report_id not in preloaded_reports_cache[user_id]:
        return {
            "success": True,
            "documents_unloaded": 0,
            "memory_freed_mb": 0,
            "message": "No preloaded documents for this report"
        }
    
    # Calculate memory freed
    documents_cache = preloaded_reports_cache[user_id][report_id]
    total_size = sum(doc["size"] for doc in documents_cache.values())
    doc_count = len(documents_cache)
    
    # Remove from cache
    del preloaded_reports_cache[user_id][report_id]
    
    # If no more reports for this user, clean up user entry
    if not preloaded_reports_cache[user_id]:
        del preloaded_reports_cache[user_id]
    
    total_size_mb = total_size / (1024 * 1024)
    logging.info(f"Unloaded {doc_count} PDFs for report {report_id}, freed {total_size_mb:.2f} MB")
    
    return {
        "success": True,
        "documents_unloaded": doc_count,
        "memory_freed_bytes": total_size,
        "memory_freed_mb": round(total_size_mb, 2),
        "message": f"Unloaded {doc_count} PDFs, freed {total_size_mb:.2f} MB"
    }


@router.get("/reports/saved/{report_id}/documents/{document_id}/file")
async def get_saved_document_file(
    report_id: str,
    document_id: str,
    request: Request,
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """Stream PDF file for saved report documents (checks preload cache first, then uses Supabase Storage)"""
    from fastapi.responses import RedirectResponse
    user_id = current_user.id
    
    # FIRST: Check preload cache for instant delivery
    if (user_id in preloaded_reports_cache and 
        report_id in preloaded_reports_cache[user_id] and 
        document_id in preloaded_reports_cache[user_id][report_id]):
        
        cached_doc = preloaded_reports_cache[user_id][report_id][document_id]
        pdf_bytes = cached_doc["content"]
        total_size = len(pdf_bytes)
        
        logging.info(f"Serving preloaded PDF {document_id} from memory cache ({total_size} bytes)")
        
        # Prepare response headers
        headers = {
            "Content-Type": "application/pdf",
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges"
        }
        
        # Handle Range requests for PDF seeking
        range_header = request.headers.get("Range")
        if range_header and (match := re.match(r"bytes=(\d+)-(\d*)", range_header)):
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else total_size - 1
            end = min(end, total_size - 1)
            
            return Response(
                content=pdf_bytes[start:end+1],
                status_code=206,  # Partial Content
                media_type="application/pdf",
                headers={
                    **headers,
                    "Content-Range": f"bytes {start}-{end}/{total_size}",
                    "Content-Length": str(end - start + 1)
                }
            )
        
        # Return full PDF from cache
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={**headers, "Content-Length": str(total_size)}
        )
    
    # FALLBACK: Not in cache, use Storage with signed URL redirect
    try:
        # Get document metadata to check for Storage path
        user_client = supabase_service._create_user_client(jwt_token)
        
        # Verify report ownership
        report_result = user_client.table("saved_reports")\
            .select("id")\
            .eq("id", report_id)\
            .eq("user_id", user_id)\
            .single()\
            .execute()
        
        if not report_result.data:
            raise HTTPException(status_code=404, detail="Report not found")
        
        # Get document Storage metadata
        doc_result = user_client.table("saved_report_documents")\
            .select("storage_path, content_hash, filename")\
            .eq("report_id", report_id)\
            .eq("document_id", document_id)\
            .single()\
            .execute()
        
        if not doc_result.data:
            raise HTTPException(status_code=404, detail="Document not found")
        
        storage_path = doc_result.data.get("storage_path")
        
        # Check if document has Storage path (new documents)
        if storage_path:
            # Generate signed URL and redirect
            from app.services.supabase_storage_service import get_storage_service
            from app.config import STORAGE_SIGNED_URL_EXPIRY_SECONDS
            
            storage_service = get_storage_service()
            
            try:
                signed_url = storage_service.get_signed_url(
                    access_token=jwt_token,
                    refresh_token="",
                    user_id=user_id,
                    storage_path=storage_path,
                    expiry_seconds=STORAGE_SIGNED_URL_EXPIRY_SECONDS
                )
                
                # Add content-hash as ETag for caching if available
                headers = {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Expose-Headers": "ETag"
                }
                
                content_hash = doc_result.data.get("content_hash")
                if content_hash:
                    headers["ETag"] = f'"{content_hash[:16]}"'
                
                # Redirect to signed URL (307 preserves method and body)
                logging.info(f"Redirecting to signed URL for document {document_id}")
                return RedirectResponse(
                    url=signed_url,
                    status_code=307,
                    headers=headers
                )
                
            except Exception as storage_error:
                logging.error(f"Failed to get signed URL for {document_id}: {storage_error}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to generate secure access URL for document"
                )
        
        # No Storage path - likely OCR document
        raise HTTPException(
            status_code=404,
            detail="Original PDF not available for this document. This may be an OCR-processed document. Please use the text-based content viewer instead."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error retrieving saved document file {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve document file")

@router.delete("/reports/saved/{report_id}")
async def delete_saved_report(
    report_id: str, 
    current_user = Depends(get_current_user),
    auth_tokens: tuple[str, str] = Depends(extract_auth_tokens)
):
    """Delete a saved report, its associated documents, and PDFs from Storage"""
    user_id = current_user.id
    access_token, refresh_token = auth_tokens
    
    try:
        success = supabase_service.delete_saved_report(access_token, user_id, report_id, refresh_token)
        
        if not success:
            raise HTTPException(status_code=404, detail="Saved report not found or access denied")
        
        return {
            "success": True,
            "message": "Saved report deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to delete saved report {report_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete saved report")

@router.patch("/reports/saved/{report_id}")
async def update_saved_report(
    report_id: str,
    request: UpdateSavedReportRequest,
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """Update a saved report's content and/or name"""
    user_id = current_user.id
    try:
        success = supabase_service.update_saved_report(
            user_jwt=jwt_token,
            user_id=user_id,
            report_id=report_id,
            report_data=request.report_data,
            report_name=request.report_name
        )
        if not success:
            raise HTTPException(status_code=404, detail="Saved report not found or update failed")

        return {
            "success": True,
            "message": "Saved report updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to update saved report {report_id} for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update saved report")

@router.get("/reports/saved/{report_id}/pdf")
async def download_saved_report_pdf(
    report_id: str,
    with_references: bool = False,
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """Download PDF of saved report using existing code patterns"""
    from fastapi.responses import StreamingResponse
    import io
    
    user_id = current_user.id
    
    try:
        # Get saved report data (includes latest edits)
        report_data = supabase_service.get_saved_report(jwt_token, user_id, report_id)
        
        if not report_data:
            raise HTTPException(status_code=404, detail="Saved report not found")
        
        # Get proper agent configuration with reportTemplate (reuse existing code pattern)
        agent_dict = _get_agent_by_id_internal(report_data["agent_id"], user_id, jwt_token)
        agent = Agent(**agent_dict)
        
        # Enhance report_data with document context (same pattern as fresh reports)
        enhanced_report_data = report_data["report_data"].copy()
        
        # Build document context from saved document content (reuse existing structure)
        document_context = enhanced_report_data.get("document_context", {})
        if "documents" not in document_context:
            # Get document IDs from the report data
            document_ids = []
            for answer_data in enhanced_report_data.get("answers", {}).values():
                for quote in answer_data.get("quotes", []):
                    doc_id = quote.get("document_id")
                    if doc_id and doc_id not in document_ids:
                        document_ids.append(doc_id)
            
            # Build documents mapping (same as fresh reports)
            documents = {}
            for doc_id in document_ids:
                try:
                    # Reuse existing document content retrieval
                    doc_content = supabase_service.get_saved_document_content(
                        jwt_token, user_id, report_id, doc_id
                    )
                    if doc_content:
                        documents[doc_id] = {
                            "filename": doc_content.get("filename", "Unknown Document"),
                            "document_id": doc_id
                        }
                except Exception as e:
                    logging.warning(f"Failed to get document {doc_id} for PDF generation: {e}")
                    documents[doc_id] = {
                        "filename": "Unknown Document",
                        "document_id": doc_id
                    }
            
            # Update document context (same structure as fresh reports)
            enhanced_report_data["document_context"] = {
                **document_context,
                "documents": documents,
                "document_ids": document_ids
            }
        
        # Generate PDF using existing PDF generator (same as fresh reports)
        pdf_content = pdf_generator.generate_pdf_report(
            agent=agent,
            report_data=enhanced_report_data,
            with_references=with_references
        )
        
        # Create streaming response (same as fresh reports)
        pdf_buffer = io.BytesIO(pdf_content)
        
        # Generate filename
        references_suffix = "_with_references" if with_references else ""
        safe_report_name = report_data["report_name"].replace(" ", "_")
        filename = f"{safe_report_name}{references_suffix}.pdf"
        
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to generate PDF for saved report {report_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate PDF")

# Custom Agent CRUD Endpoints

@router.post("/create_custom_agent", response_model=CustomAgentOut)
async def create_custom_agent(
    request: CreateCustomAgentRequest,
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """Create a new custom agent"""
    user_id = current_user.id
    
    try:
        # Extract questions data for Supabase service
        questions_data = []
        for question in request.questions:
            questions_data.append({
                "placeholder": question.placeholder,
                "prompt": question.prompt
            })
        
        # Use user ID as display name fallback since email might not be available
        # TODO: add user email to user information during registration
        created_by_name = getattr(current_user, 'email', None) or f"User {str(current_user.id)[:8]}"
        
        agent_id = supabase_service.create_custom_agent(
            user_jwt=jwt_token,
            user_id=user_id,
            created_by_name=created_by_name,
            name=request.name,
            description=request.description or "",
            report_template=request.report_template,
            questions=questions_data
        )
        
        # Get the created agent to return
        agent_data = supabase_service.get_agent_by_id(jwt_token, user_id, agent_id)
        
        if not agent_data:
            raise HTTPException(status_code=500, detail="Failed to retrieve created agent")
        
        # Transform to CustomAgentOut format
        questions_out = []
        for q in agent_data.get("agent_questions", []):
            questions_out.append({
                "id": str(q["id"]),
                "placeholder": q["placeholder"],
                "prompt": q["prompt"]
            })
        
        return CustomAgentOut(
            id=str(agent_data["id"]),
            name=agent_data["name"],
            description=agent_data["description"],
            reportTemplate=agent_data["report_template"],
            questions=questions_out,
            user_id=agent_data["user_id"],
            is_custom=agent_data["is_custom"],
            created_by_name=agent_data["created_by_name"],
            createdAt=agent_data["created_at"],
            updatedAt=agent_data["updated_at"],
            can_delete=True
        )
        
    except Exception as e:
        logging.error(f"Failed to create custom agent: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create custom agent: {str(e)}")

@router.get("/list_user_custom_agents", response_model=List[CustomAgentOut])
async def list_user_custom_agents(
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """Get user's custom agents"""
    user_id = current_user.id
    
    try:
        agents_data = supabase_service.get_user_custom_agents(jwt_token, user_id)
        
        custom_agents = []
        for agent_data in agents_data:
            questions_out = []
            for q in agent_data.get("agent_questions", []):
                questions_out.append({
                    "id": str(q["id"]),
                    "placeholder": q["placeholder"],
                    "prompt": q["prompt"]
                })
            
            custom_agents.append(CustomAgentOut(
                id=str(agent_data["id"]),
                name=agent_data["name"],
                description=agent_data["description"],
                reportTemplate=agent_data["report_template"],
                questions=questions_out,
                user_id=agent_data["user_id"],
                is_custom=agent_data["is_custom"],
                created_by_name=agent_data["created_by_name"],
                createdAt=agent_data["created_at"],
                updatedAt=agent_data["updated_at"],
                can_delete=True
            ))
        
        return custom_agents
        
    except Exception as e:
        logging.error(f"Failed to fetch custom agents: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch custom agents")

@router.put("/custom/{agent_id}", response_model=CustomAgentOut)
async def update_custom_agent(
    agent_id: str,
    request: UpdateCustomAgentRequest,
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """Update a custom agent"""
    user_id = current_user.id
    
    try:
        # Extract questions data for Supabase service
        questions_data = None
        if request.questions is not None:
            questions_data = []
            for question in request.questions:
                questions_data.append({
                    "placeholder": question.placeholder,
                    "prompt": question.prompt
                })
        
        # Update the agent using the existing service method
        success = supabase_service.update_custom_agent(
            user_jwt=jwt_token,
            user_id=user_id,
            agent_id=agent_id,
            name=request.name,
            description=request.description,
            report_template=request.report_template,
            questions=questions_data
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Custom agent not found or access denied")
        
        # Get the updated agent to return
        agent_data = supabase_service.get_agent_by_id(jwt_token, user_id, agent_id)
        
        if not agent_data:
            raise HTTPException(status_code=500, detail="Failed to retrieve updated agent")
        
        # Transform to CustomAgentOut format
        questions_out = []
        for q in agent_data.get("agent_questions", []):
            questions_out.append({
                "id": str(q["id"]),
                "placeholder": q["placeholder"],
                "prompt": q["prompt"]
            })
        
        return CustomAgentOut(
            id=str(agent_data["id"]),
            name=agent_data["name"],
            description=agent_data["description"],
            reportTemplate=agent_data["report_template"],
            questions=questions_out,
            user_id=agent_data["user_id"],
            is_custom=agent_data["is_custom"],
            created_by_name=agent_data["created_by_name"],
            createdAt=agent_data["created_at"],
            updatedAt=agent_data["updated_at"],
            can_delete=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to update custom agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update custom agent: {str(e)}")

@router.delete("/custom/{agent_id}")
async def delete_custom_agent(
    agent_id: str,
    current_user = Depends(get_current_user),
    jwt_token: str = Depends(extract_jwt_token)
):
    """Delete a custom agent"""
    user_id = current_user.id
    
    try:
        success = supabase_service.delete_custom_agent(jwt_token, user_id, agent_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Custom agent not found or access denied")
        
        return {
            "success": True,
            "message": "Custom agent deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to delete custom agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete custom agent: {str(e)}")

def _get_agent_by_id_internal(agent_id: str, user_id: str = None, jwt_token: str = None):
    """Internal helper function to get agent by ID without dependency injection"""
    try:
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
        
        # Try custom agents from database (only if user context provided)
        if user_id and jwt_token:
            try:
                agent_data = supabase_service.get_agent_by_id(jwt_token, user_id, agent_id)
                if agent_data:
                    # Transform custom agent data to match Agent schema
                    questions_out = []
                    for q in agent_data.get("agent_questions", []):
                        questions_out.append({
                            "id": str(q["id"]),
                            "placeholder": q["placeholder"],
                            "prompt": q["prompt"]
                        })
                    
                    agent_dict = {
                        "id": str(agent_data["id"]),
                        "name": agent_data["name"],
                        "description": agent_data["description"],
                        "reportTemplate": agent_data["report_template"],
                        "questions": questions_out
                    }
                    return agent_dict
            except Exception as e:
                logging.warning(f"Failed to lookup custom agent {agent_id}: {e}")
                # Continue to not found error below
        
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

@router.get("/{agent_id}", response_model=Agent)
def get_agent_by_id(agent_id: str, current_user = Depends(get_current_user), jwt_token: str = Depends(extract_jwt_token)):
    """Get a specific agent by ID (handles both prebuilt and custom agents)"""
    return _get_agent_by_id_internal(agent_id, current_user.id, jwt_token)

@router.get("/performance/report")
async def get_performance_report(current_user = Depends(get_current_user)):
    """Get comprehensive performance metrics for file processing"""
    performance_monitor = get_performance_monitor()
    
    try:
        # Get performance summary
        summary = performance_monitor.get_performance_summary(last_n_files=50)
        
        if "error" in summary:
            return {
                "available": False,
                "message": summary["error"]
            }
        
        return {
            "available": True,
            "user_id": current_user.id,
            "performance_data": summary,
            "report_generated_at": time.time()
        }
        
    except Exception as e:
        logging.error(f"Failed to generate performance report: {e}")
        return {
            "available": False,
            "error": str(e)
        }

@router.post("/performance/export")
async def export_performance_metrics(current_user = Depends(get_current_user)):
    """Export performance metrics to JSON file"""
    performance_monitor = get_performance_monitor()
    
    try:
        # Generate filename with timestamp
        timestamp = int(time.time())
        filepath = f"performance_export_{timestamp}.json"
        
        # Export metrics
        performance_monitor.export_metrics(filepath, last_n_files=1000)
        
        return {
            "success": True,
            "filepath": filepath,
            "message": f"Performance metrics exported to {filepath}"
        }
        
    except Exception as e:
        logging.error(f"Failed to export performance metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export metrics: {str(e)}")
