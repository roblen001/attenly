"""
Report Service

Combined service for report generation and quote extraction.
Integrates with vector store and LLM service to create complete reports with source references.
"""

import logging
import uuid
from typing import List, Dict, Any, Optional
from app.schemas import Agent, QuestionOut
from app.services.llm_service import llm_service
from app.services.vector_store import VectorStore
from app.config import (
    VECTOR_SEARCH_TOP_K_PER_QUESTION,
)

logger = logging.getLogger(__name__)


class ReportService:
    """Combined service for report generation and quote extraction"""
    
    def __init__(self):
        self.llm_service = llm_service
    
    async def generate_report(self, agent: Agent, vector_store: VectorStore, 
                       document_ids: Optional[List[str]] = None,
                       bbox_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate a complete report with extracted data and source quotes
        
        Args:
            agent: Agent configuration with questions and template
            vector_store: User's vector store instance
            document_ids: Optional list of specific document IDs to process
            bbox_data: Optional dictionary mapping document_ids to their bounding box data for OCR documents
            
        Returns:
            Complete report data with answers, quotes, and metadata
            
        Raises:
            ValueError: If vector store is not available, no chunks found, or LLM service is not available
        """
        
        if not vector_store.available:
            raise ValueError("Vector store not available for report generation")
        
        # Check LLM service availability before processing
        if not self.llm_service.available:
            raise ValueError("LLM service is not available. Please ensure GEMINI_API_KEY is configured and the service is properly initialized.")
        
        try:
            # Get question-specific chunks for each question individually
            questions_with_chunks = await self._gather_question_specific_chunks(
                agent.questions, vector_store, document_ids
            )
            
            if not questions_with_chunks:
                raise ValueError("No relevant document chunks found for any questions")
            
            # Build document context from all chunks
            all_chunks = []
            for item in questions_with_chunks:
                all_chunks.extend(item['relevant_chunks'])
            
            document_context = self._build_document_context(all_chunks, document_ids)
            
            # Process questions through LLM service with individual contexts
            llm_results = self.llm_service.process_agent_questions(
                questions_with_chunks, document_context, bbox_data
            )
            
            # LLM service now only returns successful results or raises an exception
            # No need to handle placeholder responses anymore
            
            # Build complete report data
            report_data = self._build_report_data(
                agent, llm_results["results"], all_chunks, document_context
            )
            
            return {
                "success": True,
                "report_id": str(uuid.uuid4()),
                "agent_id": agent.id,
                "agent_name": agent.name,
                "report_data": report_data,
                "processing_stats": {
                    "questions_processed": len(agent.questions),
                    "chunks_analyzed": len(all_chunks),
                    "documents_processed": len(document_context.get("document_ids", [])),
                    "llm_model": llm_results.get("model_used", "unknown")
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to generate report for agent {agent.id}: {e}")
            raise ValueError(f"Report generation failed: {str(e)}")
    
    async def _gather_question_specific_chunks(self, questions: List[QuestionOut], vector_store: VectorStore, 
                                       document_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Gather relevant chunks for each question individually for optimal RAG processing"""
        
        questions_with_chunks = []
        
        # Search for chunks relevant to each question individually
        for question in questions:
            try:
                # Use the question prompt as search query
                chunks = await vector_store.search_chunks(
                    query=question.prompt,
                    top_k=VECTOR_SEARCH_TOP_K_PER_QUESTION,  # Use configurable value
                    document_ids=document_ids
                )
                
                # Store question with its specific relevant chunks
                questions_with_chunks.append({
                    'question': question,
                    'relevant_chunks': chunks
                })
                
                logger.info(f"Found {len(chunks)} relevant chunks for question: {question.placeholder}")
                        
            except Exception as e:
                logger.warning(f"Failed to search chunks for question {question.placeholder}: {e}")
                # Still add the question but with empty chunks
                questions_with_chunks.append({
                    'question': question,
                    'relevant_chunks': []
                })
        
        return questions_with_chunks
    
    def _build_document_context(self, chunks: List[Dict], document_ids: Optional[List[str]]) -> Dict[str, Any]:
        """Build document context from chunks for LLM processing"""
        
        # Extract document metadata from chunks
        documents = {}
        total_pages = set()
        
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            doc_id = metadata.get("document_id")
            filename = metadata.get("filename", "Unknown")
            
            if doc_id:
                if doc_id not in documents:
                    documents[doc_id] = {
                        "id": doc_id,
                        "filename": filename,
                        "pages": set(),
                        "chunk_count": 0
                    }
                
                documents[doc_id]["chunk_count"] += 1
                
                # Track page ranges
                start_page = metadata.get("start_page")
                end_page = metadata.get("end_page")
                if start_page and end_page:
                    for page in range(start_page, end_page + 1):
                        documents[doc_id]["pages"].add(page)
                        total_pages.add(page)
        
        # Convert sets to sorted lists for JSON serialization
        for doc in documents.values():
            doc["pages"] = sorted(list(doc["pages"]))
        
        return {
            "document_ids": list(documents.keys()),
            "documents": documents,
            "total_documents": len(documents),
            "total_pages": len(total_pages),
            "total_chunks": len(chunks)
        }
    
    def _build_report_data(self, agent: Agent, llm_results: Dict[str, Any], 
                          chunks: List[Dict], document_context: Dict) -> Dict[str, Any]:
        """Build complete report data structure"""
        
        # Create answers with integrated quotes
        answers = {}
        all_quotes = []
        quote_counter = 1
        
        for question in agent.questions:
            placeholder = question.placeholder
            
            if placeholder in llm_results:
                result = llm_results[placeholder]
                
                # Process source chunks into quotes
                question_quotes = []
                for source_chunk in result.get("source_chunks", []):
                    # Extract document_id directly from source chunk (now included by LLM service)
                    document_id = source_chunk.get("document_id", "")
                    
                    # Add validation to ensure document_id is present
                    if not document_id:
                        logger.warning(f"Source chunk {source_chunk.get('chunk_id', 'unknown')} missing document_id")
                        continue  # Skip chunks without document_id
                    
                    # Build quote with all fields from source_chunk, including bbox data
                    quote = {
                        "id": str(uuid.uuid4()),
                        "index": quote_counter,
                        "chunk_id": source_chunk["chunk_id"],
                        "document_id": document_id,
                        "text": source_chunk["text"],
                        "page_range": source_chunk["page_range"],
                        "relevance_score": source_chunk.get("relevance_score", 0.0)
                    }
                    
                    # Preserve bbox-related fields if present (from OCR documents)
                    if "exact_text" in source_chunk:
                        quote["exact_text"] = source_chunk["exact_text"]
                    if "precise_page" in source_chunk:
                        quote["precise_page"] = source_chunk["precise_page"]
                    if "has_bounding_boxes" in source_chunk:
                        quote["has_bounding_boxes"] = source_chunk["has_bounding_boxes"]
                    if "word_spans" in source_chunk:
                        quote["word_spans"] = source_chunk["word_spans"]
                    
                    question_quotes.append(quote)
                    all_quotes.append(quote)
                    quote_counter += 1
                
                # Create answer with quotes
                answers[placeholder] = {
                    "id": str(uuid.uuid4()),
                    "placeholder": placeholder,
                    "question": question.prompt,
                    "answer": result["answer"],
                    "quotes": question_quotes,
                    "word_count": result.get("word_count", 0),
                    "error": result.get("error")
                }
            else:
                # Handle missing results
                answers[placeholder] = {
                    "id": str(uuid.uuid4()),
                    "placeholder": placeholder,
                    "question": question.prompt,
                    "answer": "[No answer generated]",
                    "quotes": [],
                    "word_count": 0,
                    "error": "Question not processed"
                }
        
        return {
            "template": {
                "html": agent.reportTemplate,
                "name": agent.name,
                "description": agent.description
            },
            "answers": answers,
            "quotes": all_quotes,
            "document_context": document_context,
            "generated_at": self._get_current_timestamp()
        }
    
    def populate_template(self, template_html: str, answers: Dict[str, Any]) -> str:
        """
        Populate HTML template with extracted answers and add quote superscripts
        
        Args:
            template_html: HTML template with {{placeholder}} markers
            answers: Dictionary of answers keyed by placeholder
            
        Returns:
            Populated HTML with answers and quote superscripts
        """
        
        populated_html = template_html
        
        # Replace each placeholder with answer and quotes
        for placeholder, answer_data in answers.items():
            placeholder_pattern = f"{{{{{placeholder}}}}}"
            
            if placeholder_pattern in populated_html:
                answer_text = answer_data["answer"]
                quotes = answer_data.get("quotes", [])
                
                # Add superscript references for quotes
                if quotes:
                    quote_superscripts = "".join([
                        f'<sup class="quote-superscript" data-quote-index="{quote["index"] - 1}">{quote["index"]}</sup>'
                        for quote in quotes
                    ])
                    answer_with_quotes = f"{answer_text}{quote_superscripts}"
                else:
                    answer_with_quotes = answer_text
                
                populated_html = populated_html.replace(placeholder_pattern, answer_with_quotes)
        
        return populated_html
    
    def generate_pdf_report(self, report_data: Dict[str, Any]) -> bytes:
        """
        Generate PDF from report data
        
        Args:
            report_data: Complete report data structure
            
        Returns:
            PDF bytes
            
        Note: This is a placeholder implementation. In production, you would use
        a library like weasyprint, reportlab, or similar to generate PDFs from HTML.
        """
        
        # TODO: Implement actual PDF generation
        # For now, return placeholder
        populated_html = self.populate_template(
            report_data["template"]["html"],
            report_data["answers"]
        )
        
        # Placeholder PDF content
        pdf_content = f"""PDF Report Generated
        
Agent: {report_data['template']['name']}
Generated: {report_data['generated_at']}
Questions: {len(report_data['answers'])}
Documents: {report_data['document_context']['total_documents']}

HTML Content:
{populated_html}
"""
        
        return pdf_content.encode('utf-8')
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format"""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"


# Global service instance
report_service = ReportService()
