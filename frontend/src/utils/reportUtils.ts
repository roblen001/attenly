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
  answer: any,
  quotes: any[] = [],
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
  answer: any,
  columns: ColumnDefinition[],
  quotes: any[] = [],
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
  answer: any,
  question?: Question
): string => {
  // Default to string if no question metadata or no answer_type specified
  if (!question || !question.answer_type || question.answer_type === 'string') {
    return escapeHtml(String(answer));
  }
  
  if (question.answer_type === 'list') {
    return renderListAnswer(answer);
  }
  
  if (question.answer_type === 'table') {
    return renderTableAnswer(answer, question.columns || []);
  }
  
  // Fallback to string
  return escapeHtml(String(answer));
};

export const getBaseReportStyles = (config: ReportStyleConfig): string => {
  const { context, interactive = true } = config;
  
  const baseStyles = `
    .editable-answer {
      position: relative;
      display: inline;
      background: #f7fafc;
      border: 1px solid transparent;
      border-radius: 2px;
      padding: 1px 3px;
      transition: all 0.2s ease;
      font-weight: 500;
      color: #1a365d;
      ${interactive && context === 'preview' ? 'cursor: pointer;' : ''}
    }
    
    .editable-answer:hover {
      background: #e6faf5 !important;
      border-color: #00d395 !important;
    }
    
    .answer-content {
      font-weight: 500;
      color: #1a365d;
    }
    
    .quote-superscript {
      font-size: 0.7em;
      vertical-align: super;
      color: #2196f3;
      font-weight: bold;
      margin-left: 2px;
      ${interactive && context === 'preview' ? 'cursor: pointer;' : ''}
    }
    
    .quote-superscript:hover {
      background-color: #e3f2fd;
      border-radius: 3px;
      padding: 1px 2px;
    }
  `;
  
  return baseStyles;
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
        
        renderedAnswer = `
          <span class="editable-answer" data-answer-id="${answer.id}">
            ${renderedAnswer}${superscripts}
          </span>
        `;
      } else {
        renderedAnswer = `
          <span class="editable-answer" data-answer-id="${answer.id}">
            ${renderedAnswer}
          </span>
        `;
      }
    }
    
    html = html.replace(new RegExp(placeholderPattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), renderedAnswer);
  });
  
  return html;
};

export const generatePopulatedHTML = (
  template: string,
  answers: { [placeholder: string]: ReportAnswer },
  questions: Question[] = []
): string => {
  const config: ReportStyleConfig = { context: 'preview', interactive: true };
  const styles = getBaseReportStyles(config);
  const populatedHTML = generateReportHTML(template, answers, config, questions);

  return `<style>${styles}</style>${populatedHTML}`;
};
