"""
OCR Bounding Box Service

Extracts and normalizes word-level bounding boxes from DocTR OCR output.
Provides structured bounding box data for precise quote highlighting in OCR documents.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class WordBoundingBox:
    """Word-level bounding box with normalized coordinates"""
    text: str                    # The actual word text
    confidence: float            # OCR confidence score (0-1)
    bbox: List[float]           # [x0, y0, x1, y1] normalized (0-1)
    page_number: int            # 1-based page number
    line_index: int             # Line index within page
    word_index: int             # Word index within line


@dataclass
class LineBoundingBoxes:
    """Line-level grouping of word bounding boxes"""
    line_text: str
    page_number: int
    line_index: int
    words: List[WordBoundingBox]
    line_bbox: List[float]      # Union of all word boxes in line


@dataclass
class PageBoundingBoxes:
    """Page-level bounding box data"""
    page_number: int
    lines: List[LineBoundingBoxes]
    page_dimensions: Dict[str, float]  # width, height at OCR time


@dataclass
class DocumentBoundingBoxes:
    """Complete document bounding box data"""
    document_id: str
    filename: str
    pages: List[PageBoundingBoxes]
    metadata: Dict[str, Any]


class OCRBBoxService:
    """Service for extracting and normalizing bounding boxes from DocTR output"""
    
    @staticmethod
    def extract_bounding_boxes_from_doctr(
        doctr_export: Dict[str, Any],
        document_id: str,
        filename: str
    ) -> DocumentBoundingBoxes:
        """
        Extract and normalize bounding boxes from DocTR export.
        
        Args:
            doctr_export: DocTR document export dict with pages/blocks/lines/words
            document_id: Unique document identifier
            filename: Original filename
            
        Returns:
            DocumentBoundingBoxes with normalized coordinates
        """
        logger.info(f"Extracting bounding boxes from DocTR export for {filename}")
        
        pages_data = []
        
        # Iterate through pages in DocTR export
        for page_idx, page in enumerate(doctr_export.get('pages', [])):
            page_number = page_idx + 1
            
            # Get page dimensions (typically normalized to [0,1] already in DocTR)
            page_dimensions = {
                'width': page.get('dimensions', [1.0, 1.0])[0],
                'height': page.get('dimensions', [1.0, 1.0])[1]
            }
            
            # Extract all words with geometry from this page
            page_words = OCRBBoxService._extract_words_from_page(
                page, page_number, page_dimensions
            )
            
            # Group words into lines
            lines = OCRBBoxService._group_words_by_lines(page_words)
            
            pages_data.append(PageBoundingBoxes(
                page_number=page_number,
                lines=lines,
                page_dimensions=page_dimensions
            ))
        
        logger.info(f"Extracted {len(pages_data)} pages with bounding boxes")
        
        return DocumentBoundingBoxes(
            document_id=document_id,
            filename=filename,
            pages=pages_data,
            metadata={
                'total_pages': len(pages_data),
                'total_words': sum(
                    sum(len(line.words) for line in page.lines)
                    for page in pages_data
                )
            }
        )
    
    @staticmethod
    def _extract_words_from_page(
        page: Dict[str, Any],
        page_number: int,
        page_dimensions: Dict[str, float]
    ) -> List[WordBoundingBox]:
        """
        Extract all words with geometry from a page.
        
        Args:
            page: DocTR page dict
            page_number: 1-based page number
            page_dimensions: Page width and height
            
        Returns:
            List of WordBoundingBox objects
        """
        words = []
        line_index = 0
        
        # Iterate through blocks -> lines -> words hierarchy
        for block in page.get('blocks', []):
            for line in block.get('lines', []):
                word_index = 0
                
                for word in line.get('words', []):
                    word_text = word.get('value', '')
                    confidence = word.get('confidence', 0.0)
                    geometry = word.get('geometry', [[0, 0], [0, 0]])
                    
                    # Normalize bounding box coordinates
                    bbox = OCRBBoxService._normalize_bbox_coordinates(
                        geometry, page_dimensions
                    )
                    
                    words.append(WordBoundingBox(
                        text=word_text,
                        confidence=confidence,
                        bbox=bbox,
                        page_number=page_number,
                        line_index=line_index,
                        word_index=word_index
                    ))
                    
                    word_index += 1
                
                line_index += 1
        
        return words
    
    @staticmethod
    def _normalize_bbox_coordinates(
        geometry: List[List[float]],
        page_dimensions: Dict[str, float]
    ) -> List[float]:
        """
        Convert DocTR geometry to normalized [x0, y0, x1, y1] format.
        
        DocTR geometry format: [[x_min, y_min], [x_max, y_max]]
        Output format: [x0, y0, x1, y1] with values normalized to [0, 1]
        
        Args:
            geometry: DocTR bounding box geometry
            page_dimensions: Page width and height
            
        Returns:
            [x0, y0, x1, y1] with normalized coordinates
        """
        if not geometry or len(geometry) < 2:
            return [0.0, 0.0, 0.0, 0.0]
        
        # DocTR already provides normalized coordinates [0, 1]
        # geometry format: [[x_min, y_min], [x_max, y_max]]
        x0, y0 = geometry[0]
        x1, y1 = geometry[1]
        
        # Ensure coordinates are in valid range [0, 1]
        x0 = max(0.0, min(1.0, x0))
        y0 = max(0.0, min(1.0, y0))
        x1 = max(0.0, min(1.0, x1))
        y1 = max(0.0, min(1.0, y1))
        
        return [x0, y0, x1, y1]
    
    @staticmethod
    def _group_words_by_lines(words: List[WordBoundingBox]) -> List[LineBoundingBoxes]:
        """
        Group word-level boxes into line-level structures.
        
        Words are already tagged with line_index from DocTR,
        so we just need to group by that index.
        
        Args:
            words: List of word bounding boxes
            
        Returns:
            List of LineBoundingBoxes with line-grouped words
        """
        if not words:
            return []
        
        # Group words by (page_number, line_index)
        lines_dict: Dict[Tuple[int, int], List[WordBoundingBox]] = {}
        
        for word in words:
            key = (word.page_number, word.line_index)
            if key not in lines_dict:
                lines_dict[key] = []
            lines_dict[key].append(word)
        
        # Create LineBoundingBoxes for each line
        lines = []
        for (page_number, line_index), line_words in sorted(lines_dict.items()):
            # Sort words by word_index to maintain order
            line_words.sort(key=lambda w: w.word_index)
            
            # Compute line text and union bounding box
            line_text = ' '.join(word.text for word in line_words)
            line_bbox = OCRBBoxService._union_bboxes([word.bbox for word in line_words])
            
            lines.append(LineBoundingBoxes(
                line_text=line_text,
                page_number=page_number,
                line_index=line_index,
                words=line_words,
                line_bbox=line_bbox
            ))
        
        return lines
    
    @staticmethod
    def _union_bboxes(bboxes: List[List[float]]) -> List[float]:
        """
        Compute union bounding box from multiple boxes.
        
        Args:
            bboxes: List of [x0, y0, x1, y1] bounding boxes
            
        Returns:
            [x0, y0, x1, y1] union bounding box
        """
        if not bboxes:
            return [0.0, 0.0, 0.0, 0.0]
        
        # Find minimum x0, y0 and maximum x1, y1
        x0_min = min(bbox[0] for bbox in bboxes)
        y0_min = min(bbox[1] for bbox in bboxes)
        x1_max = max(bbox[2] for bbox in bboxes)
        y1_max = max(bbox[3] for bbox in bboxes)
        
        return [x0_min, y0_min, x1_max, y1_max]
    
    @staticmethod
    def to_dict(bbox_data: DocumentBoundingBoxes) -> Dict[str, Any]:
        """
        Convert DocumentBoundingBoxes to dictionary for JSON serialization.
        
        Args:
            bbox_data: DocumentBoundingBoxes object
            
        Returns:
            Dictionary representation
        """
        return {
            'document_id': bbox_data.document_id,
            'filename': bbox_data.filename,
            'pages': [
                {
                    'page_number': page.page_number,
                    'page_dimensions': page.page_dimensions,
                    'lines': [
                        {
                            'line_text': line.line_text,
                            'page_number': line.page_number,
                            'line_index': line.line_index,
                            'line_bbox': line.line_bbox,
                            'words': [
                                {
                                    'text': word.text,
                                    'confidence': word.confidence,
                                    'bbox': word.bbox,
                                    'page_number': word.page_number,
                                    'line_index': word.line_index,
                                    'word_index': word.word_index
                                }
                                for word in line.words
                            ]
                        }
                        for line in page.lines
                    ]
                }
                for page in bbox_data.pages
            ],
            'metadata': bbox_data.metadata
        }
