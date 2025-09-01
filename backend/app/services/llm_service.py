"""
LLM Service

Provides AI-powered data extraction from document chunks.
Optimized for processing agent questions against vector store results.
"""

import logging
import os
from typing import List, Dict, Any, Optional
import json
from app.schemas import QuestionOut

logger = logging.getLogger(__name__)


class LLMService:
    """Service for AI-powered data extraction"""
    
    def __init__(self):
        self.model_name = "gemini-2.0-flash-exp"  # Gemini 2.5 Flash-Lite model
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.available = False
        
        try:
            import google.generativeai as genai
            
            if not self.api_key:
                logger.warning("GEMINI_API_KEY not found in environment variables")
                raise ValueError("Gemini API key not configured")
            
            # Configure the API
            genai.configure(api_key=self.api_key)
            
            # Initialize the model
            self.model = genai.GenerativeModel(self.model_name)
            self.available = True
            
            logger.info(f"Initialized LLM service with model: {self.model_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Gemini LLM service: {e}")
            self.model = None
    
    def process_agent_questions(self, agent_questions: List[QuestionOut], relevant_chunks: List[Dict], 
                              document_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process all agent questions against relevant document chunks
        
        Args:
            agent_questions: List of agent questions with placeholders and prompts
            relevant_chunks: List of relevant document chunks from vector store
            document_context: Additional context about the documents
            
        Returns:
            Dictionary with extracted answers and source references
            
        Raises:
            ValueError: If no relevant chunks are provided
        """
        
        if not relevant_chunks:
            raise ValueError("No relevant document chunks provided for processing")
        
        # TODO: Remove placeholder handling once LLM is fully integrated
        if not self.available:
            logger.warning("LLM service not available, returning placeholder data")
            return self._generate_placeholder_responses(agent_questions)
        
        try:
            # Prepare context from chunks using best practices
            context_text = self._prepare_context_from_chunks(relevant_chunks)
            
            # Process questions individually for better accuracy
            results = {}
            
            for question in agent_questions:
                try:
                    answer_data = self._process_single_question(
                        question, context_text, relevant_chunks, document_context
                    )
                    results[question.placeholder] = answer_data
                    
                except Exception as e:
                    logger.error(f"Failed to process question {question.placeholder}: {e}")
                    # Provide fallback response
                    results[question.placeholder] = {
                        "answer": f"[Error processing question: {str(e)}]",
                        "source_chunks": [],
                        "error": str(e)
                    }
            
            return {
                "success": True,
                "results": results,
                "total_questions": len(agent_questions),
                "processed_chunks": len(relevant_chunks),
                "model_used": self.model_name
            }
            
        except Exception as e:
            logger.error(f"Failed to process agent questions: {e}")
            raise ValueError(f"LLM processing failed: {str(e)}")
    
    def _process_single_question(self, question: QuestionOut, context_text: str, 
                               relevant_chunks: List[Dict], document_context: Dict) -> Dict:
        """Process a single question against the document context"""
        
        # Create a focused prompt for this specific question
        prompt = self._create_extraction_prompt(
            question.prompt, 
            question.placeholder,
            context_text,
            document_context
        )
        
        try:
            # Generate response using Gemini
            response = self.model.generate_content(prompt)
            
            if not response or not response.text:
                raise ValueError("Empty response from Gemini model")
            
            # Parse the structured response
            answer_data = self._parse_gemini_response(response.text, relevant_chunks)
            
            return answer_data
            
        except Exception as e:
            logger.error(f"Gemini API call failed for question {question.placeholder}: {e}")
            raise
    
    def _create_extraction_prompt(self, question_prompt: str, placeholder: str, 
                                context_text: str, document_context: Dict) -> str:
        """Create a structured prompt for data extraction"""
        
        return f"""You are an expert data extraction AI analyzing insurance documents. Extract specific information based on the question provided.

DOCUMENT CONTEXT:
{context_text}

EXTRACTION QUESTION:
{question_prompt}

INSTRUCTIONS:
1. Analyze the provided document context carefully
2. Extract the specific information requested in the question
3. If the information is not found, respond with "Not specified" or "Not found"
4. Be precise and factual - only extract information that is explicitly stated
5. For numerical values, include units when specified
6. For dates, use a consistent format (MM/DD/YYYY or as stated in document)
7. Keep your response concise and directly answer the question

RESPONSE FORMAT:
Provide only the extracted information as your answer. Do not include explanations or additional commentary unless specifically requested.

ANSWER:"""
    
    def _parse_gemini_response(self, response_text: str, relevant_chunks: List[Dict]) -> Dict:
        """Parse Gemini response and identify source chunks"""
        
        # Clean up the response text
        answer = response_text.strip()
        
        # Remove "ANSWER:" prefix if present
        if answer.startswith("ANSWER:"):
            answer = answer[7:].strip()
        
        # Find the most relevant source chunks for this answer
        source_chunks = []
        
        # Take top 3 most relevant chunks as sources
        for i, chunk in enumerate(relevant_chunks[:3]):
            source_chunks.append({
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"][:200] + "..." if len(chunk["text"]) > 200 else chunk["text"],
                "page_range": f"{chunk['metadata'].get('start_page', 'N/A')}-{chunk['metadata'].get('end_page', 'N/A')}",
                "relevance_score": chunk.get("distance", 0.0),
                "quote_index": i + 1
            })
        
        return {
            "answer": answer,
            "source_chunks": source_chunks,
            "word_count": len(answer.split())
        }
    
    def _prepare_context_from_chunks(self, chunks: List[Dict]) -> str:
        """
        Prepare context text from document chunks using best practices for LLM processing
        
        Best practices implemented:
        1. Prioritize chunks by relevance score (distance)
        2. Include page context for better understanding
        3. Maintain chunk boundaries for clarity
        4. Limit total context to stay within token limits
        5. Preserve important metadata
        """
        
        if not chunks:
            raise ValueError("No document chunks provided")
        
        # Sort chunks by relevance (lower distance = more relevant)
        sorted_chunks = sorted(chunks, key=lambda x: x.get("distance", float('inf')))
        
        context_parts = []
        total_tokens = 0
        max_context_tokens = 8000  # Leave room for prompt and response
        
        for i, chunk in enumerate(sorted_chunks):
            metadata = chunk.get("metadata", {})
            
            # Create clear section headers with metadata
            page_info = f"Pages {metadata.get('start_page', 'N/A')}-{metadata.get('end_page', 'N/A')}"
            filename = metadata.get('filename', 'Document')
            
            section_header = f"=== DOCUMENT SECTION {i+1} ===\nSource: {filename} ({page_info})\n"
            section_content = f"{chunk['text']}\n"
            section_footer = f"=== END SECTION {i+1} ===\n\n"
            
            full_section = section_header + section_content + section_footer
            
            # Estimate tokens (rough approximation: 4 chars per token)
            # TODO: Replace with actual tokenizer if available
            section_tokens = len(full_section) // 4
            
            if total_tokens + section_tokens > max_context_tokens:
                logger.info(f"Reached token limit, using {i} chunks out of {len(sorted_chunks)}")
                break
            
            context_parts.append(full_section)
            total_tokens += section_tokens
        
        if not context_parts:
            raise ValueError("No chunks could fit within token limits")
        
        return "".join(context_parts)
    
    def _generate_placeholder_responses(self, agent_questions: List[QuestionOut]) -> Dict[str, Any]:
        """Generate placeholder responses when LLM service is not available"""
        
        results = {}
        
        for question in agent_questions:
            results[question.placeholder] = {
                "answer": f"[LLM service not available - placeholder for: {question.prompt}]",
                "source_chunks": [],
                "error": "LLM service not configured"
            }
        
        return {
            "success": False,
            "results": results,
            "total_questions": len(agent_questions),
            "processed_chunks": 0,
            "model_used": "placeholder",
            "error": "LLM service not available"
        }
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get current status of the LLM service"""
        
        return {
            "available": self.available,
            "model": self.model_name if self.available else None,
            "api_key_configured": bool(self.api_key),
            "service_type": "Gemini 2.5 Flash-Lite"
        }


# Global service instance
llm_service = LLMService()
