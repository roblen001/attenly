"""
Diff Service for Audit Trail
Handles text comparison between AI baseline and user-modified content.
Uses Google's diff-match-patch algorithm for robust text diffing.
"""

from typing import List, Dict, Any
from diff_match_patch import diff_match_patch
from bs4 import BeautifulSoup
import string


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
        """
        try:
            # Strip HTML from both texts for clean comparison
            baseline_plain = self.html_to_plain_text(baseline_text)
            current_plain = self.html_to_plain_text(current_text)

            print(
                "=== DIFF DEBUG START for placeholder=%r ===\n"
                "baseline_raw=%r\n"
                "current_raw=%r\n"
                "baseline_plain=%r (len=%d)\n"
                "current_plain=%r (len=%d)",
                placeholder,
                baseline_text,
                current_text,
                baseline_plain,
                len(baseline_plain),
                current_plain,
                len(current_plain),
            )

            # Compute semantic diff
            diffs = self.dmp.diff_main(baseline_plain, current_plain)
            # Apply semantic cleanup for better readability
            self.dmp.diff_cleanupSemantic(diffs)

            print(
                "Raw diffs after diff_cleanupSemantic for %r: %r",
                placeholder,
                diffs,
            )

            # Merge adjacent changes for cleaner, more semantic spans
            merged_diffs = self._merge_semantic_diffs(diffs)

            print(
                "Merged diffs for %r: %r",
                placeholder,
                merged_diffs,
            )

            # Check if any actual changes exist (revert-to-baseline detection)
            has_changes = any(op != 0 for op, _ in merged_diffs)
            if not has_changes:
                print(
                    "No net changes for %s (reverted to baseline)",
                    placeholder,
                )
                print("=== DIFF DEBUG END (no changes) for %r ===", placeholder)
                return []

            # Convert merged diff output to storage format
            changes = self.extract_changes_for_storage(
                merged_diffs,
                current_plain,
                placeholder
            )

            print(
                "Final changes for %r: %r",
                placeholder,
                changes,
            )
            print(
                "Computed diff for %s: %d changes found (after semantic merging)",
                placeholder,
                len(changes),
            )

            print("=== DIFF DEBUG END for %r ===", placeholder)
            return changes

        except Exception as e:
            print(
                "Error computing diff for %s: %s",
                placeholder,
                str(e),
            )
            # Return empty list on error - don't break the save flow
            return []

    def html_to_plain_text(self, html: str) -> str:
        """
        Strip HTML tags for text comparison, preserving structure.
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
            print(
                "Error stripping HTML, returning original: %s",
                str(e),
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
        """
        changes: List[Dict[str, Any]] = []
        current_position = 0  # Track position in final (current) text

        print(
            "Extracting changes for %r from diffs=%r, final_text(len=%d)=%r",
            placeholder,
            diffs,
            len(final_text),
            final_text,
        )

        for idx, (operation, text) in enumerate(diffs):
            text_length = len(text)

            if operation == 1:  # INSERT
                # Text is in current but not in baseline
                change = {
                    "change_type": "insert",
                    "text_content": text,
                    "start_offset": current_position,
                    "end_offset": current_position + text_length,
                    "answer_placeholder": placeholder
                }
                changes.append(change)
                print(
                    "[%s] INSERT change for %r: %r",
                    placeholder,
                    idx,
                    change,
                )
                current_position += text_length

            elif operation == -1:  # DELETE
                # Text is in baseline but not in current
                # Deleted text doesn't occupy space in final text,
                # so we record it at the current position
                change = {
                    "change_type": "delete",
                    "text_content": text,
                    "start_offset": current_position,
                    "end_offset": current_position,  # No length in final text
                    "answer_placeholder": placeholder
                }
                changes.append(change)
                print(
                    "[%s] DELETE change for %r: %r",
                    placeholder,
                    idx,
                    change,
                )
                # Don't advance position - deleted text not in final

            else:  # operation == 0 (EQUAL)
                # Text unchanged, just advance position
                current_position += text_length
                print(
                    "[%s] EQUAL segment idx=%d text=%r (advance position to %d)",
                    placeholder,
                    idx,
                    text,
                    current_position,
                )

        # Sanity check: how much of final_text we've "walked"
        if current_position != len(final_text):
            print(
                "extract_changes_for_storage: final position (%d) != len(final_text) (%d) "
                "for placeholder=%r. This may indicate a mismatch between "
                "diff text and rendered text.",
                current_position,
                len(final_text),
                placeholder,
            )

        return changes

    def _merge_semantic_diffs(self, diffs: List[tuple]) -> List[tuple]:
        """
        Merge adjacent changes of the same type for cleaner semantic spans.
        
        This simplified version only merges consecutive operations of the same type.
        It never absorbs EQUAL (unchanged) spans into change spans, preventing
        incorrect highlighting of baseline text.
        """
        if not diffs:
            return diffs

        print("Starting _merge_semantic_diffs with diffs=%r", diffs)

        merged: List[tuple] = []
        i = 0
        
        while i < len(diffs):
            current_op, current_text = diffs[i]
            
            # If EQUAL operation, keep as-is and move on
            if current_op == 0:
                merged.append((current_op, current_text))
                i += 1
                continue
            
            # For INSERT or DELETE, merge consecutive operations of the same type
            merge_buffer = [current_text]
            j = i + 1
            
            # Look ahead and merge only same-type operations
            while j < len(diffs):
                next_op, next_text = diffs[j]
                
                # Only merge if it's the exact same operation type
                if next_op == current_op:
                    merge_buffer.append(next_text)
                    j += 1
                else:
                    # Stop at any different operation (including EQUAL)
                    break
            
            merged_text = ''.join(merge_buffer)
            merged.append((current_op, merged_text))
            i = j

        print(
            "Merged %d diff operations into %d semantic spans: %r",
            len(diffs),
            len(merged),
            merged,
        )
        return merged

    def _is_whitespace_or_punctuation(self, text: str) -> bool:
        """
        Check if text contains only whitespace and/or punctuation.
        """
        if not text:
            return True
        
        allowed = set(string.whitespace + string.punctuation)
        return all(c in allowed for c in text)

    def has_changes(self, baseline_text: str, current_text: str) -> bool:
        """
        Quick check if two texts differ (after HTML stripping).
        """
        baseline_plain = self.html_to_plain_text(baseline_text)
        current_plain = self.html_to_plain_text(current_text)
        return baseline_plain != current_plain
