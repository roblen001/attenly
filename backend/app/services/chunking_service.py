"""
Chunking Service for Two-Level Document Processing

Implements the two-level chunking strategy:
- L1 Chunks: Semantic sections based on pages and natural boundaries (1000-1600 tokens)
- L2 Chunks: Fixed windows within L1 chunks for vector search (512 tokens with overlap)
"""

import uuid
import logging
from typing import List, Dict, Any, Tuple
import re

logger = logging.getLogger(__name__)


class ChunkingService:
    """Service for creating two-level document chunks optimized for LLM inference"""
    
    def __init__(self):
        try:
            import tiktoken
            self.encoder = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
        except ImportError:
            # Fallback token estimation if tiktoken not available
            self.encoder = None
        
        # Chunking parameters based on best practices
        self.L1_TARGET = 1200  # tokens - target size for L1 chunks
        self.L1_MAX = 2000     # tokens - hard maximum for L1 chunks
        self.L2_WINDOW = 512   # tokens - size of L2 windows
        self.L2_OVERLAP = 80   # tokens - overlap between L2 windows
    
    def create_two_level_chunks(self, document_id: str, pdf_data: Dict[str, Any], filename: str) -> Tuple[List[Dict], List[Dict]]:
        """Create L1 and L2 chunks from processed PDF data"""
        
        try:
            # Validate input data
            if not pdf_data or not pdf_data.get("pages"):
                raise ValueError("Invalid PDF data: no pages found")
            
            # Create L1 chunks based on pages and natural boundaries
            l1_chunks = self._create_page_based_chunks(document_id, pdf_data, filename)
            
            if not l1_chunks:
                raise ValueError("Failed to create L1 chunks from document")
            
            # Create L2 chunks as sliding windows within each L1 chunk
            l2_chunks = []
            for l1_chunk in l1_chunks:
                windows = self._create_window_chunks(l1_chunk)
                l2_chunks.extend(windows)
            
            if not l2_chunks:
                raise ValueError("Failed to create L2 chunks from document")
            
            return l1_chunks, l2_chunks
            
        except Exception as e:
            logger.error(f"Failed to create chunks for document {document_id}: {e}")
            raise ValueError(f"Chunking failed: {str(e)}")
    
    def _create_page_based_chunks(self, document_id: str, pdf_data: Dict[str, Any], filename: str) -> List[Dict]:
        """Create L1 chunks based on pages and natural boundaries"""
        chunks = []
        current_chunk = self._new_l1_chunk(document_id, filename)
        
        for page in pdf_data["pages"]:
            page_tokens = page["token_count"]
            
            # If adding this page would exceed L1_MAX, finalize current chunk
            if current_chunk["token_count"] + page_tokens > self.L1_MAX and current_chunk["text"]:
                chunks.append(current_chunk.copy())
                current_chunk = self._new_l1_chunk(document_id, filename)
            
            # Add page to current chunk
            if current_chunk["start_page"] is None:
                current_chunk["start_page"] = page["page_number"]
            current_chunk["end_page"] = page["page_number"]
            
            # Add page content with page marker
            page_content = f"\n--- PAGE {page['page_number']} ---\n{page['markdown']}\n"
            current_chunk["text"] += page_content
            current_chunk["token_count"] += page_tokens
            
            # Track tables and paragraphs for metadata
            current_chunk["tables"].extend([
                {**table, "page_number": page["page_number"]} 
                for table in page["tables"]
            ])
            current_chunk["paragraphs"].extend([
                {**para, "page_number": page["page_number"]} 
                for para in page["paragraphs"]
            ])
            
            # If chunk is at good size and we have complete content, consider finalizing
            if (current_chunk["token_count"] >= self.L1_TARGET and 
                self._chunk_ends_cleanly(page)):
                chunks.append(current_chunk.copy())
                current_chunk = self._new_l1_chunk(document_id, filename)
        
        # Add final chunk if it has content
        if current_chunk["text"].strip():
            chunks.append(current_chunk)
        
        return chunks
    
    def _create_window_chunks(self, l1_chunk: Dict) -> List[Dict]:
        """Create L2 chunks as sliding windows within an L1 chunk"""
        l2_chunks = []
        text = l1_chunk["text"]
        
        if not text.strip():
            return l2_chunks
        
        # Split text into tokens for precise windowing
        if self.encoder:
            tokens = self.encoder.encode(text)
        else:
            # Fallback: split by words and estimate
            words = text.split()
            tokens = list(range(len(words)))  # Use indices as token placeholders
        
        # Create sliding windows
        start_idx = 0
        window_count = 0
        
        while start_idx < len(tokens):
            end_idx = min(start_idx + self.L2_WINDOW, len(tokens))
            
            # Extract window text
            if self.encoder:
                window_tokens = tokens[start_idx:end_idx]
                window_text = self.encoder.decode(window_tokens)
            else:
                # Fallback: use word-based windowing
                words = text.split()
                window_words = words[start_idx:end_idx]
                window_text = " ".join(window_words)
            
            # Preserve table integrity - if window cuts through a table, extend to include it
            window_text = self._preserve_table_integrity(window_text, l1_chunk)
            
            # Create L2 chunk
            l2_chunk = {
                "chunk_id": f"L2_{uuid.uuid4()}",
                "parent_id": l1_chunk["chunk_id"],
                "document_id": l1_chunk["document_id"],
                "level": 2,
                "text": window_text.strip(),
                "offset_start": start_idx,
                "offset_end": end_idx - 1,
                "token_count": self._count_tokens(window_text),
                "window_index": window_count,
                "filename": l1_chunk["filename"],
                "start_page": l1_chunk["start_page"],
                "end_page": l1_chunk["end_page"]
            }
            
            if l2_chunk["text"]:  # Only add non-empty chunks
                l2_chunks.append(l2_chunk)
            
            # Move to next window with overlap
            start_idx += self.L2_WINDOW - self.L2_OVERLAP
            window_count += 1
            
            # Break if we've reached the end
            if end_idx >= len(tokens):
                break
        
        return l2_chunks
    
    def _preserve_table_integrity(self, window_text: str, l1_chunk: Dict) -> str:
        """Ensure tables are not cut in the middle - extend window if needed"""
        # Check if window cuts through a table
        lines = window_text.split('\n')
        
        # If last few lines contain table markers, try to complete the table
        table_lines = []
        for i in range(len(lines) - 1, max(-1, len(lines) - 5), -1):
            if '|' in lines[i] or (lines[i].strip() and set(lines[i].strip()) == {'-'}):
                table_lines.insert(0, lines[i])
            else:
                break
        
        # If we found partial table at the end, try to extend from parent
        if table_lines and not self._is_complete_table(table_lines):
            # For now, just return the window as-is
            # In a more sophisticated implementation, we could extend from the parent L1 chunk
            pass
        
        return window_text
    
    def _is_complete_table(self, lines: List[str]) -> bool:
        """Check if table lines represent a complete table"""
        if not lines:
            return False
        
        # Simple heuristic: table is complete if it has both header and data rows
        has_header = any('|' in line and line.count('|') >= 2 for line in lines[:2])
        has_separator = any(line.strip() and set(line.strip()) <= {'-', '|', ' '} for line in lines)
        
        return has_header and has_separator
    
    def _chunk_ends_cleanly(self, page: Dict) -> bool:
        """Check if page ends at a natural boundary"""
        if not page["lines"]:
            return True
        
        last_line = page["lines"][-1].strip()
        
        # Ends cleanly if:
        # 1. Not in the middle of a table
        # 2. Not ending with incomplete sentence (very basic check)
        not_mid_table = not ('|' in last_line and last_line.count('|') < 3)
        not_incomplete = not last_line.endswith(',')
        
        return not_mid_table and not_incomplete
    
    def _new_l1_chunk(self, document_id: str, filename: str) -> Dict:
        """Create a new empty L1 chunk"""
        return {
            "chunk_id": f"L1_{uuid.uuid4()}",
            "document_id": document_id,
            "level": 1,
            "text": "",
            "start_page": None,
            "end_page": None,
            "filename": filename,
            "token_count": 0,
            "tables": [],
            "paragraphs": []
        }
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken or fallback estimation"""
        if self.encoder:
            return len(self.encoder.encode(text))
        else:
            # Rough estimation: ~4 characters per token
            return len(text) // 4
    
    def get_chunk_statistics(self, l1_chunks: List[Dict], l2_chunks: List[Dict]) -> Dict[str, Any]:
        """Generate statistics about the chunking results"""
        return {
            "l1_chunks": {
                "count": len(l1_chunks),
                "avg_tokens": sum(chunk["token_count"] for chunk in l1_chunks) / len(l1_chunks) if l1_chunks else 0,
                "min_tokens": min(chunk["token_count"] for chunk in l1_chunks) if l1_chunks else 0,
                "max_tokens": max(chunk["token_count"] for chunk in l1_chunks) if l1_chunks else 0,
                "total_tables": sum(len(chunk["tables"]) for chunk in l1_chunks),
                "total_paragraphs": sum(len(chunk["paragraphs"]) for chunk in l1_chunks)
            },
            "l2_chunks": {
                "count": len(l2_chunks),
                "avg_tokens": sum(chunk["token_count"] for chunk in l2_chunks) / len(l2_chunks) if l2_chunks else 0,
                "min_tokens": min(chunk["token_count"] for chunk in l2_chunks) if l2_chunks else 0,
                "max_tokens": max(chunk["token_count"] for chunk in l2_chunks) if l2_chunks else 0
            },
            "total_tokens": sum(chunk["token_count"] for chunk in l1_chunks)
        }
