"""
LLM Service

Provides AI-powered data extraction from document chunks.
Optimized for cost-efficient RAG processing with batch inferencing.
Uses Gemini 2.5 Flash-Lite for maximum cost efficiency.

TODO: generalize later to support multiple LLM providers/models
TODO: add custom embeddings so we don't need to use chromas default embeddings (I am thinking of using voyager)
"""

import logging
import os
from typing import List, Dict, Any, Optional, Union
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from app.schemas import QuestionOut
from app.config import (
    LLM_MODEL_NAME,
    GEMINI_API_KEY,
    LLM_MAX_CONTEXT_TOKENS_PER_QUESTION,
    LLM_TEMPERATURE,
    LLM_THINKING_BUDGET,
    LLM_RESPONSE_FORMAT,
    VECTOR_SEARCH_MAX_SOURCE_QUOTES
)

logger = logging.getLogger(__name__)


class LLMService:
    """Service for AI-powered data extraction with cost optimization"""
    
    def __init__(self):
        self.model_name = LLM_MODEL_NAME
        self.api_key = GEMINI_API_KEY
        self.available = False
        self.client = None
        
        try:
            from google import genai
            from google.genai import types
            
            if not self.api_key:
                logger.warning("GEMINI_API_KEY not found in environment variables")
                raise ValueError("Gemini API key not configured")
            
            # Initialize the client - new API gets API key from environment automatically
            self.client = genai.Client(api_key=self.api_key)
            self.available = True
            
            # Store types for configuration
            self.types = types
            
            logger.info(f"Initialized cost-optimized LLM service with model: {self.model_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Gemini LLM service: {e}")
            self.client = None
    
    def process_agent_questions(self, questions_with_chunks: List[Dict[str, Any]], 
                              document_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process all agent questions in a single batch request with question-specific contexts
        
        Args:
            questions_with_chunks: List of dicts with 'question' and 'relevant_chunks' for each question
            document_context: Additional context about the documents
            
        Returns:
            Dictionary with extracted answers and source references
            
        Raises:
            ValueError: If no questions provided or LLM service is not available
        """
        
        if not questions_with_chunks:
            raise ValueError("No questions with chunks provided for processing")
        
        if not self.available:
            raise ValueError("LLM service is not available. Please ensure GEMINI_API_KEY is configured and the service is properly initialized.")
        
        try:
            # Process ALL questions in a single batch request with individual contexts
            batch_results = self._process_questions_batch_with_individual_contexts(
                questions_with_chunks, document_context
            )
            
            total_chunks = sum(len(item['relevant_chunks']) for item in questions_with_chunks)
            
            return {
                "success": True,
                "results": batch_results,
                "total_questions": len(questions_with_chunks),
                "processed_chunks": total_chunks,
                "model_used": self.model_name,
                "processing_method": "batch_optimized_individual_contexts"
            }
            
        except Exception as e:
            logger.error(f"Failed to process agent questions in batch: {e}")
            raise ValueError(f"LLM batch processing failed: {str(e)}")
    
    def _process_questions_batch(self, agent_questions: List[QuestionOut], context_text: str, 
                               relevant_chunks: List[Dict], document_context: Dict) -> Dict[str, Any]:
        """Process all questions in a single batch request for maximum cost efficiency"""
        
        # Create a single batch prompt with all questions
        batch_prompt = self._create_batch_extraction_prompt(
            agent_questions, context_text, document_context
        )
        
        try:
            # Configure for cost optimization and structured output
            config = self.types.GenerateContentConfig(
                # Use configurable thinking budget
                thinking_config=self.types.ThinkingConfig(thinking_budget=LLM_THINKING_BUDGET),
                # Use structured JSON output for consistent parsing
                response_mime_type=LLM_RESPONSE_FORMAT,
                response_schema=self._create_batch_response_schema(agent_questions)
            )
            
            # Single API call for all questions - maximum cost efficiency
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=batch_prompt,
                config=config
            )
            
            if not response or not response.text:
                raise ValueError("Empty response from Gemini model")
            
            # Parse the batch JSON response
            batch_results = self._parse_batch_response(response.text, agent_questions, relevant_chunks)
            
            logger.info(f"Successfully processed {len(agent_questions)} questions in single batch request")
            return batch_results
            
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            raise ValueError(f"Failed to process questions in batch: {str(e)}")
    
    def _process_questions_batch_with_individual_contexts(self, questions_with_chunks: List[Dict[str, Any]], 
                                                        document_context: Dict) -> Dict[str, Any]:
        """Process all questions in a single batch request, each with its own relevant context"""
        
        # Create a single batch prompt with all questions and their individual contexts
        batch_prompt = self._create_batch_prompt_with_individual_contexts(
            questions_with_chunks, document_context
        )
        
        try:
            # Configure for cost optimization and structured output
            config = self.types.GenerateContentConfig(
                # Use configurable thinking budget
                thinking_config=self.types.ThinkingConfig(thinking_budget=LLM_THINKING_BUDGET),
                # Use structured JSON output for consistent parsing
                response_mime_type=LLM_RESPONSE_FORMAT,
                response_schema=self._create_batch_response_schema_from_questions_with_chunks(questions_with_chunks)
            )
            
            # Single API call for all questions - maximum cost efficiency
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=batch_prompt,
                config=config
            )
            
            if not response or not response.text:
                raise ValueError("Empty response from Gemini model")
            
            # Parse the batch JSON response
            batch_results = self._parse_batch_response_with_individual_contexts(
                response.text, questions_with_chunks
            )
            
            logger.info(f"Successfully processed {len(questions_with_chunks)} questions with individual contexts in single batch request")
            return batch_results
            
        except Exception as e:
            logger.error(f"Batch processing with individual contexts failed: {e}")
            raise ValueError(f"Failed to process questions in batch: {str(e)}")

    def _create_batch_prompt_with_individual_contexts(self, questions_with_chunks: List[Dict[str, Any]], 
                                                    document_context: Dict) -> str:
        """Create a single batch prompt where each question has its own relevant context"""
        
        questions_section = ""
        
        for i, item in enumerate(questions_with_chunks, 1):
            question = item['question']
            relevant_chunks = item['relevant_chunks']
            
            # Prepare individual context for this question
            context_text = self._prepare_context_from_chunks(relevant_chunks) if relevant_chunks else "No relevant context found"
            
            questions_section += f"""
=== QUESTION {i} (ID: {question.placeholder}) ===
QUESTION: {question.prompt}

RELEVANT CONTEXT FOR THIS QUESTION:
{context_text}

"""
        
        return f"""You are an expert data extraction AI analyzing insurance documents. Extract specific information for ALL questions provided below. Each question has its own relevant context section.

{questions_section}

INSTRUCTIONS:
1. For each question, analyze ONLY its specific relevant context section
2. Extract the specific information requested for each question
3. If information is not found in a question's context, respond with "Not specified" or "Not found"
4. Be precise and factual - only extract information that is explicitly stated
5. For numerical values, include units when specified
6. For dates, use a consistent format (MM/DD/YYYY or as stated in document)
7. Keep responses concise and directly answer each question
8. Respond in the exact JSON format specified

RESPONSE FORMAT:
You must respond with a valid JSON object containing answers for all questions using their IDs as keys."""

    def _create_batch_response_schema_from_questions_with_chunks(self, questions_with_chunks: List[Dict[str, Any]]) -> 'self.types.Schema':
        """Create JSON schema for structured batch response from questions with chunks"""
        
        properties = {}
        required_fields = []
        
        for item in questions_with_chunks:
            question = item['question']
            properties[question.placeholder] = self.types.Schema(type=self.types.Type.STRING)
            required_fields.append(question.placeholder)
        
        return self.types.Schema(
            type=self.types.Type.OBJECT,
            properties=properties,
            required=required_fields
        )

    def _parse_batch_response_with_individual_contexts(self, response_text: str, 
                                                     questions_with_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse batch JSON response for questions with individual contexts"""
        
        try:
            # Parse JSON response
            batch_data = json.loads(response_text)
            
            results = {}
            
            for item in questions_with_chunks:
                question = item['question']
                relevant_chunks = item['relevant_chunks']
                placeholder = question.placeholder
                
                if placeholder in batch_data:
                    answer = batch_data[placeholder]
                    
                    # Create structured result with question-specific source chunks
                    results[placeholder] = {
                        "answer": answer,
                        "source_chunks": self._get_source_chunks_for_question(relevant_chunks),
                        "word_count": len(answer.split()) if answer else 0
                    }
                else:
                    # Question missing from response - create empty result
                    logger.warning(f"Question {placeholder} missing from batch response")
                    results[placeholder] = {
                        "answer": "Not processed",
                        "source_chunks": [],
                        "word_count": 0
                    }
            
            return results
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse batch JSON response: {e}")
            logger.error(f"Raw response: {response_text}")
            
            # Create error results for all questions
            results = {}
            for item in questions_with_chunks:
                question = item['question']
                results[question.placeholder] = {
                    "answer": "JSON parsing error",
                    "source_chunks": [],
                    "word_count": 0,
                    "error": "Failed to parse batch response"
                }
            
            return results

    def _get_source_chunks_for_question(self, relevant_chunks: List[Dict]) -> List[Dict]:
        """Get source chunks for a specific question (top 3 most relevant)"""
        
        source_chunks = []
        
        # Take configurable number of most relevant chunks as sources for this specific question
        for i, chunk in enumerate(relevant_chunks[:VECTOR_SEARCH_MAX_SOURCE_QUOTES]):
            source_chunks.append({
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"][:200] + "..." if len(chunk["text"]) > 200 else chunk["text"],
                "page_range": f"{chunk['metadata'].get('start_page', 'N/A')}-{chunk['metadata'].get('end_page', 'N/A')}",
                "relevance_score": chunk.get("distance", 0.0),
                "quote_index": i + 1
            })
        
        return source_chunks
    
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
        
        # Take configurable number of most relevant chunks as sources
        for i, chunk in enumerate(relevant_chunks[:VECTOR_SEARCH_MAX_SOURCE_QUOTES]):
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
        max_context_tokens = LLM_MAX_CONTEXT_TOKENS_PER_QUESTION  # Use configurable limit
        
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
