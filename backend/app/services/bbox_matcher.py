"""
Bounding Box Matcher Service

Deterministic word-span matching service for mapping quote text to word bounding boxes.
Provides exact multi-token scanning with fuzzy fallback for OCR quote highlighting.
"""

from typing import List, Dict, Any, Optional
import logging
import re

logger = logging.getLogger(__name__)


class BBoxMatcher:
    """
    Matches quote text to word spans with bounding boxes using deterministic matching.
    
    Strategy:
    1. Normalize quote text and document words (lowercase, strip punctuation)
    2. Exact multi-token scan for matches
    3. Fallback to fuzzy matching for OCR errors
    4. Return matched word spans with bounding boxes
    """
    
    def __init__(self, fuzzy_threshold: float = 0.85):
        """
        Initialize bbox matcher with fuzzy matching threshold.
        
        Args:
            fuzzy_threshold: Similarity threshold for fuzzy matching (0-1)
        """
        self.fuzzy_threshold = fuzzy_threshold
    
    def match_quote_to_words(
        self,
        quote_text: str,
        document_bboxes: Dict[str, Any],
        page_number: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Map quote text to word spans with bounding boxes.
        
        Args:
            quote_text: The quote text to match
            document_bboxes: Complete document bounding box data
            page_number: Optional page number hint to limit search
            
        Returns:
            List of word span dicts with text, bbox, and page info
        """
        if not quote_text or not document_bboxes:
            return []
        
        try:
            # Use consistent normalization pipeline
            quote_tokens = self._normalize_and_tokenize(quote_text)
            
            if not quote_tokens:
                return []
            
            # Get pages to search (all pages or specific page)
            pages_to_search = document_bboxes.get('pages', [])
            if page_number:
                pages_to_search = [
                    p for p in pages_to_search 
                    if p.get('page_number') == page_number
                ]
            
            # Try exact matching first
            word_spans = self._exact_match(quote_tokens, pages_to_search)
            
            # Fallback to fuzzy matching if exact match fails
            if not word_spans and len(quote_tokens) > 0:
                word_spans = self._fuzzy_match(quote_tokens, pages_to_search)
            
            return word_spans
            
        except Exception as e:
            logger.error(f"Failed to match quote to bboxes: {e}")
            return []
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for matching.
        
        - Lowercase
        - Strip punctuation (keep spaces)
        - Normalize whitespace
        - Handle common OCR errors (ligatures)
        
        Args:
            text: Text to normalize
            
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
        # Lowercase
        text = text.lower()
        
        # Handle common ligatures (OCR artifacts)
        ligature_map = {
            'ﬁ': 'fi',
            'ﬂ': 'fl',
            'ﬀ': 'ff',
            'ﬃ': 'ffi',
            'ﬄ': 'ffl',
            'ﬆ': 'st',
        }
        for ligature, replacement in ligature_map.items():
            text = text.replace(ligature, replacement)
        
        # Remove punctuation but keep spaces
        # Keep alphanumeric and spaces only
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Normalize whitespace (multiple spaces to single space)
        text = ' '.join(text.split())
        
        return text
    
    def _normalize_and_tokenize(self, text: str) -> List[str]:
        """
        Wrapper to ensure consistent normalization pipeline.
        raw text -> normalized string -> tokens
        
        Args:
            text: Text to normalize and tokenize
            
        Returns:
            List of normalized tokens
        """
        normalized = self._normalize_text(text)
        return normalized.split() if normalized else []
    
    def _build_doc_tokens(
        self,
        pages: List[Dict[str, Any]]
    ) -> tuple:
        """
        Build document tokens and mapping in a single pass.
        
        This ensures consistent tokenization between quote and document.
        Each word is normalized once, and tokens are mapped back to source words.
        
        Args:
            pages: Pages with word bounding boxes
            
        Returns:
            Tuple of (all_word_data, doc_tokens, token_to_word):
            - all_word_data: List of original word dicts with text, bbox, page, etc.
            - doc_tokens: Flattened list of normalized tokens for entire document
            - token_to_word: Maps each token index to its source word index
        """
        all_word_data = []
        doc_tokens = []
        token_to_word = []
        
        for page in pages:
            page_num = page.get('page_number', 1)
            for line in page.get('lines', []):
                for word_data in line.get('words', []):
                    word_idx = len(all_word_data)
                    
                    # Store original word data
                    all_word_data.append({
                        'text': word_data.get('text', ''),
                        'bbox': word_data.get('bbox', [0, 0, 0, 0]),
                        'page': page_num,
                        'confidence': word_data.get('confidence', 1.0)
                    })
                    
                    # Normalize & tokenize this word once
                    tokens = self._normalize_and_tokenize(all_word_data[-1]['text'])
                    doc_tokens.extend(tokens)
                    
                    # Each produced token points back to this word
                    token_to_word.extend([word_idx] * len(tokens))
        
        return all_word_data, doc_tokens, token_to_word
    
    def _exact_match(
        self,
        quote_tokens: List[str],
        pages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Exact multi-token scan for quote matches using prebuilt token structures.
        
        Args:
            quote_tokens: Normalized quote tokens to match
            pages: Pages with word bounding boxes
            
        Returns:
            List of matched word spans or empty list if no match
        """
        # Build tokens and mapping in single pass (guaranteed consistent with quote)
        all_word_data, doc_tokens, token_to_word = self._build_doc_tokens(pages)
        
        qlen = len(quote_tokens)
        n = len(doc_tokens)
        
        if qlen == 0 or n == 0 or qlen > n:
            return []
        
        # Sliding window match on prebuilt tokens
        for i in range(n - qlen + 1):
            if doc_tokens[i:i + qlen] == quote_tokens:
                # Map token span back to unique word indices
                word_indices = token_to_word[i:i + qlen]
                
                # Deduplicate while preserving order (some tokens may come from same word)
                result_indices = []
                seen = set()
                for idx in word_indices:
                    if idx not in seen:
                        seen.add(idx)
                        result_indices.append(idx)
                
                return [all_word_data[j] for j in result_indices]
        
        return []
    
    def _fuzzy_match(
        self,
        quote_tokens: List[str],
        pages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Fuzzy matching fallback for OCR errors using prebuilt token structures.
        
        Uses token-wise similarity scoring to find best match.
        
        Args:
            quote_tokens: Normalized quote tokens to match
            pages: Pages with word bounding boxes
            
        Returns:
            List of matched word spans or empty list if no match
        """
        # Reuse the same token building approach for consistency
        all_word_data, doc_tokens, token_to_word = self._build_doc_tokens(pages)
        
        qlen = len(quote_tokens)
        n = len(doc_tokens)
        
        if qlen == 0 or n == 0 or qlen > n:
            return []
        
        # Find best matching window using token-wise similarity
        best_score = 0.0
        best_start = -1
        
        for i in range(n - qlen + 1):
            # Calculate similarity for this window
            total_similarity = sum(
                self._string_similarity(quote_tokens[j], doc_tokens[i + j])
                for j in range(qlen)
            )
            avg_similarity = total_similarity / qlen
            
            if avg_similarity > best_score:
                best_score = avg_similarity
                best_start = i
        
        # Check if best match meets threshold
        if best_start == -1 or best_score < self.fuzzy_threshold:
            return []
        
        # Map token span back to unique word indices
        word_indices = token_to_word[best_start:best_start + qlen]
        result_indices = []
        seen = set()
        for idx in word_indices:
            if idx not in seen:
                seen.add(idx)
                result_indices.append(idx)
        
        return [all_word_data[j] for j in result_indices]
    
    def _string_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate string similarity using Jaro-Winkler-like metric.
        
        Simple implementation without external dependencies.
        
        Args:
            s1: First string
            s2: Second string
            
        Returns:
            Similarity score (0-1)
        """
        if s1 == s2:
            return 1.0
        
        if not s1 or not s2:
            return 0.0
        
        # Simple character-based similarity
        # Count matching characters in order
        matches = 0
        min_len = min(len(s1), len(s2))
        
        for i in range(min_len):
            if s1[i] == s2[i]:
                matches += 1
        
        # Also count matching characters out of order (transpositions)
        s1_chars = set(s1)
        s2_chars = set(s2)
        common_chars = len(s1_chars & s2_chars)
        
        # Combine positional and set-based matching
        positional_score = matches / max(len(s1), len(s2))
        set_score = common_chars / max(len(s1_chars), len(s2_chars))
        
        # Weight positional matching more heavily
        return 0.7 * positional_score + 0.3 * set_score
    
    def compute_union_bbox(self, word_spans: List[Dict[str, Any]]) -> List[float]:
        """
        Compute union bounding box from multiple word spans.
        
        Args:
            word_spans: List of word span dicts with bbox field
            
        Returns:
            Union bounding box [x0, y0, x1, y1] or [0, 0, 0, 0] if empty
        """
        if not word_spans:
            return [0.0, 0.0, 0.0, 0.0]
        
        bboxes = [span.get('bbox', [0, 0, 0, 0]) for span in word_spans]
        bboxes = [bbox for bbox in bboxes if len(bbox) == 4]
        
        if not bboxes:
            return [0.0, 0.0, 0.0, 0.0]
        
        x0_min = min(bbox[0] for bbox in bboxes)
        y0_min = min(bbox[1] for bbox in bboxes)
        x1_max = max(bbox[2] for bbox in bboxes)
        y1_max = max(bbox[3] for bbox in bboxes)
        
        return [x0_min, y0_min, x1_max, y1_max]
