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
from typing import List, Dict, Any, Optional, Union, Tuple
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from app.schemas import QuestionOut, AnswerType
from app.services.performance_monitor import time_operation, get_performance_monitor
from app.services.bbox_matcher import BBoxMatcher
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
    ANSWER_NOT_FOUND_PHRASES,
    MAX_CONCURRENT_QUOTE_EXTRACTIONS,
    MAX_CONCURRENT_LLM_REQUESTS,
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

    def _execute_parallel(
        self,
        items: List[Any],
        worker_fn: callable,
        key_fn: callable,
        max_workers: int,
        aggregate_lists: bool = False,
        error_result_fn: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Generic parallel executor for LLM operations using ThreadPoolExecutor.

        This utility provides a reusable pattern for executing multiple independent
        LLM operations in parallel while handling errors gracefully.

        Args:
            items: List of items to process
            worker_fn: Function that processes a single item, returns (key, result) or (key, ..., result, ...)
            key_fn: Function to extract the key from an item (for error handling fallback)
            max_workers: Maximum number of concurrent workers
            aggregate_lists: If True, aggregate results into lists by key (for multi-result per key).
                           If False, direct assignment (one result per key).
            error_result_fn: Optional function that returns a default error result given (key, error).
                           If None, errors are logged but key may be missing from results.

        Returns:
            Dictionary mapping keys to results (or lists of results if aggregate_lists=True)
        """
        results: Dict[str, Any] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = {
                executor.submit(worker_fn, item): key_fn(item)
                for item in items
            }

            # Collect results as they complete
            for future in as_completed(futures):
                fallback_key = futures[future]
                try:
                    result = future.result()

                    # Handle different return formats: (key, data) or (key, ..., data, ...)
                    if isinstance(result, tuple) and len(result) >= 2:
                        key = result[0]
                        data = result[-1] if len(result) == 2 else result[1:]
                    else:
                        key = fallback_key
                        data = result

                    if aggregate_lists:
                        if key not in results:
                            results[key] = []
                        if isinstance(data, list):
                            results[key].extend(data)
                        else:
                            results[key].append(data)
                    else:
                        # For tuple results like (key, result_dict), extract the result_dict
                        if isinstance(result, tuple) and len(result) == 2:
                            results[key] = result[1]
                        else:
                            results[key] = data

                except Exception as e:
                    logger.warning(f"Parallel execution failed for {fallback_key}: {e}")
                    if error_result_fn:
                        if aggregate_lists:
                            if fallback_key not in results:
                                results[fallback_key] = []
                            results[fallback_key].append(error_result_fn(fallback_key, e))
                        else:
                            results[fallback_key] = error_result_fn(fallback_key, e)

        return results

    def process_agent_questions(self, questions_with_chunks: List[Dict[str, Any]], 
                              document_context: Dict[str, Any],
                              bbox_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Process all agent questions in a single batch request with question-specific contexts
        
        Args:
            questions_with_chunks: List of dicts with 'question' and 'relevant_chunks' for each question
            document_context: Additional context about the documents
            bbox_data: Optional dictionary mapping document_ids to their bounding box data for OCR documents
            
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
            # Process ALL questions in a single batch request with individual contexts and bbox data
            batch_results = self._process_questions_batch_with_individual_contexts(
                questions_with_chunks, document_context, bbox_data
            )
            
            total_chunks = sum(len(item['relevant_chunks']) for item in questions_with_chunks)
            
            return {
                "success": True,
                "results": batch_results,
                "total_questions": len(questions_with_chunks),
                "processed_chunks": total_chunks,
                "model_used": self.model_name,
                "processing_method": "parallel_individual_calls"
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
                                                        document_context: Dict,
                                                        bbox_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Process all questions with individual API calls in parallel.

        REFACTORED: Now uses parallel per-question API calls instead of a single batch prompt.
        This provides better quality (focused context) with similar latency (parallel execution).
        """
        # Phase 1: Parallel LLM calls for all questions
        with time_operation("llm_parallel_question_processing",
                          {"question_count": len(questions_with_chunks)}) as timer:
            raw_results = self._process_questions_parallel_threaded(questions_with_chunks, document_context)
            parallel_processing_time = timer.stop().duration

        logger.info(f"LLM Parallel Processing: {len(questions_with_chunks)} questions in {parallel_processing_time:.2f}s")

        # Phase 2: Prepare questions needing quote extraction
        questions_needing_quotes = []
        results = {}
        quote_extraction_time = 0

        for item in questions_with_chunks:
            question = item['question']
            relevant_chunks = item['relevant_chunks']
            placeholder = question.placeholder

            if placeholder in raw_results:
                raw_result = raw_results[placeholder]
                answer = raw_result.get("answer", "Not processed")

                # Initialize result structure
                results[placeholder] = {
                    "answer": answer,
                    "source_chunks": [],
                    "word_count": raw_result.get("word_count", 0),
                }

                # Add error if present
                if raw_result.get("error"):
                    results[placeholder]["error"] = raw_result["error"]
                    continue  # Skip quote extraction for errored questions

                # Collect questions needing quotes based on answer type
                if question.answer_type == AnswerType.STRING:
                    answer_str = str(answer) if answer else ""
                    answer_quality = self._analyze_answer_quality(answer_str)

                    if answer_quality == AnswerQuality.FOUND and relevant_chunks:
                        questions_needing_quotes.append({
                            "placeholder": placeholder,
                            "answer": answer_str,
                            "question_prompt": question.prompt,
                            "relevant_chunks": relevant_chunks,
                            "answer_type": "string",
                            "target": None
                        })
                else:
                    # List/Table answers: collect individual quotable values
                    quotable_values = self._get_quotable_values_from_answer(answer, question)
                    for qv in quotable_values:
                        value = qv["value"]
                        target = qv["target"]
                        answer_quality = self._analyze_answer_quality(value)

                        if answer_quality == AnswerQuality.FOUND and relevant_chunks:
                            questions_needing_quotes.append({
                                "placeholder": placeholder,
                                "answer": value,
                                "question_prompt": f"Find evidence for: {value}",
                                "relevant_chunks": relevant_chunks,
                                "answer_type": "structured",
                                "target": target
                            })
            else:
                # Question missing from results
                logger.warning(f"Question {placeholder} missing from parallel results")
                results[placeholder] = {
                    "answer": "Not processed",
                    "source_chunks": [],
                    "word_count": 0,
                    "error": "Missing from parallel processing results"
                }

        # Phase 3: Batch extract quotes (existing parallel quote extraction)
        if questions_needing_quotes:
            logger.info(f"Extracting quotes for {len(questions_needing_quotes)} items")
            with time_operation("llm_quote_extraction",
                              {"item_count": len(questions_needing_quotes)}) as timer:
                batch_quotes = self._extract_precise_quotes_batch(questions_needing_quotes, bbox_data)
                quote_extraction_time = timer.stop().duration

            # Distribute quotes back to results
            for placeholder, quotes in batch_quotes.items():
                if placeholder in results:
                    results[placeholder]["source_chunks"].extend(quotes)

            logger.info(f"Quote extraction: {quote_extraction_time*1000:.0f}ms for {len(questions_needing_quotes)} items")
        else:
            logger.info("No questions needed quote extraction")

        # Log comprehensive timing
        total_time = parallel_processing_time + quote_extraction_time
        logger.info(f"LLM Processing Complete: {len(questions_with_chunks)} questions in {total_time:.2f}s "
                   f"({len(questions_with_chunks)/total_time:.1f} questions/sec)")

        return results

    def _create_batch_prompt_with_individual_contexts(self, questions_with_chunks: List[Dict[str, Any]],
                                                    document_context: Dict) -> str:
        """Create a single batch prompt where each question has its own relevant context"""

        questions_section = ""

        for i, item in enumerate(questions_with_chunks, 1):
            question = item['question']
            relevant_chunks = item['relevant_chunks']

            # Prepare individual context for this question
            context_text = self._prepare_context_from_chunks(relevant_chunks) if relevant_chunks else "No relevant context found"

            # Get format instruction for this question's answer type
            format_instruction = self._get_answer_format_instruction(question)

            questions_section += f"""
=== QUESTION {i} (ID: {question.placeholder}) ===
QUESTION: {question.prompt}

EXPECTED FORMAT: {format_instruction}

RELEVANT CONTEXT FOR THIS QUESTION:
{context_text}

"""

        # Build dynamic response format section based on question types
        response_format_section = self._build_response_format_section(questions_with_chunks)

        return f"""You are an expert data extraction AI. Extract specific information for ALL questions provided below. Each question has its own relevant context section.

{questions_section}

INSTRUCTIONS:
1. For each question, analyze ONLY its specific relevant context section
2. Extract the specific information requested for each question
3. If information is not found in a question's context, respond with "Not specified" or "Not found"
4. Be precise and factual - only extract information that is explicitly supported in the context
5. For numerical values, include units when specified
6. For dates, use a consistent format (YYYY-MM-DD or as stated in document)
7. Directly answer each question
8. CRITICAL: Follow the EXPECTED FORMAT instruction for each question exactly

{response_format_section}
"""

    def _create_batch_response_schema_from_questions_with_chunks(self, questions_with_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create JSON schema for structured batch response from questions with chunks - simplified for compatibility"""
        
        # For the older API, we'll use a simpler approach without schema validation
        # This ensures compatibility with google-generativeai 0.8.2
        return {}

    def _parse_batch_response_with_individual_contexts(self, response_text: str,
                                                     questions_with_chunks: List[Dict[str, Any]],
                                                     bbox_data: Optional[Dict] = None) -> Dict[str, Any]:
        """Parse batch JSON response for questions with individual contexts"""
        try:
            # Parse JSON response
            batch_data = json.loads(response_text)

            results = {}

            # First pass: collect all questions that need quote extraction
            questions_needing_quotes = []

            for item in questions_with_chunks:
                question = item['question']
                relevant_chunks = item['relevant_chunks']
                placeholder = question.placeholder

                if placeholder in batch_data:
                    answer = batch_data[placeholder]

                    # Initialize result structure
                    results[placeholder] = {
                        "answer": answer,
                        "source_chunks": [],  # Will be populated after batch quote extraction
                        "word_count": self._calculate_word_count(answer)
                    }

                    # Collect questions that need quotes based on answer type
                    if question.answer_type == AnswerType.STRING:
                        answer_str = str(answer) if answer else ""
                        answer_quality = self._analyze_answer_quality(answer_str)

                        if answer_quality == AnswerQuality.FOUND and relevant_chunks:
                            questions_needing_quotes.append({
                                "placeholder": placeholder,
                                "answer": answer_str,
                                "question_prompt": question.prompt,
                                "relevant_chunks": relevant_chunks,
                                "answer_type": "string",
                                "target": None
                            })
                    else:
                        # List/Table answers: collect individual quotable values
                        quotable_values = self._get_quotable_values_from_answer(answer, question)
                        for qv in quotable_values:
                            value = qv["value"]
                            target = qv["target"]
                            answer_quality = self._analyze_answer_quality(value)

                            if answer_quality == AnswerQuality.FOUND and relevant_chunks:
                                questions_needing_quotes.append({
                                    "placeholder": placeholder,
                                    "answer": value,
                                    "question_prompt": f"Find evidence for: {value}",
                                    "relevant_chunks": relevant_chunks,
                                    "answer_type": "structured",
                                    "target": target
                                })
                else:
                    # Question missing from response - create empty result
                    logger.warning(f"Question {placeholder} missing from batch response")
                    results[placeholder] = {
                        "answer": "Not processed",
                        "source_chunks": [],
                        "word_count": 0
                    }

            # Second pass: batch extract quotes for all questions that need them
            if questions_needing_quotes:
                logger.info(f"🔍 Batch extracting quotes for {len(questions_needing_quotes)} items")
                batch_quotes = self._extract_precise_quotes_batch(questions_needing_quotes, bbox_data)

                # Distribute quotes back to results
                for placeholder, quotes in batch_quotes.items():
                    if placeholder in results:
                        # Merge quotes (for structured answers, there may be multiple quote groups)
                        results[placeholder]["source_chunks"].extend(quotes)

                logger.info(f"✅ Batch quote extraction complete")
            else:
                logger.info("No questions needed quote extraction (all answers were NOT_FOUND or empty)")

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

    def _get_source_chunks_for_question(self, relevant_chunks: List[Dict], answer: str, question_prompt: str,
                                       bbox_data: Optional[Dict] = None) -> List[Dict]:
        """
        Get intelligent source chunks for a specific question using answer quality analysis and precise quote extraction
        
        Args:
            relevant_chunks: List of relevant document chunks
            answer: The LLM's answer for quality analysis
            question_prompt: The original question prompt for quote extraction
            bbox_data: Optional dictionary mapping document_ids to their bounding box data
            
        Returns:
            List of source chunk dictionaries with precise quotes or empty list if answer not found
        """
        
        # Analyze answer quality to determine if we should include quotes
        answer_quality = self._analyze_answer_quality(answer)
        
        # Only return source quotes for FOUND answers
        if answer_quality != AnswerQuality.FOUND:
            logger.info(f"Answer quality is {answer_quality.value}, returning empty source chunks for answer: {answer[:50]}...")
            return []
        
        # For found answers, use precise quote extraction with bbox data
        precise_quotes = self._extract_precise_quotes(answer, relevant_chunks, question_prompt, bbox_data)
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

    def _get_answer_format_instruction(self, question: QuestionOut) -> str:
        """
        Generate answer format instruction based on answer_type.

        This creates clear, explicit formatting instructions for the LLM
        to ensure consistent structured output.
        """
        if question.answer_type == AnswerType.STRING:
            return "Respond with a plain text string."

        elif question.answer_type == AnswerType.LIST:
            return (
                'Respond with a JSON array of strings. '
                'Example: ["First item", "Second item", "Third item"]'
            )

        elif question.answer_type == AnswerType.TABLE:
            if not question.columns:
                return "Respond with a plain text string."

            # Build example from column definitions
            column_keys = [col.key for col in question.columns]
            example_row = {key: f"<{key}>" for key in column_keys}
            example_json = json.dumps([example_row], indent=None)

            return (
                f'Respond with a JSON array of objects. '
                f'Each object must have exactly these keys: {column_keys}. '
                f'Example format: {example_json}'
            )

        return "Respond with a plain text string."

    def _get_response_schema_hint(self, question: QuestionOut) -> str:
        """Generate schema hint for JSON response section"""
        if question.answer_type == AnswerType.STRING:
            return f'"{question.placeholder}": "string value"'

        elif question.answer_type == AnswerType.LIST:
            return f'"{question.placeholder}": ["item1", "item2", ...]'

        elif question.answer_type == AnswerType.TABLE:
            if question.columns:
                keys = [col.key for col in question.columns]
                obj_example = ", ".join([f'"{k}": "..."' for k in keys])
                return f'"{question.placeholder}": [{{{obj_example}}}]'
            return f'"{question.placeholder}": "string value"'

        return f'"{question.placeholder}": "string value"'

    def _create_single_question_prompt(self, question: QuestionOut,
                                       relevant_chunks: List[Dict],
                                       document_context: Dict) -> str:
        """
        Create a focused prompt for a SINGLE question with its relevant context.

        This allows the LLM to focus entirely on answering one specific question
        with maximum quality, rather than splitting attention across multiple questions.
        """
        # Prepare context text from chunks
        context_text = self._prepare_context_from_chunks(relevant_chunks) if relevant_chunks else "No relevant context found"

        # Get format instruction for this question's answer type
        format_instruction = self._get_answer_format_instruction(question)

        # Build response schema hint based on answer type
        response_schema = self._get_response_schema_hint(question)

        return f"""You are an expert data extraction AI. Extract specific information based on the provided context.

QUESTION (ID: {question.placeholder}):
{question.prompt}

EXPECTED FORMAT: {format_instruction}

RELEVANT CONTEXT:
{context_text}

INSTRUCTIONS:
1. Analyze the provided context carefully
2. Extract the specific information requested
3. If information is not found, respond with "Not specified" or "Not found"
4. Be precise and factual - only extract information explicitly supported
5. For numerical values, include units when specified
6. For dates, use a consistent format (YYYY-MM-DD or as stated in document)
7. Directly answer the question
8. CRITICAL: Follow the EXPECTED FORMAT instruction exactly

RESPONSE FORMAT (JSON):
{{
  {response_schema}
}}

Respond with valid JSON only."""

    def _process_single_question_sync(self, question_item: Dict[str, Any],
                                       document_context: Dict) -> Tuple[str, Dict[str, Any]]:
        """
        Process a single question synchronously (for ThreadPoolExecutor).

        This method is designed to be called from ThreadPoolExecutor threads.

        Args:
            question_item: Dict with 'question' (QuestionOut) and 'relevant_chunks'
            document_context: Document context dictionary

        Returns:
            Tuple of (placeholder, result_dict)
        """
        question = question_item['question']
        relevant_chunks = question_item['relevant_chunks']
        placeholder = question.placeholder

        try:
            # Create focused prompt for this single question
            prompt = self._create_single_question_prompt(question, relevant_chunks, document_context)

            # Configure generation parameters
            generation_config = self.genai.types.GenerationConfig(
                temperature=LLM_TEMPERATURE,
                response_mime_type="application/json"
            )

            # Make synchronous API call
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config
            )

            if not response or not response.text:
                logger.warning(f"Empty response for question {placeholder}")
                return (placeholder, {
                    "answer": "No response from LLM",
                    "source_chunks": [],
                    "word_count": 0,
                    "error": "Empty LLM response"
                })

            # Parse the JSON response
            response_data = json.loads(response.text)

            # Extract the answer (it should be keyed by placeholder)
            if placeholder in response_data:
                answer = response_data[placeholder]
            else:
                # Fallback: try to get any value from response
                answer = next(iter(response_data.values()), "Not found")

            return (placeholder, {
                "answer": answer,
                "relevant_chunks": relevant_chunks,  # Preserve for quote extraction
                "question": question,  # Preserve for quote extraction
                "source_chunks": [],  # Will be populated after quote extraction
                "word_count": self._calculate_word_count(answer)
            })

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error for question {placeholder}: {e}")
            return (placeholder, {
                "answer": "JSON parsing error",
                "source_chunks": [],
                "word_count": 0,
                "error": f"Failed to parse response: {str(e)}"
            })
        except Exception as e:
            logger.warning(f"Error processing question {placeholder}: {e}")
            return (placeholder, {
                "answer": "Processing error",
                "source_chunks": [],
                "word_count": 0,
                "error": str(e)
            })

    def _process_questions_parallel_threaded(self, questions_with_chunks: List[Dict[str, Any]],
                                              document_context: Dict) -> Dict[str, Dict[str, Any]]:
        """
        Execute question processing in parallel using the generic parallel executor.

        Args:
            questions_with_chunks: List of question dicts with 'question' and 'relevant_chunks'
            document_context: Document context dictionary

        Returns:
            Dictionary mapping placeholder -> result dict
        """
        # Create worker closure that captures document_context
        def process_question(q_item: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
            return self._process_single_question_sync(q_item, document_context)

        def get_placeholder(q_item: Dict[str, Any]) -> str:
            return q_item['question'].placeholder

        def error_result(key: str, error: Exception) -> Dict[str, Any]:
            return {
                "answer": "Thread execution error",
                "source_chunks": [],
                "word_count": 0,
                "error": str(error)
            }

        return self._execute_parallel(
            items=questions_with_chunks,
            worker_fn=process_question,
            key_fn=get_placeholder,
            max_workers=MAX_CONCURRENT_LLM_REQUESTS,
            aggregate_lists=False,
            error_result_fn=error_result
        )

    def _build_response_format_section(self, questions_with_chunks: List[Dict[str, Any]]) -> str:
        """Build the response format section with schema examples for all answer types"""

        schema_lines = []
        has_string = False
        has_list = False
        has_table = False

        for item in questions_with_chunks:
            q = item['question']
            schema_lines.append("  " + self._get_response_schema_hint(q))

            if q.answer_type == AnswerType.STRING:
                has_string = True
            elif q.answer_type == AnswerType.LIST:
                has_list = True
            elif q.answer_type == AnswerType.TABLE:
                has_table = True

        # Build type-specific instructions
        type_instructions = []
        if has_string:
            type_instructions.append("- STRING questions: Return a plain text string value")
        if has_list:
            type_instructions.append("- LIST questions: Return a JSON array of strings")
        if has_table:
            type_instructions.append("- TABLE questions: Return a JSON array of objects with the exact keys specified")

        type_instructions_str = "\n".join(type_instructions) if type_instructions else ""

        return f"""RESPONSE FORMAT:
You must respond with a valid JSON object. Use the following structure:
{{
{chr(10).join(schema_lines)}
}}

FORMAT REQUIREMENTS:
{type_instructions_str}
- Follow the EXPECTED FORMAT instruction for each question exactly
- Ensure all JSON is properly formatted and valid"""

    def _calculate_word_count(self, answer: Any) -> int:
        """Calculate word count for various answer types"""
        if isinstance(answer, str):
            return len(answer.split()) if answer else 0
        elif isinstance(answer, list):
            total = 0
            for item in answer:
                if isinstance(item, str):
                    total += len(item.split())
                elif isinstance(item, dict):
                    for v in item.values():
                        if isinstance(v, str):
                            total += len(v.split())
            return total
        return 0

    def _get_quotable_values_from_answer(self, answer: Any, question: QuestionOut) -> List[Dict[str, Any]]:
        """
        Extract individual quotable values from structured answers (list/table).

        Returns a list of dicts with:
        - 'value': The text value to find quotes for
        - 'target': Dict describing where this value belongs (for associating quotes later)
        """
        quotable_values = []

        if question.answer_type == AnswerType.LIST:
            if isinstance(answer, list):
                for idx, item in enumerate(answer):
                    if isinstance(item, str) and item.strip():
                        quotable_values.append({
                            "value": item,
                            "target": {"type": "list", "index": idx}
                        })

        elif question.answer_type == AnswerType.TABLE:
            if isinstance(answer, list):
                for row_idx, row in enumerate(answer):
                    if isinstance(row, dict):
                        for key, value in row.items():
                            if isinstance(value, str) and value.strip():
                                quotable_values.append({
                                    "value": value,
                                    "target": {"type": "table", "row": row_idx, "key": key}
                                })

        return quotable_values

    def _get_source_chunks_for_structured_answer(self, relevant_chunks: List[Dict],
                                                  answer: Any, question: QuestionOut,
                                                  bbox_data: Optional[Dict] = None) -> List[Dict]:
        """
        Get source chunks for structured answers (list/table) with quotes
        targeted to individual items/cells.
        """
        all_quotes = []

        # Get individual values to quote
        quotable_values = self._get_quotable_values_from_answer(answer, question)

        for qv in quotable_values:
            value = qv["value"]
            target = qv["target"]

            # Analyze if this value was actually found (not "Not specified", etc.)
            answer_quality = self._analyze_answer_quality(value)

            if answer_quality == AnswerQuality.FOUND:
                # Get quotes for this specific value
                quotes = self._extract_precise_quotes(
                    value,
                    relevant_chunks,
                    f"Find evidence for: {value}",
                    bbox_data
                )

                # Add target info to each quote
                for quote in quotes:
                    quote["target"] = target
                    all_quotes.append(quote)

        return all_quotes

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
        
        return f"""You are a document quote extraction system. Your task is to find EXACT text from the source document that supports the given answer.

QUESTION: {question}

ANSWER TO SUPPORT: {answer}

DOCUMENT CHUNKS:
{chunks_section}

EXTRACTION RULES:
1. VERBATIM ONLY - Copy text exactly as it appears in the document, character-for-character
2. COMPLETE QUOTES - Extract enough text to provide meaningful evidence (typically a full sentence or clause)
3. SELF-CONTAINED - The quote should make sense on its own without needing the surrounding text
4. DIRECTLY RELEVANT - Only extract text that directly supports or contains the answer
5. NO FABRICATION - Never invent, paraphrase, or modify the source text

GUIDELINES:
- Prefer complete sentences over fragments when they provide better context
- If the answer is a name/number/date, include the surrounding phrase that gives it meaning
- Maximum {MAX_QUOTE_LENGTH} characters per quote
- Return up to {VECTOR_SEARCH_MAX_SOURCE_QUOTES} quotes, prioritized by relevance

RESPONSE FORMAT (JSON array):
[
  {{
    "chunk_number": 1,
    "exact_text": "The complete verbatim quote from the document",
    "page_context": "PAGE X"
  }}
]

EXAMPLE:
Answer: "December 31, 2024"
Document text: "The fiscal year ended December 31, 2024. Total revenue was $5.2M."
Response:
[
  {{
    "chunk_number": 1,
    "exact_text": "The fiscal year ended December 31, 2024.",
    "page_context": "PAGE 12"
  }}
]

Return EMPTY ARRAY [] if no exact supporting text exists. Never approximate or fabricate quotes."""

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

                # Trim exact_text to maximum length if needed
                full_quote_text = exact_text
                if len(full_quote_text) > MAX_QUOTE_LENGTH:
                    full_quote_text = full_quote_text[:MAX_QUOTE_LENGTH] + "..."

                # Create precise quote with exact positioning
                precise_quote = {
                    "chunk_id": chunk["chunk_id"],
                    "document_id": document_id,
                    "text": full_quote_text.strip(),
                    "exact_text": exact_text,  # The exact string for highlighting
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
    
    def _enhance_quotes_with_bboxes(self, quotes: List[Dict], bbox_data: Dict) -> List[Dict]:
        """
        Enhance quotes with bounding box word spans for precise highlighting
        
        Args:
            quotes: List of quote dictionaries from LLM extraction
            bbox_data: Dictionary mapping document_ids to their DocumentBoundingBoxes data
            
        Returns:
            Enhanced quotes with word_spans added where bbox matching succeeds
        """
        
        if not bbox_data:
            logger.info("No bbox data provided for quote enhancement")
            return quotes
        
        bbox_matcher = BBoxMatcher()
        enhanced_quotes = []
        
        for quote in quotes:
            enhanced_quote = quote.copy()
            
            document_id = quote.get("document_id")
            exact_text = quote.get("exact_text", "")
            precise_page = quote.get("precise_page")
            
            # Check if this document has bbox data
            if document_id and document_id in bbox_data:
                document_bboxes = bbox_data[document_id]
                
                try:
                    # Use bbox matcher to find word spans for this quote
                    word_spans = bbox_matcher.match_quote_to_words(
                        quote_text=exact_text,
                        document_bboxes=document_bboxes,
                        page_number=precise_page  # Use precise page if available
                    )

                    if word_spans:
                        # Add bbox information to quote
                        enhanced_quote["has_bounding_boxes"] = True
                        enhanced_quote["word_spans"] = word_spans
                        logger.info(f"✓ Matched quote to {len(word_spans)} word spans with bboxes: '{exact_text[:50]}...'")
                    else:
                        # No bbox match found
                        enhanced_quote["has_bounding_boxes"] = False
                        logger.info(f"✗ No bbox match for quote: '{exact_text[:30]}...'")
                        
                except Exception as e:
                    logger.warning(f"Failed to match quote to bboxes: {e}")
                    enhanced_quote["has_bounding_boxes"] = False
            else:
                # No bbox data for this document
                enhanced_quote["has_bounding_boxes"] = False
            
            enhanced_quotes.append(enhanced_quote)
        
        # Log summary
        bbox_matched = sum(1 for q in enhanced_quotes if q.get("has_bounding_boxes"))
        logger.info(f"📦 BBox Enhancement: {bbox_matched}/{len(quotes)} quotes matched to bounding boxes")
        
        return enhanced_quotes
    
    def _extract_precise_quotes(self, answer: str, relevant_chunks: List[Dict], question_prompt: str, 
                               bbox_data: Optional[Dict] = None) -> List[Dict]:
        """
        Use LLM to identify specific text portions that support the answer, with optional bbox matching
        
        Args:
            answer: The extracted answer from the LLM
            relevant_chunks: List of relevant document chunks
            question_prompt: The original question prompt
            bbox_data: Optional dictionary mapping document_ids to their bounding box data
            
        Returns:
            List of precise quote dictionaries with supporting text and optional word spans
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
            
            # Enhance quotes with bounding box word spans if available
            if bbox_data:
                precise_quotes = self._enhance_quotes_with_bboxes(precise_quotes, bbox_data)
            
            logger.info(f"Successfully extracted {len(precise_quotes)} precise quotes for answer: {answer[:50]}...")
            return precise_quotes

        except Exception as e:
            logger.error(f"Failed to extract precise quotes: {e}")
            # Return empty list on failure - don't break the main processing
            return []

    def _extract_precise_quotes_batch(self, questions_needing_quotes: List[Dict[str, Any]],
                                      bbox_data: Optional[Dict] = None) -> Dict[str, List[Dict]]:
        """
        Extract quotes for multiple questions using PARALLEL individual LLM calls.

        This approach sends all requests simultaneously but as separate API calls,
        giving each extraction focused context (better quality) while maintaining
        low latency through parallelism (total time ≈ slowest single call).

        Args:
            questions_needing_quotes: List of dicts with:
                - placeholder: Question placeholder ID
                - answer: The answer text to find quotes for
                - question_prompt: Original question prompt
                - relevant_chunks: List of relevant document chunks
                - answer_type: "string" or "structured"
                - target: Target info for structured answers (row/column)
            bbox_data: Optional dictionary mapping document_ids to their bounding box data

        Returns:
            Dictionary mapping placeholder -> list of quote dictionaries
        """

        if not questions_needing_quotes:
            return {}

        # Run parallel extraction using ThreadPoolExecutor
        # This works reliably whether called from sync or async context
        try:
            with time_operation("llm_parallel_quote_extraction",
                              {"question_count": len(questions_needing_quotes)}) as timer:
                results = self._extract_quotes_parallel_threaded(questions_needing_quotes, bbox_data)
                total_time = timer.stop().duration

            total_quotes = sum(len(quotes) for quotes in results.values())
            logger.info(f"⏱️ Parallel quote extraction: {total_time*1000:.0f}ms for {len(questions_needing_quotes)} items, {total_quotes} quotes extracted")

            return results

        except Exception as e:
            logger.error(f"Failed to extract quotes in parallel: {e}")
            return {q["placeholder"]: [] for q in questions_needing_quotes}

    def _extract_quotes_parallel_threaded(self, questions_needing_quotes: List[Dict[str, Any]],
                                          bbox_data: Optional[Dict] = None) -> Dict[str, List[Dict]]:
        """
        Execute quote extractions in parallel using the generic parallel executor.

        Args:
            questions_needing_quotes: List of question dicts needing quote extraction
            bbox_data: Optional bbox data for enhancement

        Returns:
            Dictionary mapping placeholder -> list of quote dictionaries
        """
        # Create worker closure that captures bbox_data and handles target embedding
        def extract_single(q_item: Dict[str, Any]) -> Tuple[str, List[Dict]]:
            """Extract quotes for a single question, embedding target info."""
            placeholder = q_item["placeholder"]
            target = q_item.get("target")

            # Build unique ID for logging
            question_id = placeholder
            if target:
                if target.get("type") == "list":
                    question_id = f"{placeholder}__list_{target['index']}"
                elif target.get("type") == "table":
                    question_id = f"{placeholder}__table_{target['row']}_{target['key']}"

            try:
                quotes = self._extract_single_quote_sync(q_item, bbox_data)
                # Embed target info into quotes before returning
                if target:
                    for quote in quotes:
                        quote["target"] = target
                return (placeholder, quotes)
            except Exception as e:
                logger.warning(f"Quote extraction failed for {question_id}: {e}")
                return (placeholder, [])

        def get_placeholder(q_item: Dict[str, Any]) -> str:
            return q_item["placeholder"]

        return self._execute_parallel(
            items=questions_needing_quotes,
            worker_fn=extract_single,
            key_fn=get_placeholder,
            max_workers=MAX_CONCURRENT_QUOTE_EXTRACTIONS,
            aggregate_lists=True,
            error_result_fn=None  # Errors handled in worker, returns empty list
        )

    def _extract_single_quote_sync(self, q_item: Dict[str, Any],
                                   bbox_data: Optional[Dict] = None) -> List[Dict]:
        """
        Extract quotes for a single question/answer pair synchronously.

        Args:
            q_item: Dict with placeholder, answer, question_prompt, relevant_chunks
            bbox_data: Optional bbox data for enhancement

        Returns:
            List of quote dictionaries for this item
        """
        answer = q_item["answer"]
        question_prompt = q_item["question_prompt"]
        relevant_chunks = q_item["relevant_chunks"]

        if not relevant_chunks:
            return []

        # Create focused prompt for this single extraction
        prompt = self._create_single_quote_extraction_prompt(answer, relevant_chunks, question_prompt)

        # Configure for quote extraction
        generation_config = self.genai.types.GenerationConfig(
            temperature=0.0,
            response_mime_type="application/json"
        )

        # Make synchronous API call
        response = self.model.generate_content(prompt, generation_config=generation_config)

        if not response or not response.text:
            return []

        # Parse response and enhance with bbox data
        quotes = self._parse_single_quote_response(response.text, relevant_chunks, bbox_data)
        return quotes

    def _create_single_quote_extraction_prompt(self, answer: str, chunks: List[Dict], question: str) -> str:
        """
        Create a focused prompt for extracting quotes for a SINGLE answer.

        This is simpler than the batch prompt, allowing the LLM to focus entirely
        on finding the best quotes for one specific answer.
        """
        # Prepare chunks with clear numbering
        chunks_section = ""
        for i, chunk in enumerate(chunks, 1):
            metadata = chunk.get("metadata", {})
            page_info = f"Pages {metadata.get('start_page', 'N/A')}-{metadata.get('end_page', 'N/A')}"
            filename = metadata.get('filename', 'Document')

            # Extract page markers
            page_markers = []
            lines = chunk['text'].split('\n')
            for line in lines:
                if '--- PAGE' in line and '---' in line:
                    page_markers.append(line.strip())

            page_info_detailed = page_info
            if page_markers:
                page_info_detailed += f" (Contains: {', '.join(page_markers[:3])})"

            chunks_section += f"""
=== CHUNK {i} ===
Source: {filename} ({page_info_detailed})
Text: {chunk['text']}

"""

        return f"""You are a document quote extraction system. Find EXACT text from the source that supports the given answer.

QUESTION: {question}

ANSWER TO SUPPORT: {answer}

DOCUMENT CHUNKS:
{chunks_section}

EXTRACTION RULES:
1. VERBATIM ONLY - Copy text exactly as it appears, character-for-character
2. COMPLETE QUOTES - Extract enough text to provide meaningful evidence (typically a full sentence)
3. SELF-CONTAINED - The quote should make sense on its own
4. DIRECTLY RELEVANT - Only extract text that directly supports the answer
5. NO FABRICATION - Never invent or paraphrase

GUIDELINES:
- Prefer complete sentences over fragments
- If the answer is a name/number/date, include surrounding context
- Maximum {MAX_QUOTE_LENGTH} characters per quote
- Return up to {VECTOR_SEARCH_MAX_SOURCE_QUOTES} quotes maximum
- Prioritize relevance and quality of quotes over quantity
- For simple one-word answers, a single quote is often best

RESPONSE FORMAT (JSON array):
[
  {{
    "chunk_number": 1,
    "exact_text": "The complete verbatim quote from the document",
    "page_context": "PAGE X"
  }}
]

Return EMPTY ARRAY [] if no exact supporting text exists."""

    def _parse_single_quote_response(self, response_text: str, chunks: List[Dict],
                                     bbox_data: Optional[Dict] = None) -> List[Dict]:
        """
        Parse the response from a single quote extraction call.

        Args:
            response_text: JSON response from LLM
            chunks: The relevant chunks for this extraction
            bbox_data: Optional bbox data for enhancement

        Returns:
            List of processed quote dictionaries
        """
        try:
            quote_data = json.loads(response_text)

            if not isinstance(quote_data, list):
                return []

            quotes = []
            for quote_item in quote_data:
                if not isinstance(quote_item, dict):
                    continue

                chunk_number = quote_item.get("chunk_number", 0)
                exact_text = quote_item.get("exact_text", "")
                page_context = quote_item.get("page_context", "")

                # Validate chunk number
                if chunk_number < 1 or chunk_number > len(chunks):
                    continue

                chunk = chunks[chunk_number - 1]
                metadata = chunk.get("metadata", {})

                document_id = metadata.get("document_id", "")
                if not document_id:
                    continue

                # Extract precise page number
                precise_page = self._extract_precise_page_number(
                    exact_text, chunk['text'], page_context, metadata
                )

                # Trim to max length
                full_quote_text = exact_text
                if len(full_quote_text) > MAX_QUOTE_LENGTH:
                    full_quote_text = full_quote_text[:MAX_QUOTE_LENGTH] + "..."

                quote_dict = {
                    "chunk_id": chunk["chunk_id"],
                    "document_id": document_id,
                    "text": full_quote_text.strip(),
                    "exact_text": exact_text,
                    "page_range": str(precise_page) if precise_page else f"{metadata.get('start_page', 'N/A')}-{metadata.get('end_page', 'N/A')}",
                    "precise_page": precise_page,
                    "page_context": page_context,
                    "relevance_score": chunk.get("distance", 0.0),
                }

                # Enhance with bbox data if available
                if bbox_data and document_id in bbox_data:
                    try:
                        bbox_matcher = BBoxMatcher()
                        word_spans = bbox_matcher.match_quote_to_words(
                            quote_text=exact_text,
                            document_bboxes=bbox_data[document_id],
                            page_number=precise_page
                        )
                        if word_spans:
                            quote_dict["has_bounding_boxes"] = True
                            quote_dict["word_spans"] = word_spans
                        else:
                            quote_dict["has_bounding_boxes"] = False
                    except Exception as e:
                        logger.warning(f"Failed to match bbox: {e}")
                        quote_dict["has_bounding_boxes"] = False
                else:
                    quote_dict["has_bounding_boxes"] = False

                quotes.append(quote_dict)

            return quotes

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse single quote response: {e}")
            return []
        except Exception as e:
            logger.warning(f"Error processing single quote response: {e}")
            return []

    def _create_batch_quote_extraction_prompt(self, questions_needing_quotes: List[Dict[str, Any]]) -> str:
        """
        Create a single prompt for extracting quotes for ALL questions at once.

        Args:
            questions_needing_quotes: List of question dicts needing quote extraction

        Returns:
            Formatted batch prompt string
        """

        # Build sections for each question
        questions_section = ""

        # We need to track chunk mappings per question since chunks can overlap
        for idx, q_item in enumerate(questions_needing_quotes, 1):
            placeholder = q_item["placeholder"]
            answer = q_item["answer"]
            question_prompt = q_item["question_prompt"]
            relevant_chunks = q_item["relevant_chunks"]
            target = q_item.get("target")

            # Build chunk context for this question
            chunks_text = ""
            for chunk_idx, chunk in enumerate(relevant_chunks, 1):
                metadata = chunk.get("metadata", {})
                page_info = f"Pages {metadata.get('start_page', 'N/A')}-{metadata.get('end_page', 'N/A')}"
                filename = metadata.get('filename', 'Document')

                # Extract page markers from chunk text
                page_markers = []
                lines = chunk['text'].split('\n')
                for line in lines:
                    if '--- PAGE' in line and '---' in line:
                        page_markers.append(line.strip())

                page_info_detailed = page_info
                if page_markers:
                    page_info_detailed += f" (Contains: {', '.join(page_markers[:3])})"

                chunks_text += f"  [CHUNK {chunk_idx}] Source: {filename} ({page_info_detailed})\n  Text: {chunk['text'][:1500]}{'...' if len(chunk['text']) > 1500 else ''}\n\n"

            # Build question identifier (include target for structured answers)
            question_id = placeholder
            if target:
                if target.get("type") == "list":
                    question_id = f"{placeholder}__list_{target['index']}"
                elif target.get("type") == "table":
                    question_id = f"{placeholder}__table_{target['row']}_{target['key']}"

            questions_section += f"""
=== ITEM {idx} (item_id: {question_id}) ===
QUESTION: {question_prompt}
ANSWER TO SUPPORT: {answer}

DOCUMENT CHUNKS FOR THIS ITEM:
{chunks_text}
"""

        return f"""You are a document quote extraction system. Extract EXACT text from source documents that supports each answer.

EXTRACTION RULES:
1. VERBATIM ONLY - Copy text exactly as it appears, character-for-character
2. COMPLETE QUOTES - Extract enough text to provide meaningful evidence (typically a full sentence or clause)
3. SELF-CONTAINED - Each quote should make sense on its own
4. DIRECTLY RELEVANT - Only extract text that directly supports or contains the answer
5. NO FABRICATION - Never invent, paraphrase, or modify source text
6. NO ITEM_ID MODIFICATION - Use the provided item_id exactly as given

GUIDELINES:
- Prefer complete sentences over fragments when they provide better context
- If the answer is a name/number/date, include the surrounding phrase that gives it meaning
- Maximum {MAX_QUOTE_LENGTH} characters per quote
- Up to {VECTOR_SEARCH_MAX_SOURCE_QUOTES} quotes per item_id this is a HARD LIMIT - return fewer if necessary
- Use EMPTY ARRAY [] when no supporting text exists
- Make sure page_context is always formatter as "PAGE X" with a single page number X
- If you are finding quotes for one word answers then a single quote is perfectly acceptable
- the fewest powerful number of quotes possible is preferred

Here are all the questions and their document chunks needing quotes:
{questions_section}

RESPONSE FORMAT (JSON object with item IDs as keys):
{{
  "<item_id>": [
    {{
      "chunk_number": 1,
      "exact_text": "The complete verbatim quote from the document",
      "page_context": "PAGE X"
    }}
  ],
}}

Return valid JSON only."""

    def _parse_batch_quote_extraction_response(self, response_text: str,
                                               questions_needing_quotes: List[Dict[str, Any]],
                                               bbox_data: Optional[Dict] = None) -> Dict[str, List[Dict]]:
        """
        Parse the batch quote extraction response and map quotes back to placeholders.

        Args:
            response_text: JSON response from LLM
            questions_needing_quotes: Original list of questions for chunk mapping
            bbox_data: Optional bbox data for enhancement

        Returns:
            Dictionary mapping placeholder -> list of processed quote dictionaries
        """

        try:
            batch_data = json.loads(response_text)

            if not isinstance(batch_data, dict):
                logger.warning("Batch quote response is not a dict, returning empty quotes")
                return {q["placeholder"]: [] for q in questions_needing_quotes}

            # Build a mapping from question_id to question data for chunk lookup
            id_to_question = {}
            for q_item in questions_needing_quotes:
                placeholder = q_item["placeholder"]
                target = q_item.get("target")

                # Build the same ID used in the prompt
                question_id = placeholder
                if target:
                    if target.get("type") == "list":
                        question_id = f"{placeholder}__list_{target['index']}"
                    elif target.get("type") == "table":
                        question_id = f"{placeholder}__table_{target['row']}_{target['key']}"

                id_to_question[question_id] = q_item

            # Process each item in the response
            result = {}

            for question_id, quotes_data in batch_data.items():
                if question_id not in id_to_question:
                    logger.warning(f"Unknown question_id in batch response: {question_id}")
                    continue

                q_item = id_to_question[question_id]
                placeholder = q_item["placeholder"]
                relevant_chunks = q_item["relevant_chunks"]
                target = q_item.get("target")

                # Initialize placeholder in result if not present
                if placeholder not in result:
                    result[placeholder] = []

                if not isinstance(quotes_data, list):
                    continue

                # Process each quote for this item
                for quote_item in quotes_data:
                    if not isinstance(quote_item, dict):
                        continue

                    chunk_number = quote_item.get("chunk_number", 0)
                    exact_text = quote_item.get("exact_text", "")
                    page_context = quote_item.get("page_context", "")

                    # Validate chunk number
                    if chunk_number < 1 or chunk_number > len(relevant_chunks):
                        logger.warning(f"Invalid chunk number {chunk_number} for {question_id}")
                        continue

                    chunk = relevant_chunks[chunk_number - 1]
                    metadata = chunk.get("metadata", {})

                    document_id = metadata.get("document_id", "")
                    if not document_id:
                        logger.warning(f"Chunk missing document_id, skipping quote")
                        continue

                    # Extract precise page number
                    precise_page = self._extract_precise_page_number(
                        exact_text, chunk['text'], page_context, metadata
                    )

                    # Trim exact_text to maximum length if needed
                    full_quote_text = exact_text
                    if len(full_quote_text) > MAX_QUOTE_LENGTH:
                        full_quote_text = full_quote_text[:MAX_QUOTE_LENGTH] + "..."

                    # Build quote dict
                    quote_dict = {
                        "chunk_id": chunk["chunk_id"],
                        "document_id": document_id,
                        "text": full_quote_text.strip(),
                        "exact_text": exact_text,
                        "page_range": str(precise_page) if precise_page else f"{metadata.get('start_page', 'N/A')}-{metadata.get('end_page', 'N/A')}",
                        "precise_page": precise_page,
                        "page_context": page_context,
                        "relevance_score": chunk.get("distance", 0.0),
                    }

                    # Add target info for structured answers
                    if target:
                        quote_dict["target"] = target

                    # Enhance with bbox data if available
                    if bbox_data and document_id in bbox_data:
                        try:
                            bbox_matcher = BBoxMatcher()
                            word_spans = bbox_matcher.match_quote_to_words(
                                quote_text=exact_text,
                                document_bboxes=bbox_data[document_id],
                                page_number=precise_page
                            )
                            if word_spans:
                                quote_dict["has_bounding_boxes"] = True
                                quote_dict["word_spans"] = word_spans
                            else:
                                quote_dict["has_bounding_boxes"] = False
                        except Exception as e:
                            logger.warning(f"Failed to match bbox for quote: {e}")
                            quote_dict["has_bounding_boxes"] = False
                    else:
                        quote_dict["has_bounding_boxes"] = False

                    result[placeholder].append(quote_dict)

            # Ensure all placeholders have entries (even if empty)
            for q_item in questions_needing_quotes:
                placeholder = q_item["placeholder"]
                if placeholder not in result:
                    result[placeholder] = []

            # Log summary
            total_quotes = sum(len(quotes) for quotes in result.values())
            logger.info(f"📝 Parsed batch quotes: {total_quotes} quotes for {len(result)} placeholders")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse batch quote JSON: {e}")
            logger.error(f"Raw response: {response_text}...")
            return {q["placeholder"]: [] for q in questions_needing_quotes}
        except Exception as e:
            logger.error(f"Error processing batch quote response: {e}")
            return {q["placeholder"]: [] for q in questions_needing_quotes}

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
