/**
 * Audit Trail Decorator Utility
 * 
 * Converts plain text and change records into React nodes with Microsoft Word-style
 * track changes visualization (green highlights for insertions, red strikethrough for deletions).
 */

import React from 'react';
import type { AuditChange } from '../types';

/**
 * Format a tooltip string for a change with user and timestamp information.
 * 
 * @param change - The audit change containing metadata
 * @returns Formatted tooltip string
 */
function formatTooltip(change: AuditChange): string {
  const changeType = change.change_type === 'insert' ? 'Added' : 'Deleted';
  const userName = change.user_name || 'Unknown User';
  
  // Format timestamp
  const date = new Date(change.created_at);
  const formattedDate = date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
  const formattedTime = date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  });
  
  return `${changeType} by ${userName} · ${formattedDate} · ${formattedTime}`;
}

/**
 * Represents a text segment with optional change information.
 */
interface TextSegment {
  text: string;
  change?: AuditChange;
  startOffset: number;
  endOffset: number;
}

/**
 * Convert plain text with changes array into decorated React nodes with track changes styling.
 * 
 * Algorithm:
 * 1. If no changes, return plain text
 * 2. Sort changes by start_offset to process in order
 * 3. Walk through text building segments:
 *    - Unchanged regions → plain text nodes
 *    - Insert regions → <span> with green highlight
 *    - Delete regions → <span> with red strikethrough (inserted at position)
 * 4. Attach tooltip data-title attribute to each change span
 * 
 * @param text - The plain text content (after HTML stripping)
 * @param changes - Array of changes for this text, or undefined if no changes
 * @returns React fragment with mixed text/span nodes
 */
export function decorateWithAuditSpans(
  text: string,
  changes: AuditChange[] | undefined
): React.ReactNode {
  // If no changes, return plain text
  if (!changes || changes.length === 0) {
    return text;
  }
  
  // Sort changes by start_offset to process in order
  const sortedChanges = [...changes].sort((a, b) => a.start_offset - b.start_offset);
  
  // Build segments by walking through the text
  const segments: TextSegment[] = [];
  let currentPosition = 0;
  
  for (const change of sortedChanges) {
    // Add any unchanged text before this change
    if (currentPosition < change.start_offset) {
      segments.push({
        text: text.substring(currentPosition, change.start_offset),
        startOffset: currentPosition,
        endOffset: change.start_offset
      });
    }
    
    if (change.change_type === 'insert') {
      // Insert: text exists in current version
      segments.push({
        text: text.substring(change.start_offset, change.end_offset),
        change: change,
        startOffset: change.start_offset,
        endOffset: change.end_offset
      });
      currentPosition = change.end_offset;
    } else {
      // Delete: text doesn't exist in current version, show at current position
      segments.push({
        text: change.text_content,
        change: change,
        startOffset: change.start_offset,
        endOffset: change.start_offset // Deleted text has no length in final
      });
      // Don't advance currentPosition - deleted text is not in the final text
    }
  }
  
  // Add any remaining unchanged text after all changes
  if (currentPosition < text.length) {
    segments.push({
      text: text.substring(currentPosition),
      startOffset: currentPosition,
      endOffset: text.length
    });
  }
  
  // Convert segments to React nodes
  return (
    <>
      {segments.map((segment, index) => {
        if (!segment.change) {
          // Unchanged text - render as plain text
          return <React.Fragment key={index}>{segment.text}</React.Fragment>;
        }
        
        // Changed text - render with appropriate styling
        const className = segment.change.change_type === 'insert' 
          ? 'audit-trail-insert' 
          : 'audit-trail-delete';
        
        const tooltip = formatTooltip(segment.change);
        
        return (
          <span
            key={index}
            className={className}
            data-title={tooltip}
            title={tooltip}
          >
            {segment.text}
          </span>
        );
      })}
    </>
  );
}
