import type { ReportAnswer, Question, ColumnDefinition } from '../types';

// Report styling utilities
export interface ReportStyleConfig {
  context: 'preview' | 'pdf';
  interactive?: boolean;
}

export const generateSuperscript = (num: number): string => {
  const supers = ['⁰','¹','²','³','⁴','⁵','⁶','⁷','⁸','⁹'];
  const digits = num
    .toString()
    .split('')
    .map(d => supers[parseInt(d, 10)])
    .join('');
  return `⁽${digits}⁾`;
};

/**
 * HTML escape utility - prevents XSS attacks
 */
export const escapeHtml = (text: string): string => {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return text.replace(/[&<>"']/g, m => map[m]);
};

/**
 * Render a list answer as HTML list items with individual editing and targeted quotes
 * Returns <li> elements that go inside <ul> wrapper (provided by template)
 */
export const renderListAnswer = (
  answer: unknown,
  quotes: Array<{ index: number; target?: { type: string; index?: number; row?: number; key?: string } }> = [],
  answerId: string,
  context: 'preview' | 'pdf' = 'preview'
): string => {
  if (!Array.isArray(answer)) {
    // Fallback for non-array
    return `<li><span class="editable-answer" data-answer-id="${answerId}" data-list-index="0">${escapeHtml(String(answer))}</span></li>`;
  }
  
  return answer
    .map((item, index) => {
      const itemText = escapeHtml(String(item));
      
      // Find quotes for this specific list item
      const itemQuotes = quotes.filter(q => 
        q.target?.type === 'list' && q.target?.index === index
      );
      
      // Generate superscripts for this item's quotes
      let superscripts = '';
      if (itemQuotes.length > 0) {
        if (context === 'pdf') {
          superscripts = itemQuotes.map(q => generateSuperscript(q.index)).join('');
        } else {
          superscripts = itemQuotes.map(q =>
            `<sup class="quote-superscript" data-quote-index="${q.index - 1}">${generateSuperscript(q.index)}</sup>`
          ).join('');
        }
      }
      
      // Wrap each item in its own editable span
      return `<li><span class="editable-answer" data-answer-id="${answerId}" data-list-index="${index}">${itemText}${superscripts}</span></li>`;
    })
    .join('\n    ');
};

/**
 * Render a table answer as complete table HTML with individual cell editing and targeted quotes
 * Returns <thead> and <tbody> elements (template provides <table> wrapper)
 */
export const renderTableAnswer = (
  answer: unknown,
  columns: ColumnDefinition[],
  quotes: Array<{ index: number; target?: { type: string; index?: number; row?: number; key?: string } }> = [],
  answerId: string,
  context: 'preview' | 'pdf' = 'preview'
): string => {
  if (!Array.isArray(answer)) {
    return `<thead><tr><th>Error</th></tr></thead><tbody><tr><td>Invalid table data</td></tr></tbody>`;
  }
  
  if (!columns || columns.length === 0) {
    return `<thead><tr><th>Error</th></tr></thead><tbody><tr><td>No columns defined</td></tr></tbody>`;
  }
  
  // Generate thead
  const headerCells = columns
    .map(col => `<th>${escapeHtml(col.header)}</th>`)
    .join('');
  const thead = `<thead><tr>${headerCells}</tr></thead>`;
  
  // Generate tbody with individual cell editing
  const rows = answer.map((row, rowIndex) => {
    if (typeof row !== 'object' || row === null) {
      return '';
    }
    
    const cells = columns
      .map(col => {
        const cellValue = String(row[col.key] || '');
        const cellText = escapeHtml(cellValue);
        
        // Find quotes for this specific cell
        const cellQuotes = quotes.filter(q =>
          q.target?.type === 'table' &&
          q.target?.row === rowIndex &&
          q.target?.key === col.key
        );
        
        // Generate superscripts for this cell's quotes
        let superscripts = '';
        if (cellQuotes.length > 0) {
          if (context === 'pdf') {
            superscripts = cellQuotes.map(q => generateSuperscript(q.index)).join('');
          } else {
            superscripts = cellQuotes.map(q =>
              `<sup class="quote-superscript" data-quote-index="${q.index - 1}">${generateSuperscript(q.index)}</sup>`
            ).join('');
          }
        }
        
        // Wrap each cell value in its own editable span
        return `<td><span class="editable-answer" data-answer-id="${answerId}" data-table-row="${rowIndex}" data-table-col="${col.key}">${cellText}${superscripts}</span></td>`;
      })
      .join('');
    
    return `<tr>${cells}</tr>`;
  }).filter(row => row !== '').join('\n      ');
  
  const tbody = rows 
    ? `<tbody>${rows}</tbody>` 
    : `<tbody><tr><td colspan="${columns.length}">No data</td></tr></tbody>`;
  
  return `${thead}\n    ${tbody}`;
};

/**
 * Route to appropriate renderer based on answer type
 * Mirrors backend pdf_generator.py rendering logic
 */
export const renderAnswer = (
  answer: unknown,
  question?: Question
): string => {
  // Default to string if no question metadata or no answer_type specified
  if (!question || !question.answer_type || question.answer_type === 'string') {
    return escapeHtml(String(answer));
  }
  
  if (question.answer_type === 'list') {
    return renderListAnswer(answer, [], 'temp-id');
  }
  
  if (question.answer_type === 'table') {
    return renderTableAnswer(answer, question.columns || [], [], 'temp-id');
  }
  
  // Fallback to string
  return escapeHtml(String(answer));
};

/**
 * Prefix CSS selectors to increase specificity and prevent global style conflicts
 * Transforms: "h1 { ... }" → ".template-isolated-content h1 { ... }"
 */
const prefixCssSelectors = (css: string, prefix: string): string => {
  if (!css || !css.trim()) return '';
  
  // Simple regex-based approach to prefix selectors
  // This handles most common CSS patterns
  return css.replace(/([^{}]+)\{/g, (match, selector) => {
    // Clean up the selector
    const cleanSelector = selector.trim();
    
    // Skip @ rules (media queries, keyframes, etc.)
    if (cleanSelector.startsWith('@')) {
      return match;
    }
    
    // Split multiple selectors (e.g., "h1, h2, h3")
    const selectors = cleanSelector.split(',').map((s: string) => s.trim());
    
    // Prefix each selector
    const prefixedSelectors = selectors.map((sel: string) => {
      // Special handling for body tag - apply styles to container itself
      if (sel === 'body' || sel.startsWith('body ') || sel.startsWith('body:') || sel.startsWith('body.')) {
        // Replace body with our container
        return sel.replace(/^body/, prefix);
      }
      
      // For all other selectors, add prefix as ancestor
      return `${prefix} ${sel}`;
    });
    
    return `${prefixedSelectors.join(', ')} {`;
  });
};

export const getBaseReportStyles = (config: ReportStyleConfig, customCss?: string): string => {
  const { context, interactive = true } = config;

  // CSS isolation reset - block Attenly global styles from cascading
  const isolationReset = `
    /* CSS Isolation for Template Content - Reset to browser defaults */
    .template-isolated-content {
      all: revert;
    }

    /* Reset all descendants to prevent app styles from leaking in */
    .template-isolated-content * {
      all: revert;
    }
  `;
  
  // Base styles for interactive elements with HIGH SPECIFICITY to override everything
  const baseStyles = `
    /* Interactive Element Styles (Edit Boxes & Quotes) - Highest Priority */
    .report-html .template-isolated-content .editable-answer {
      position: relative !important;
      display: inline !important;
      background: #f7fafc !important;
      border: 1px solid transparent !important;
      border-radius: 2px !important;
      padding: 1px 3px !important;
      transition: all 0.2s ease !important;
      font-weight: 500 !important;
      color: #1a365d !important;
      white-space: pre-wrap !important;
      ${interactive && context === 'preview' ? 'cursor: pointer !important;' : ''}
    }
    
    .report-html .template-isolated-content .editable-answer:hover {
      background: #e6faf5 !important;
      border-color: #00d395 !important;
    }
    
    .report-html .template-isolated-content .answer-content {
      font-weight: 500 !important;
      color: #1a365d !important;
    }
    
    .report-html .template-isolated-content .quote-superscript {
      font-size: 0.7em !important;
      vertical-align: super !important;
      color: #2196f3 !important;
      font-weight: bold !important;
      margin-left: 2px !important;
      ${interactive && context === 'preview' ? 'cursor: pointer !important;' : ''}
    }
    
    .report-html .template-isolated-content .quote-superscript:hover {
      background-color: #e3f2fd !important;
      border-radius: 3px !important;
      padding: 1px 2px !important;
    }

    /* Audit Trail Styles - Track Changes Visualization */
    .report-html .template-isolated-content .audit-trail-insert {
      background-color: #d1fae5 !important;
      border-bottom: 2px solid #10b981 !important;
      padding: 2px 4px !important;
      border-radius: 2px !important;
      font-weight: 500 !important;
    }

    .report-html .template-isolated-content .audit-trail-delete {
      background-color: #fee2e2 !important;
      text-decoration: line-through !important;
      text-decoration-color: #ef4444 !important;
      text-decoration-thickness: 2px !important;
      padding: 2px 4px !important;
      border-radius: 2px !important;
      color: #991b1b !important;
      font-weight: 500 !important;
    }

    .report-html .template-isolated-content .audit-trail-insert:hover,
    .report-html .template-isolated-content .audit-trail-delete:hover {
      cursor: help !important;
      opacity: 0.9 !important;
    }
  `;
  
  // Prefix custom CSS selectors to increase specificity over global styles
  const templateCss = customCss && customCss.trim() ? `
    /* Custom Template Styles (Prefixed for Isolation) */
    ${prefixCssSelectors(customCss, '.template-isolated-content')}
  ` : '';

  // Keep even legacy template CSS inside the report's paint and stacking
  // boundary. New templates are additionally constrained on the server.
  const isolationBoundary = `
    .report-html > .template-isolated-content {
      contain: layout paint style !important;
      isolation: isolate !important;
      position: relative !important;
      overflow: clip !important;
      max-width: 100% !important;
      box-sizing: border-box !important;
    }
  `;
  
  // Build final CSS with proper cascade order
  const finalCss = `
    ${isolationReset}
    ${templateCss}
    ${isolationBoundary}
    ${baseStyles}
  `;

  return finalCss;
};

export const generateReportHTML = (
  content: string,
  answers: { [placeholder: string]: ReportAnswer },
  config: ReportStyleConfig,
  questions: Question[] = []
): string => {
  let html = content;
  let quoteCounter = 1;
  const { context } = config;
  
  // Build question lookup map for answer_type metadata
  const questionMap = new Map<string, Question>();
  questions.forEach(q => questionMap.set(q.placeholder, q));
  
  Object.entries(answers).forEach(([placeholder, answer]) => {
    const placeholderPattern = `{{${placeholder}}}`;
    const question = questionMap.get(placeholder);
    
    let renderedAnswer: string;
    
    // Render based on type with proper parameters
    if (question?.answer_type === 'list') {
      // Update quote indexes for this answer
      const quotesWithIndex = answer.quotes.map(q => ({
        ...q,
        index: quoteCounter++
      }));
      renderedAnswer = renderListAnswer(answer.answer, quotesWithIndex, answer.id, context);
    } else if (question?.answer_type === 'table') {
      // Update quote indexes for this answer
      const quotesWithIndex = answer.quotes.map(q => ({
        ...q,
        index: quoteCounter++
      }));
      renderedAnswer = renderTableAnswer(answer.answer, question.columns || [], quotesWithIndex, answer.id, context);
    } else {
      // String type - render text and add superscripts separately
      renderedAnswer = escapeHtml(String(answer.answer));
      
      // Add superscripts for STRING type
      if (answer.quotes && answer.quotes.length > 0) {
        const quoteNumbers = answer.quotes.map(() => quoteCounter++);

        let superscripts = '';
        if (context === 'pdf') {
          superscripts = quoteNumbers.map(num => generateSuperscript(num)).join('');
        } else {
          superscripts = quoteNumbers.map(num =>
            `<sup class="quote-superscript" data-quote-index="${num - 1}">${generateSuperscript(num)}</sup>`
          ).join('');
        }
        
        renderedAnswer = `<span class="editable-answer" data-answer-id="${answer.id}">${renderedAnswer}${superscripts}</span>`;
      } else {
        renderedAnswer = `<span class="editable-answer" data-answer-id="${answer.id}">${renderedAnswer}</span>`;
      }
    }
    
    html = html.replace(new RegExp(placeholderPattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), renderedAnswer);
  });
  
  return html;
};

export const generatePopulatedHTML = (
  template: string,
  answers: { [placeholder: string]: ReportAnswer },
  questions: Question[] = [],
  customCss?: string
): string => {
  const config: ReportStyleConfig = { context: 'preview', interactive: true };
  const styles = getBaseReportStyles(config, customCss);
  const populatedHTML = generateReportHTML(template, answers, config, questions);

  // Wrap populated HTML in isolation container to prevent global style conflicts
  const wrappedHTML = `<div class="template-isolated-content">${populatedHTML}</div>`;

  const finalHTML = `<style>${styles}</style>${wrappedHTML}`;

  return finalHTML;
};
