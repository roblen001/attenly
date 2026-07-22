/**
 * Audit Trail Decorator Utility
 */

import React from 'react';
import type { AuditChange } from '../types';

function formatTooltip(change: AuditChange): string {
  const changeType = change.change_type === 'insert' ? 'Added' : 'Deleted';
  const userName = change.user_name || 'Unknown User';

  const date = new Date(change.created_at);
  const formattedDate = date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
  const formattedTime = date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });

  return `${changeType} by ${userName} · ${formattedDate} · ${formattedTime}`;
}

interface TextSegment {
  text: string;
  change?: AuditChange;
  startOffset: number;
  endOffset: number;
}

export function decorateWithAuditSpans(
  text: string,
  changes: AuditChange[] | undefined
): React.ReactNode {
  if (!changes || changes.length === 0) {
    return text;
  }

  const sortedChanges = [...changes].sort(
    (a, b) => a.start_offset - b.start_offset
  );
  const segments: TextSegment[] = [];
  let currentPosition = 0;

  for (const change of sortedChanges) {
    // Unchanged text before this change
    if (currentPosition < change.start_offset) {
      const unchangedText = text.substring(currentPosition, change.start_offset);
      segments.push({
        text: unchangedText,
        startOffset: currentPosition,
        endOffset: change.start_offset,
      });
      currentPosition = change.start_offset;
    }

    if (change.change_type === 'insert') {
      const expected = change.text_content;

      segments.push({
        text: expected, // trust backend text
        change,
        startOffset: change.start_offset,
        endOffset: change.end_offset,
      });

      currentPosition = change.end_offset;
    } else {
      // DELETE: text doesn't exist in final string
      segments.push({
        text: change.text_content,
        change,
        startOffset: change.start_offset,
        endOffset: change.start_offset,
      });

      // no advance
    }
  }

  // Trailing unchanged text
  if (currentPosition < text.length) {
    const tailText = text.substring(currentPosition);
    segments.push({
      text: tailText,
      startOffset: currentPosition,
      endOffset: text.length,
    });
  }

  return (
    <>
      {segments.map((segment, index) => {
        if (!segment.change) {
          return <React.Fragment key={index}>{segment.text}</React.Fragment>;
        }

        const className =
          segment.change.change_type === 'insert'
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
