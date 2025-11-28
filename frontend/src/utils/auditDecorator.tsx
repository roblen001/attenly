/**
 * Audit Trail Decorator Utility
 */

import React from 'react';
import type { AuditChange } from '../types';

// 🔊 This should show once when the module is loaded
console.log('[AUDIT] auditDecorator module loaded');

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
  console.groupCollapsed(
    '[AUDIT] decorateWithAuditSpans call',
    'len=',
    text?.length ?? 0
  );
  console.log('[AUDIT] full text:', JSON.stringify(text));
  console.log('[AUDIT] incoming changes:', changes);

  if (!changes || changes.length === 0) {
    console.log('[AUDIT] no changes → returning plain text');
    console.groupEnd();
    return text;
  }

  const sortedChanges = [...changes].sort(
    (a, b) => a.start_offset - b.start_offset
  );
  console.log('[AUDIT] sortedChanges:', sortedChanges);

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
      console.log('[AUDIT] unchanged segment', {
        from: currentPosition,
        to: change.start_offset,
        text: unchangedText,
      });
      currentPosition = change.start_offset;
    }

    if (change.change_type === 'insert') {
      const fromText = text.substring(change.start_offset, change.end_offset);
      const expected = change.text_content;

      if (fromText !== expected) {
        console.warn(
          '[AUDIT] INSERT mismatch between frontend text and backend text_content',
          {
            placeholder: change.answer_placeholder,
            start_offset: change.start_offset,
            end_offset: change.end_offset,
            fromText,
            expected,
          }
        );
      }

      segments.push({
        text: expected, // trust backend text
        change,
        startOffset: change.start_offset,
        endOffset: change.end_offset,
      });

      console.log('[AUDIT] INSERT segment', {
        start_offset: change.start_offset,
        end_offset: change.end_offset,
        text_used: expected,
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

      console.log('[AUDIT] DELETE segment', {
        at_position: change.start_offset,
        text_from_change: change.text_content,
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

    console.log('[AUDIT] trailing unchanged segment', {
      from: currentPosition,
      to: text.length,
      text: tailText,
    });
  }

  console.log('[AUDIT] final segments:', segments);
  console.groupEnd();

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
