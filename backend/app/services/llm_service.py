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
from enum import Enum
from app.schemas import QuestionOut
from app.services.performance_monitor import time_operation, get_performance_monitor
from app.config import (
    LLM_MODEL_NAME,
    GEMINI_API_KEY,
    LLM_MAX_CONTEXT_TOKENS_PER_QUESTION,
    LLM_TEMPERATURE,
    LLM_THINKING_BUDGET,
    LLM_RESPONSE_FORMAT,
    VECTOR_SEARCH_MAX_SOURCE_QUOTES,
    QUOTE_CONTEXT_CHARS,
    MAX_QUOTE_LENGTH,
    MIN_ANSWER_CONFIDENCE,
    ANSWER_NOT_FOUND_PHRASES
)

logger = logging.getLogger(__name__)


class AnswerQuality(Enum):
    """Enum for answer quality assessment"""
    FOUND = "found"
    NOT_FOUND = "not_found"
    PARTIAL = "partial"
    UNCERTAIN = "uncertain"


class LLMService:
    """Service for AI-powered data extraction with cost optimization"""
    
    def __init__(self):
        self.model_name = LLM_MODEL_NAME
        self.api_key = GEMINI_API_KEY
        self.available = False
        self.client = None
        
        try:
            import google.generativeai as genai
            
            if not self.api_key:
                logger.warning("GEMINI_API_KEY not found in environment variables")
                raise ValueError("Gemini API key not configured")
            
            # Configure the API key
            genai.configure(api_key=self.api_key)
            
            # Initialize the model
            self.model = genai.GenerativeModel(self.model_name)
            self.available = True
            
            # Store genai for later use
            self.genai = genai
            
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
                response_schema=self._create_batch_response_schema(agent_questions),
                temperature=LLM_TEMPERATURE,
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
        
        performance_monitor = get_performance_monitor()
        
        # Create a single batch prompt with all questions and their individual contexts
        with time_operation("llm_batch_prompt_preparation", 
                          {"question_count": len(questions_with_chunks)}) as timer:
            batch_prompt = self._create_batch_prompt_with_individual_contexts(
                questions_with_chunks, document_context
            )
            prompt_prep_time = timer.stop().duration
        
        # Write the batch prompt to a text file for debugging
        with open("batch_prompt_debug.txt", "w", encoding="utf-8") as f:
            f.write(batch_prompt)
        
        try:
            # Configure generation parameters
            generation_config = self.genai.types.GenerationConfig(
                temperature=LLM_TEMPERATURE,
                response_mime_type="application/json"
            )
            
            # Single API call for all questions - maximum cost efficiency
            with time_operation("llm_api_call", 
                              {"question_count": len(questions_with_chunks), 
                               "model": self.model_name,
                               "prompt_length": len(batch_prompt)}) as timer:
                response = self.model.generate_content(
                    batch_prompt,
                    generation_config=generation_config
                )
                api_call_time = timer.stop().duration
            
            if not response or not response.text:
                raise ValueError("Empty response from Gemini model")
            
            # Parse the batch JSON response
            with time_operation("llm_response_parsing", 
                              {"response_length": len(response.text)}) as timer:
                batch_results = self._parse_batch_response_with_individual_contexts(
                    response.text, questions_with_chunks
                )
                parsing_time = timer.stop().duration
            
            # Log comprehensive timing breakdown
            total_time = prompt_prep_time + api_call_time + parsing_time
            logger.info(f"🤖 LLM Processing Complete: {len(questions_with_chunks)} questions in {total_time:.2f}s")
            logger.info(f"⏱️  LLM Timing Breakdown - Prep: {prompt_prep_time*1000:.1f}ms, "
                       f"API: {api_call_time*1000:.1f}ms, Parse: {parsing_time*1000:.1f}ms")
            logger.info(f"🚀 LLM Performance - {len(questions_with_chunks)/total_time:.1f} questions/sec, "
                       f"API latency: {api_call_time*1000:.0f}ms")
            
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
        
        return f"""You are an expert data extraction AI. Extract specific information for ALL questions provided below. Each question has its own relevant context section.

{questions_section}

INSTRUCTIONS:
1. For each question, analyze ONLY its specific relevant context section
2. Extract the specific information requested for each question
3. If information is not found in a question's context, respond with "Not specified" or "Not found"
4. Be precise and factual - only extract information that is explicitly has support in the context
5. For numerical values, include units when specified
6. For dates, use a consistent format (MM/DD/YYYY or as stated in document)
7. Directly answer each question
8. Respond in the exact JSON format specified

RESPONSE FORMAT:
You must respond with a valid JSON object containing answers for all questions using their IDs as keys."""

    def _create_batch_response_schema_from_questions_with_chunks(self, questions_with_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create JSON schema for structured batch response from questions with chunks - simplified for compatibility"""
        
        # For the older API, we'll use a simpler approach without schema validation
        # This ensures compatibility with google-generativeai 0.8.2
        return {}

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
                    
                    # Create structured result with intelligent source chunks using answer quality analysis
                    results[placeholder] = {
                        "answer": answer,
                        "source_chunks": self._get_source_chunks_for_question(relevant_chunks, answer, question.prompt),
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

    def _get_source_chunks_for_question(self, relevant_chunks: List[Dict], answer: str, question_prompt: str) -> List[Dict]:
        """
        Get intelligent source chunks for a specific question using answer quality analysis and precise quote extraction
        
        Args:
            relevant_chunks: List of relevant document chunks
            answer: The LLM's answer for quality analysis
            question_prompt: The original question prompt for quote extraction
            
        Returns:
            List of source chunk dictionaries with precise quotes or empty list if answer not found
        """
        
        # Analyze answer quality to determine if we should include quotes
        answer_quality = self._analyze_answer_quality(answer)
        
        # Only return source quotes for FOUND answers
        if answer_quality != AnswerQuality.FOUND:
            logger.info(f"Answer quality is {answer_quality.value}, returning empty source chunks for answer: {answer[:50]}...")
            return []
        
        # For found answers, use precise quote extraction
        precise_quotes = self._extract_precise_quotes(answer, relevant_chunks, question_prompt)
        if precise_quotes:
            logger.info(f"Using {len(precise_quotes)} precise quotes for FOUND answer")
            return precise_quotes
        else:
            logger.warning("Precise quote extraction failed for FOUND answer, returning empty list")
            return []
    
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
8. Do not use the file name as a source - only use actual content from the document

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
    
    def _analyze_answer_quality(self, answer: str) -> AnswerQuality:
        """
        Analyze answer text to determine if information was actually found
        
        Args:
            answer: The LLM's answer text
            
        Returns:
            AnswerQuality enum indicating whether information was found
        """
        
        if not answer or not answer.strip():
            return AnswerQuality.NOT_FOUND
        
        answer_lower = answer.lower().strip()
        
        # Check for explicit "not found" phrases
        for phrase in ANSWER_NOT_FOUND_PHRASES:
            if phrase in answer_lower:
                return AnswerQuality.NOT_FOUND
        
        # Check for partial information indicators
        partial_indicators = [
            "partially", "some", "limited", "incomplete", "partial",
            "may be", "might be", "appears to be", "seems to be"
        ]
        
        for indicator in partial_indicators:
            if indicator in answer_lower:
                return AnswerQuality.PARTIAL
        
        # Check for uncertainty indicators
        uncertainty_indicators = [
            "uncertain", "unclear", "ambiguous", "possibly", "potentially",
            "likely", "probably", "maybe", "perhaps", "could be"
        ]
        
        for indicator in uncertainty_indicators:
            if indicator in answer_lower:
                return AnswerQuality.UNCERTAIN
        
        # If answer contains actual content and no negative indicators, consider it found
        # Additional check: answer should be more than just a few words
        if len(answer.strip()) > 3 and not answer_lower.startswith(("n/a", "na", "none")):
            return AnswerQuality.FOUND
        
        return AnswerQuality.NOT_FOUND
    
    def _create_quote_extraction_prompt(self, answer: str, chunks: List[Dict], question: str) -> str:
        """
        Create specialized prompt for LLM to identify exact supporting text with precise positioning
        
        Args:
            answer: The extracted answer from the LLM
            chunks: List of relevant document chunks
            question: The original question prompt
            
        Returns:
            Formatted prompt for exact quote extraction optimized for cheap/bad models
        """
        
        # Prepare chunks with clear numbering and page information
        chunks_section = ""
        for i, chunk in enumerate(chunks, 1):
            metadata = chunk.get("metadata", {})
            page_info = f"Pages {metadata.get('start_page', 'N/A')}-{metadata.get('end_page', 'N/A')}"
            filename = metadata.get('filename', 'Document')
            
            # Extract specific page numbers from chunk text if available
            page_markers = []
            lines = chunk['text'].split('\n')
            for line in lines:
                if '--- PAGE' in line and '---' in line:
                    page_markers.append(line.strip())
            
            page_info_detailed = f"{page_info}"
            if page_markers:
                page_info_detailed += f" (Contains: {', '.join(page_markers[:3])})"
            
            chunks_section += f"""
=== CHUNK {i} ===
Source: {filename} ({page_info_detailed})
Text: {chunk['text']}

"""
        
        return f"""You are a precise text extraction system. Your ONLY job is to find EXACT text strings from the document that support the given answer.

1. COPY EXACT TEXT ONLY - Do NOT paraphrase, summarize, or change ANY words
2. EXTRACT VERBATIM - The text must appear EXACTLY as written in the document
3. NO INTERPRETATION - Just find and copy the exact supporting strings
4. MAXIMUM PRECISION - Find the shortest exact text that supports the answer

QUESTION: {question}

ANSWER TO SUPPORT: {answer}

DOCUMENT CHUNKS:
{chunks_section}

TASK:
Find the EXACT text strings (word-for-word) from the chunks that support the answer. You must:

1. Copy text EXACTLY as it appears - no changes, no paraphrasing
2. Find the shortest exact text that supports the answer
3. If the answer mentions "Company A", find the exact text containing "Company A" 
4. Include minimal context (2-3 words before/after) only if needed for clarity
5. Maximum {MAX_QUOTE_LENGTH} characters per quote
6. Return up to {VECTOR_SEARCH_MAX_SOURCE_QUOTES} most relevant exact matches

RESPONSE FORMAT - EXACT JSON:
[
  {{
    "chunk_number": 1,
    "exact_text": "EXACT STRING FROM DOCUMENT",
    "page_context": "PAGE X context if available",
    "start_context": "few words before",
    "end_context": "few words after"
  }}
]

EXAMPLE:
If answer is "Company A Limited" and document contains "The insurer is Company A Limited with policy", respond:
[
  {{
    "chunk_number": 1,
    "exact_text": "Company A Limited",
    "page_context": "PAGE 5",
    "start_context": "The insurer is",
    "end_context": "with policy"
  }}
]

IMPORTANT: Return EMPTY ARRAY [] if no exact supporting text found. Do NOT make up or approximate text."""

    def _parse_quote_extraction_response(self, response: str, chunks: List[Dict]) -> List[Dict]:
        """
        Parse LLM response containing exact supporting text with precise page tracking
        
        Args:
            response: JSON response from quote extraction LLM call
            chunks: Original chunks for mapping back to metadata
            
        Returns:
            List of precise quote dictionaries with exact positioning and page numbers
        """
        
        try:
            quote_data = json.loads(response)
            
            if not isinstance(quote_data, list):
                logger.warning("Quote extraction response is not a list, returning empty quotes")
                return []
            
            precise_quotes = []
            
            for i, quote_item in enumerate(quote_data):
                if not isinstance(quote_item, dict):
                    continue
                
                chunk_number = quote_item.get("chunk_number", 0)
                exact_text = quote_item.get("exact_text", "")
                page_context = quote_item.get("page_context", "")
                start_context = quote_item.get("start_context", "")
                end_context = quote_item.get("end_context", "")
                
                # Validate chunk number and get corresponding chunk
                if chunk_number < 1 or chunk_number > len(chunks):
                    logger.warning(f"Invalid chunk number {chunk_number} in quote extraction")
                    continue
                
                chunk = chunks[chunk_number - 1]  # Convert to 0-based index
                metadata = chunk.get("metadata", {})
                
                # Extract document_id and validate it exists
                document_id = metadata.get("document_id", "")
                if not document_id:
                    logger.warning(f"Chunk {chunk.get('chunk_id', 'unknown')} missing document_id in metadata, skipping quote")
                    continue
                
                # Extract precise page number from page_context or chunk text
                precise_page = self._extract_precise_page_number(exact_text, chunk['text'], page_context, metadata)
                
                # Build the full quote text with context for display
                full_quote_text = ""
                if start_context:
                    full_quote_text += start_context + " "
                full_quote_text += exact_text
                if end_context:
                    full_quote_text += " " + end_context
                
                # Trim to maximum length if needed
                if len(full_quote_text) > MAX_QUOTE_LENGTH:
                    full_quote_text = full_quote_text[:MAX_QUOTE_LENGTH] + "..."
                
                # Create precise quote with exact positioning
                precise_quote = {
                    "chunk_id": chunk["chunk_id"],
                    "document_id": document_id,
                    "text": full_quote_text.strip(),
                    "exact_text": exact_text,  # The exact string for highlighting
                    "start_context": start_context,
                    "end_context": end_context,
                    "page_range": str(precise_page) if precise_page else f"{metadata.get('start_page', 'N/A')}-{metadata.get('end_page', 'N/A')}",
                    "precise_page": precise_page,  # Specific page number for highlighting
                    "page_context": page_context,
                    "relevance_score": chunk.get("distance", 0.0),
                    "quote_index": i + 1
                }
                
                precise_quotes.append(precise_quote)
            
            logger.info(f"Extracted {len(precise_quotes)} precise quotes with exact positioning")
            return precise_quotes
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse quote extraction JSON response: {e}")
            logger.error(f"Raw response: {response}")
            return []
        except Exception as e:
            logger.error(f"Error processing quote extraction response: {e}")
            return []
    
    def _extract_precise_page_number(self, exact_text: str, chunk_text: str, page_context: str, metadata: Dict) -> Optional[int]:
        """
        Extract the precise page number where the exact text appears
        
        Args:
            exact_text: The exact text to find
            chunk_text: The full chunk text
            page_context: Page context from LLM (e.g., "PAGE 5")
            metadata: Chunk metadata with page range
            
        Returns:
            Specific page number or None if not found
        """
        
        # First, try to extract from page_context provided by LLM
        if page_context:
            import re
            page_match = re.search(r'PAGE\s+(\d+)', page_context, re.IGNORECASE)
            if page_match:
                try:
                    return int(page_match.group(1))
                except ValueError:
                    pass
        
        # Second, try to find the exact text in chunk and determine its page
        if exact_text and chunk_text:
            # Find the position of exact_text in chunk_text
            text_position = chunk_text.lower().find(exact_text.lower())
            if text_position != -1:
                # Look for page markers before this position
                text_before = chunk_text[:text_position]
                page_markers = []
                
                import re
                for match in re.finditer(r'--- PAGE (\d+) ---', text_before):
                    try:
                        page_markers.append(int(match.group(1)))
                    except ValueError:
                        continue
                
                # Return the last page marker found before the text
                if page_markers:
                    return page_markers[-1]
        
        # Fallback: if chunk spans only one page, use that
        start_page = metadata.get('start_page')
        end_page = metadata.get('end_page')
        if start_page == end_page and start_page:
            return start_page
        
        # Final fallback: use start page
        return start_page
    
    def _extract_precise_quotes(self, answer: str, relevant_chunks: List[Dict], question_prompt: str) -> List[Dict]:
        """
        Use LLM to identify specific text portions that support the answer
        
        Args:
            answer: The extracted answer from the LLM
            relevant_chunks: List of relevant document chunks
            question_prompt: The original question prompt
            
        Returns:
            List of precise quote dictionaries with supporting text
        """
        
        if not relevant_chunks:
            logger.info("No relevant chunks provided for quote extraction")
            return []
        
        try:
            # Create quote extraction prompt
            quote_prompt = self._create_quote_extraction_prompt(answer, relevant_chunks, question_prompt)
            
            # Configure for quote extraction (use JSON output)
            generation_config = self.genai.types.GenerationConfig(
                temperature=0.0,  # Low temperature for consistent extraction
                response_mime_type="application/json"
            )
            
            # Make LLM call for quote extraction
            response = self.model.generate_content(
                quote_prompt,
                generation_config=generation_config
            )
            
            if not response or not response.text:
                logger.warning("Empty response from quote extraction LLM call")
                return []
            
            # Parse the quote extraction response
            precise_quotes = self._parse_quote_extraction_response(response.text, relevant_chunks)
            
            logger.info(f"Successfully extracted {len(precise_quotes)} precise quotes for answer: {answer[:50]}...")
            return precise_quotes
            
        except Exception as e:
            logger.error(f"Failed to extract precise quotes: {e}")
            # Return empty list on failure - don't break the main processing
            return []
    
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
