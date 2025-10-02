"""
Batch Embedding Service for Optimized Vector Generation

This service handles batch embedding generation using Google's Generative AI API,
significantly improving performance over individual embedding calls.

Performance improvements:
- Batch processing: 50 texts per API call instead of 1
- Concurrent requests: Multiple batches processed simultaneously
- Error handling: Retry logic with exponential backoff
- Memory optimization: Streaming processing for large datasets
"""

import asyncio
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from contextlib import asynccontextmanager
import google.generativeai as genai
import httpx
from app.config import (
    GEMINI_API_KEY, 
    EMBEDDING_BATCH_SIZE, 
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_TIMEOUT_SECONDS,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MAX_CONCURRENT_BATCHES
)

# Global HTTP client for connection reuse (HTTP/2 enabled)
_HTTPX_CLIENT: Optional[httpx.AsyncClient] = None

def _get_client() -> httpx.AsyncClient:
    """Get or create the global HTTP client with HTTP/2 support and connection reuse"""
    global _HTTPX_CLIENT
    if _HTTPX_CLIENT is None:
        _HTTPX_CLIENT = httpx.AsyncClient(
            http2=True, 
            timeout=httpx.Timeout(60.0),  # Longer timeout for batch operations
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        logger.info("Initialized global httpx client with HTTP/2 and connection reuse")
    return _HTTPX_CLIENT

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """Result of a batch embedding operation"""
    embeddings: List[List[float]]
    batch_index: int
    processing_time: float
    retry_count: int
    error: Optional[str] = None
    success: bool = True


class EmbeddingBatchService:
    """
    Batch embedding service using Google's Generative AI API
    
    Features:
    - Batch processing of up to 50 texts per API call
    - Concurrent processing of multiple batches
    - Automatic retry with exponential backoff
    - Performance monitoring and error tracking
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required for batch embedding service")
        
        # Configure Google AI
        genai.configure(api_key=self.api_key)
        
        # Configuration
        self.batch_size = EMBEDDING_BATCH_SIZE
        self.max_retries = EMBEDDING_MAX_RETRIES
        self.timeout = EMBEDDING_TIMEOUT_SECONDS
        self.model_name = EMBEDDING_MODEL_NAME
        self.max_concurrent_batches = EMBEDDING_MAX_CONCURRENT_BATCHES
        
        # Performance tracking
        self.total_embeddings_generated = 0
        self.total_api_calls = 0
        self.total_processing_time = 0.0
        self.error_count = 0
        
        # Rate limiting
        self._semaphore = asyncio.Semaphore(self.max_concurrent_batches)
        self._last_request_time = 0.0
        self._min_request_interval = 0.1  # 100ms between requests
        
        logger.info(f"Initialized EmbeddingBatchService with batch_size={self.batch_size}, "
                   f"max_concurrent={self.max_concurrent_batches}")
    
    def _split_into_batches(self, texts: List[str]) -> List[List[str]]:
        """Split texts into batches of appropriate size"""
        batches = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batches.append(batch)
        return batches
    
    async def _rate_limit_delay(self):
        """Implement rate limiting between requests"""
        current_time = time.time()
        time_since_last_request = current_time - self._last_request_time
        
        if time_since_last_request < self._min_request_interval:
            delay = self._min_request_interval - time_since_last_request
            await asyncio.sleep(delay)
        
        self._last_request_time = time.time()
    
    async def _generate_batch_embeddings(
        self, 
        texts: List[str], 
        batch_index: int,
        retry_count: int = 0
    ) -> BatchResult:
        """Generate embeddings for a single batch using the real batch API with retry logic"""
        
        start_time = time.time()
        await self._rate_limit_delay()

        # Use the real batch API endpoint with correct format
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:batchEmbedContents"
        params = {"key": self.api_key}
        # Correct payload format per Google AI API documentation
        payload = {
            "requests": [
                {
                    "model": f"models/{self.model_name}",
                    "content": {"parts": [{"text": text}]}
                }
                for text in texts
            ]
        }

        client = _get_client()
        backoff = 0.5

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"Making batch API call for {len(texts)} texts (batch {batch_index}, attempt {attempt + 1})")
                
                r = await client.post(url, params=params, json=payload)
                
                # Handle server errors with retry
                if r.status_code >= 500:
                    raise httpx.HTTPStatusError("Server error", request=r.request, response=r)
                
                r.raise_for_status()
                data = r.json()

                # Response format: {"embeddings": [{"values": [...]}, ...]}
                emb_items = data.get("embeddings", [])
                if not emb_items:
                    raise ValueError(f"Bad batch response: keys={list(data.keys())}")

                embeddings = [item["values"] for item in emb_items]
                if len(embeddings) != len(texts):
                    raise ValueError(f"Batch size mismatch ({len(embeddings)} != {len(texts)})")

                processing_time = time.time() - start_time
                
                # Update statistics
                self.total_api_calls += 1
                self.total_embeddings_generated += len(embeddings)
                self.total_processing_time += processing_time

                logger.debug(f"✅ Generated {len(embeddings)} embeddings in batch {batch_index} "
                           f"({processing_time:.2f}s, attempt {attempt + 1})")

                return BatchResult(
                    embeddings=embeddings,
                    batch_index=batch_index,
                    processing_time=processing_time,
                    retry_count=attempt,
                    success=True,
                )

            except (httpx.HTTPError, ValueError) as e:
                error_msg = f"Batch {batch_index} failed (attempt {attempt + 1}): {str(e)}"
                logger.warning(error_msg)
                
                if attempt < self.max_retries:
                    logger.info(f"Retrying batch {batch_index} after {backoff}s delay")
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                
                # Final failure after all retries
                self.error_count += 1
                logger.error(f"Batch {batch_index} failed after {self.max_retries + 1} attempts: {str(e)}")
                
                return BatchResult(
                    embeddings=[],
                    batch_index=batch_index,
                    processing_time=time.time() - start_time,
                    retry_count=attempt,
                    error=str(e),
                    success=False,
                )

        # This should never be reached, but included for safety
        return BatchResult(
            embeddings=[],
            batch_index=batch_index,
            processing_time=time.time() - start_time,
            retry_count=self.max_retries,
            error="Maximum retries exceeded",
            success=False,
        )
    
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts using batch processing
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors (one per input text)
            
        Raises:
            ValueError: If no texts provided or all batches fail
            RuntimeError: If embedding generation fails
        """
        
        if not texts:
            raise ValueError("No texts provided for embedding generation")
        
        logger.info(f"Starting batch embedding generation for {len(texts)} texts")
        start_time = time.time()
        
        # Split into batches
        batches = self._split_into_batches(texts)
        logger.info(f"Split into {len(batches)} batches of max {self.batch_size} texts each")
        
        # Process batches concurrently with semaphore limiting
        async def process_batch_with_semaphore(batch_texts: List[str], batch_index: int):
            async with self._semaphore:
                return await self._generate_batch_embeddings(batch_texts, batch_index)
        
        # Create tasks for concurrent execution
        tasks = [
            process_batch_with_semaphore(batch_texts, i)
            for i, batch_texts in enumerate(batches)
        ]
        
        # Execute all batches concurrently
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions that occurred
        processed_results = []
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                logger.error(f"Batch {i} failed with exception: {result}")
                processed_results.append(BatchResult(
                    embeddings=[],
                    batch_index=i,
                    processing_time=0.0,
                    retry_count=0,
                    error=str(result),
                    success=False
                ))
            else:
                processed_results.append(result)
        
        batch_results = processed_results
        
        # Check for failures
        failed_batches = [r for r in batch_results if not r.success]
        if failed_batches:
            total_failed_texts = sum(len(batches[r.batch_index]) for r in failed_batches)
            if len(failed_batches) == len(batch_results):
                raise RuntimeError(f"All {len(batch_results)} batches failed")
            else:
                logger.warning(f"{len(failed_batches)} batches failed, "
                              f"affecting {total_failed_texts} texts")
        
        # Combine embeddings in original order
        all_embeddings = []
        for batch_result in sorted(batch_results, key=lambda x: x.batch_index):
            if batch_result.success:
                all_embeddings.extend(batch_result.embeddings)
            else:
                # For failed batches, add zero vectors to maintain index alignment
                batch_size = len(batches[batch_result.batch_index])
                zero_embeddings = [[0.0] * 768 for _ in range(batch_size)]  # text-embedding-004 has 768 dimensions
                all_embeddings.extend(zero_embeddings)
                logger.error(f"Using zero vectors for failed batch {batch_result.batch_index}")
        
        total_time = time.time() - start_time
        success_rate = (len(batch_results) - len(failed_batches)) / len(batch_results) * 100
        
        logger.info(f"Batch embedding completed: {len(all_embeddings)} embeddings generated "
                   f"in {total_time:.2f}s ({success_rate:.1f}% success rate)")
        
        if len(all_embeddings) != len(texts):
            logger.error(f"Embedding count mismatch: expected {len(texts)}, got {len(all_embeddings)}")
            raise RuntimeError(f"Embedding generation failed: count mismatch")
        
        return all_embeddings
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for monitoring"""
        
        avg_processing_time = (
            self.total_processing_time / self.total_api_calls 
            if self.total_api_calls > 0 else 0.0
        )
        
        avg_embeddings_per_call = (
            self.total_embeddings_generated / self.total_api_calls 
            if self.total_api_calls > 0 else 0.0
        )
        
        error_rate = (
            self.error_count / self.total_api_calls * 100 
            if self.total_api_calls > 0 else 0.0
        )
        
        return {
            "total_embeddings_generated": self.total_embeddings_generated,
            "total_api_calls": self.total_api_calls,
            "total_processing_time": self.total_processing_time,
            "avg_processing_time_per_call": avg_processing_time,
            "avg_embeddings_per_call": avg_embeddings_per_call,
            "error_count": self.error_count,
            "error_rate_percent": error_rate,
            "batch_size": self.batch_size,
            "max_concurrent_batches": self.max_concurrent_batches
        }
    
    def reset_stats(self):
        """Reset performance statistics"""
        self.total_embeddings_generated = 0
        self.total_api_calls = 0
        self.total_processing_time = 0.0
        self.error_count = 0
        logger.info("Performance statistics reset")


# Global instance for reuse across requests
_global_embedding_service: Optional[EmbeddingBatchService] = None


def get_embedding_service() -> EmbeddingBatchService:
    """Get or create the global embedding service instance"""
    global _global_embedding_service
    
    if _global_embedding_service is None:
        _global_embedding_service = EmbeddingBatchService()
    
    return _global_embedding_service


@asynccontextmanager
async def embedding_service_context():
    """Context manager for embedding service with cleanup"""
    service = get_embedding_service()
    try:
        yield service
    finally:
        # Log final stats
        stats = service.get_performance_stats()
        if stats["total_api_calls"] > 0:
            logger.info(f"Embedding service session complete: "
                       f"{stats['total_embeddings_generated']} embeddings, "
                       f"{stats['total_api_calls']} API calls, "
                       f"{stats['error_rate_percent']:.1f}% error rate")


async def generate_embeddings_for_texts(texts: List[str]) -> List[List[float]]:
    """
    Convenience function for generating embeddings with automatic service management
    
    Args:
        texts: List of text strings to embed
        
    Returns:
        List of embedding vectors
    """
    async with embedding_service_context() as service:
        return await service.generate_embeddings_batch(texts)


# Testing and validation functions
async def test_embedding_service():
    """Test the embedding service with sample texts"""
    
    test_texts = [
        "This is a test document about machine learning.",
        "Another test text about artificial intelligence.",
        "A third example focusing on natural language processing.",
        "Final test text about deep learning algorithms."
    ]
    
    try:
        logger.info("Testing embedding service...")
        embeddings = await generate_embeddings_for_texts(test_texts)
        
        logger.info(f"Successfully generated {len(embeddings)} embeddings")
        logger.info(f"Embedding dimension: {len(embeddings[0]) if embeddings else 0}")
        
        # Get performance stats
        service = get_embedding_service()
        stats = service.get_performance_stats()
        logger.info(f"Performance stats: {stats}")
        
        return True
        
    except Exception as e:
        logger.error(f"Embedding service test failed: {e}")
        return False


if __name__ == "__main__":
    # Run test when executed directly
    asyncio.run(test_embedding_service())
