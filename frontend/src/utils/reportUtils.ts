import type { ReportAnswer } from '../types';

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
  config: ReportStyleConfig
): string => {
  let html = content;
  let quoteCounter = 1;
  const { context } = config;
  
  Object.entries(answers).forEach(([placeholder, answer]) => {
    const placeholderPattern = `{{${placeholder}}}`;
    
    // Generate superscripts for quotes
    let superscripts = '';
    if (answer.quotes && answer.quotes.length > 0) {
      const quoteNumbers = answer.quotes.map(() => quoteCounter++);
      
      if (context === 'pdf') {
        superscripts = quoteNumbers.map(num => generateSuperscript(num)).join('');
      } else {
        superscripts = quoteNumbers.map(num => 
          `<sup class="quote-superscript" data-quote-index="${num - 1}">${generateSuperscript(num)}</sup>`
        ).join('');
      }
    }
    
    let answerHTML;
    if (context === 'pdf') {
      answerHTML = `${answer.answer}${superscripts}`;
    } else {
      answerHTML = `
        <span class="editable-answer" data-answer-id="${answer.id}">
          <span class="answer-content">${answer.answer}</span>${superscripts}
        </span>
      `;
    }
    
    html = html.replace(new RegExp(placeholderPattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), answerHTML);
  });
  
  return html;
};

export const generatePopulatedHTML = (
  template: string,
  answers: { [placeholder: string]: ReportAnswer }
): string => {
  const config: ReportStyleConfig = { context: 'preview', interactive: true };
  const styles = getBaseReportStyles(config);
  const populatedHTML = generateReportHTML(template, answers, config);

  return `<style>${styles}</style>${populatedHTML}`;
};
