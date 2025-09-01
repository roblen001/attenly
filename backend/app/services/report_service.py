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

logger = logging.getLogger(__name__)


class ReportService:
    """Combined service for report generation and quote extraction"""
    
    def __init__(self):
        self.llm_service = llm_service
    
    def generate_report(self, agent: Agent, vector_store: VectorStore, 
                       document_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Generate a complete report with extracted data and source quotes
        
        Args:
            agent: Agent configuration with questions and template
            vector_store: User's vector store instance
            document_ids: Optional list of specific document IDs to process
            
        Returns:
            Complete report data with answers, quotes, and metadata
            
        Raises:
            ValueError: If vector store is not available or no chunks found
        """
        
        if not vector_store.available:
            raise ValueError("Vector store not available for report generation")
        
        try:
            # Get all relevant chunks for the agent's questions
            all_relevant_chunks = self._gather_relevant_chunks(
                agent.questions, vector_store, document_ids
            )
            
            if not all_relevant_chunks:
                raise ValueError("No relevant document chunks found for report generation")
            
            # Process questions through LLM service
            document_context = self._build_document_context(all_relevant_chunks, document_ids)
            
            llm_results = self.llm_service.process_agent_questions(
                agent.questions, all_relevant_chunks, document_context
            )
            
            # Handle both successful LLM processing and placeholder responses
            if not llm_results["success"]:
                logger.warning(f"LLM processing not successful: {llm_results.get('error', 'Unknown error')}")
                # Continue with placeholder data instead of raising an error
            
            # Build complete report data
            report_data = self._build_report_data(
                agent, llm_results["results"], all_relevant_chunks, document_context
            )
            
            return {
                "success": True,
                "report_id": str(uuid.uuid4()),
                "agent_id": agent.id,
                "agent_name": agent.name,
                "report_data": report_data,
                "processing_stats": {
                    "questions_processed": len(agent.questions),
                    "chunks_analyzed": len(all_relevant_chunks),
                    "documents_processed": len(document_context.get("document_ids", [])),
                    "llm_model": llm_results.get("model_used", "unknown")
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to generate report for agent {agent.id}: {e}")
            raise ValueError(f"Report generation failed: {str(e)}")
    
    def _gather_relevant_chunks(self, questions: List[QuestionOut], vector_store: VectorStore, 
                              document_ids: Optional[List[str]] = None) -> List[Dict]:
        """Gather relevant chunks for all questions using vector search"""
        
        all_chunks = []
        seen_chunk_ids = set()
        
        # Search for chunks relevant to each question
        for question in questions:
            try:
                # Use the question prompt as search query
                chunks = vector_store.search_chunks(
                    query=question.prompt,
                    top_k=15,  # Get more chunks per question for better coverage
                    document_ids=document_ids
                )
                
                # Add unique chunks to our collection
                for chunk in chunks:
                    chunk_id = chunk["chunk_id"]
                    if chunk_id not in seen_chunk_ids:
                        all_chunks.append(chunk)
                        seen_chunk_ids.add(chunk_id)
                        
            except Exception as e:
                logger.warning(f"Failed to search chunks for question {question.placeholder}: {e}")
                continue
        
        # Sort by relevance (distance) and limit total chunks
        all_chunks.sort(key=lambda x: x.get("distance", float('inf')))
        
        # Limit to top 50 chunks to manage token usage
        return all_chunks[:50]
    
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
                    quote = {
                        "id": str(uuid.uuid4()),
                        "index": quote_counter,
                        "chunk_id": source_chunk["chunk_id"],
                        "text": source_chunk["text"],
                        "page_range": source_chunk["page_range"],
                        "relevance_score": source_chunk.get("relevance_score", 0.0)
                    }
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
