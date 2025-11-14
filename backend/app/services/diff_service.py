"""
Diff Service for Audit Trail
Handles text comparison between AI baseline and user-modified content.
Uses Google's diff-match-patch algorithm for robust text diffing.
"""

from typing import List, Dict, Any
from diff_match_patch import diff_match_patch
from bs4 import BeautifulSoup
import string
import logging

logger = logging.getLogger(__name__)


class DiffService:
    """
    Service for computing differences between text versions.
    
    Uses diff-match-patch for accurate text comparison and applies
    semantic merging to produce human-readable change spans.
    
    Merging Rules:
    - Adjacent operations of the same type (INSERT/INSERT or DELETE/DELETE)
      are merged into single spans
    - Operations separated only by whitespace/punctuation are merged
    - This produces cleaner visualizations: "added this phrase" rather than
      "added 'this' ... added 'phrase'" with fragments in between
    
    Semantic Diff Merging Configuration:
    - Merging Strategy: Rule-based (not threshold-based)
    - Merge adjacent INSERT or DELETE operations
    - Merge across EQUAL spans containing only whitespace/punctuation
    - Never merge INSERT and DELETE operations together
    
    Rationale: Legal/insurance text requires predictable, semantic spans
    rather than character-level fragmentation.
    """

    def __init__(self):
        """Initialize diff-match-patch instance with standard settings."""
        self.dmp = diff_match_patch()
        # Standard timeout for diff computation (1 second)
        self.dmp.Diff_Timeout = 1.0

    def compute_answer_diff(
        self,
        baseline_text: str,
        current_text: str,
        placeholder: str
    ) -> List[Dict[str, Any]]:
        """
        Compute differences between baseline and current text for one answer.

        This is the main entry point for diff computation. It handles:
        1. HTML stripping (compare plain text)
        2. Computing semantic diffs
        3. Merging adjacent changes for cleaner spans
        4. Converting to storage format with offsets

        Args:
            baseline_text: Original AI-generated text
            current_text: Current user-modified text
            placeholder: Answer placeholder key (e.g., "loss_description")

        Returns:
            List of change dictionaries ready for database storage:
            [
                {
                    "change_type": "insert" or "delete",
                    "text_content": "the changed text",
                    "start_offset": 0,
                    "end_offset": 10,
                    "placeholder": "loss_description"
                },
                ...
            ]
        """
        try:
            # Strip HTML from both texts for clean comparison
            baseline_plain = self.html_to_plain_text(baseline_text)
            current_plain = self.html_to_plain_text(current_text)

            # Compute semantic diff
            diffs = self.dmp.diff_main(baseline_plain, current_plain)
            
            # Apply semantic cleanup for better readability
            self.dmp.diff_cleanupSemantic(diffs)
            
            # Merge adjacent changes for cleaner, more semantic spans
            merged_diffs = self._merge_semantic_diffs(diffs)
            
            # Check if any actual changes exist (revert-to-baseline detection)
            has_changes = any(op != 0 for op, _ in merged_diffs)
            if not has_changes:
                logger.info(f"No net changes for {placeholder} (reverted to baseline)")
                return []

            # Convert merged diff output to storage format
            changes = self.extract_changes_for_storage(
                merged_diffs,
                current_plain,
                placeholder
            )

            logger.info(
                f"Computed diff for {placeholder}: "
                f"{len(changes)} changes found (after semantic merging)"
            )

            return changes

        except Exception as e:
            logger.error(
                f"Error computing diff for {placeholder}: {str(e)}",
                exc_info=True
            )
            # Return empty list on error - don't break the save flow
            return []

    def html_to_plain_text(self, html: str) -> str:
        """
        Strip HTML tags for text comparison, preserving structure.

        This function removes HTML markup while preserving the readable
        text content. It handles common HTML entities and ensures clean
        text for accurate comparison.

        Args:
            html: HTML string (may include formatting tags)

        Returns:
            Plain text string suitable for comparison
        """
        if not html:
            return ""

        try:
            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract text (automatically handles HTML entities)
            text = soup.get_text()
            
            # Clean up excessive whitespace while preserving structure
            # Replace multiple spaces with single space
            text = ' '.join(text.split())
            
            return text.strip()

        except Exception as e:
            logger.warning(
                f"Error stripping HTML, returning original: {str(e)}"
            )
            # Fallback: return original text if parsing fails
            return html

    def extract_changes_for_storage(
        self,
        diffs: List[tuple],
        final_text: str,
        placeholder: str
    ) -> List[Dict[str, Any]]:
        """
        Convert diff-match-patch output to database storage format.

        Walks through the diff output and computes character offsets
        for each change in the final text. This enables precise highlighting
        in the UI.

        Args:
            diffs: diff-match-patch output [(operation, text), ...]
                   operation: -1 (delete), 0 (equal), 1 (insert)
            final_text: The final (current) text after all changes
            placeholder: Answer placeholder for grouping changes

        Returns:
            List of change dictionaries with offsets:
            [
                {
                    "change_type": "insert" or "delete",
                    "text_content": "changed text",
                    "start_offset": position in final text,
                    "end_offset": position in final text,
                    "placeholder": "answer_key"
                }
            ]
        """
        changes = []
        current_position = 0  # Track position in final (current) text

        for operation, text in diffs:
            text_length = len(text)

            if operation == 1:  # INSERT
                # Text is in current but not in baseline
                changes.append({
                    "change_type": "insert",
                    "text_content": text,
                    "start_offset": current_position,
                    "end_offset": current_position + text_length,
                    "answer_placeholder": placeholder
                })
                current_position += text_length

            elif operation == -1:  # DELETE
                # Text is in baseline but not in current
                # Deleted text doesn't occupy space in final text,
                # so we record it at the current position
                changes.append({
                    "change_type": "delete",
                    "text_content": text,
                    "start_offset": current_position,
                    "end_offset": current_position,  # No length in final text
                    "answer_placeholder": placeholder
                })
                # Don't advance position - deleted text not in final

            else:  # operation == 0 (EQUAL)
                # Text unchanged, just advance position
                current_position += text_length

        return changes

    def _merge_semantic_diffs(self, diffs: List[tuple]) -> List[tuple]:
        """
        Merge adjacent changes of the same type for cleaner semantic spans.
        
        This method applies two passes:
        1. Merge operations of same type separated by short EQUAL spans
        2. Collect all DELETEs in a region, then all INSERTs in that region
        
        This produces human-readable change spans. For example:
        
        Instead of: "parked [red]on[/red] [green]at[/green] the [red]street[/red] [green]residence[/green]"
        Produces: "parked [red]on the street[/red] [green]at the residence[/green]"
        
        Args:
            diffs: List of (operation, text) tuples from diff-match-patch
                   operation: -1 (delete), 0 (equal), 1 (insert)
        
        Returns:
            Merged diff list with same structure [(op, text), ...]
        """
        if not diffs:
            return diffs
        
        # Pass 1: Merge operations of same type separated by short EQUAL spans
        MERGE_THRESHOLD = 10  # characters
        merged_pass1 = []
        i = 0
        
        while i < len(diffs):
            current_op, current_text = diffs[i]
            
            # If EQUAL operation, keep as-is
            if current_op == 0:
                merged_pass1.append((current_op, current_text))
                i += 1
                continue
            
            # For INSERT or DELETE, look ahead to merge with similar operations
            merge_buffer = [current_text]
            j = i + 1
            
            while j < len(diffs):
                next_op, next_text = diffs[j]
                
                # If same operation type, merge it
                if next_op == current_op:
                    merge_buffer.append(next_text)
                    j += 1
                # If EQUAL span is short enough, absorb it and continue
                elif next_op == 0 and len(next_text) <= MERGE_THRESHOLD:
                    merge_buffer.append(next_text)
                    j += 1
                # Otherwise, stop merging
                else:
                    break
            
            merged_text = ''.join(merge_buffer)
            merged_pass1.append((current_op, merged_text))
            i = j
        
        # Pass 2: Group DELETEs and INSERTs in close proximity
        # If we have DELETE-INSERT-DELETE-INSERT pattern in a small region,
        # collect all DELETEs together, then all INSERTs
        merged_pass2 = []
        i = 0
        
        while i < len(merged_pass1):
            current_op, current_text = merged_pass1[i]
            
            # Keep EQUAL operations as-is
            if current_op == 0:
                merged_pass2.append((current_op, current_text))
                i += 1
                continue
            
            # Check if we're in a substitution region (alternating DEL/INS)
            region_parts = []  # Store (op, text) tuples
            j = i
            
            # Collect a region of changes (stops at long EQUAL span)
            while j < len(merged_pass1):
                op, text = merged_pass1[j]
                
                if op == -1:  # DELETE
                    region_parts.append((op, text))
                    j += 1
                elif op == 1:  # INSERT
                    region_parts.append((op, text))
                    j += 1
                elif op == 0 and len(text) <= MERGE_THRESHOLD:
                    # Short EQUAL - include it in the region
                    region_parts.append((op, text))
                    j += 1
                else:
                    # Long EQUAL or end - stop the region
                    break
            
            # Now consolidate: collect all DELETEs, all INSERTs
            region_deletes = []
            region_inserts = []
            
            for op, text in region_parts:
                if op == -1:
                    region_deletes.append(text)
                elif op == 1:
                    region_inserts.append(text)
                elif op == 0:
                    # EQUAL spans go into both to show context
                    region_deletes.append(text)
                    region_inserts.append(text)
            
            # Emit grouped changes
            if region_deletes:
                merged_pass2.append((-1, ''.join(region_deletes)))
            if region_inserts:
                merged_pass2.append((1, ''.join(region_inserts)))
            
            i = j
        
        logger.debug(f"Merged {len(diffs)} diff operations into {len(merged_pass2)} semantic spans")
        return merged_pass2

    def _is_whitespace_or_punctuation(self, text: str) -> bool:
        """
        Check if text contains only whitespace and/or punctuation.
        
        Used to determine if an EQUAL span between two changes of the same type
        should be absorbed into a merged span for cleaner visualization.
        
        Args:
            text: Text to check
        
        Returns:
            True if text contains only whitespace/punctuation characters
        """
        if not text:
            return True
        
        allowed = set(string.whitespace + string.punctuation)
        return all(c in allowed for c in text)

    def has_changes(self, baseline_text: str, current_text: str) -> bool:
        """
        Quick check if two texts differ (after HTML stripping).

        Useful for determining if we need to store changes at all.

        Args:
            baseline_text: Original AI-generated text
            current_text: Current user-modified text

        Returns:
            True if texts differ, False if identical
        """
        baseline_plain = self.html_to_plain_text(baseline_text)
        current_plain = self.html_to_plain_text(current_text)
        return baseline_plain != current_plain
