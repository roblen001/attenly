/**
 * Agent Transform Utilities
 * 
 * Transforms custom agent data from TinyMCE editor format to prebuilt agent format
 * for consistent processing and rendering.
 */

interface QuestionOut {
  id: string;
  placeholder: string;
  prompt: string;
}

interface TransformResult {
  cleanTemplate: string;
  cleanQuestions: QuestionOut[];
}

/**
 * Generate a clean placeholder name from question text
 */
function generatePlaceholderName(questionText: string): string {
  return questionText
    // Remove question words and common prefixes
    .replace(/^(what is|what are|who is|where is|when is|how much|how many|extract|provide|list|identify)\s+/i, '')
    
    // Remove articles and prepositions
    .replace(/\b(the|a|an|of|for|in|on|at|by|with|from|to)\b/gi, ' ')
    
    // Remove question marks and punctuation
    .replace(/[?!.,;:]/g, '')
    
    // Split into words and filter out empty/short words
    .split(/\s+/)
    .filter(word => word.length > 2)
    
    // Convert to PascalCase
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join('')
    
    // Ensure it starts with a letter and is valid
    .replace(/^[^a-zA-Z]/, 'Field')
    
    // Limit length
    .substring(0, 30);
}

/**
 * Ensure placeholder name is unique
 */
function ensureUniquePlaceholder(baseName: string, existingPlaceholders: string[]): string {
  let uniqueName = baseName;
  let counter = 1;
  
  while (existingPlaceholders.includes(uniqueName)) {
    uniqueName = `${baseName}${counter}`;
    counter++;
  }
  
  return uniqueName;
}

/**
 * Generate fallback placeholder name
 */
function fallbackPlaceholder(index: number): string {
  return `CustomField${index + 1}`;
}

/**
 * Transform custom agent data to match prebuilt agent format
 */
export function transformCustomAgentData(reportTemplate: string, questions: QuestionOut[]): TransformResult {
  const placeholderMap = new Map<string, string>();
  const existingPlaceholders: string[] = [];
  
  // Generate clean placeholders for each question
  questions.forEach((question, index) => {
    const questionText = question.prompt;
    let cleanPlaceholder = generatePlaceholderName(questionText);
    
    // Ensure uniqueness
    cleanPlaceholder = ensureUniquePlaceholder(cleanPlaceholder, existingPlaceholders);
    
    // Fallback if still invalid
    if (!cleanPlaceholder || cleanPlaceholder.length < 3) {
      cleanPlaceholder = fallbackPlaceholder(index);
    }
    
    placeholderMap.set(question.id, cleanPlaceholder);
    existingPlaceholders.push(cleanPlaceholder);
  });
  
  // Transform template: replace anchor tags with simple placeholders
  let cleanTemplate = reportTemplate;
  questions.forEach(question => {
    const cleanPlaceholder = placeholderMap.get(question.id);
    if (cleanPlaceholder) {
      // Match anchor tags with the specific question ID
      const anchorRegex = new RegExp(
        `<a[^>]*data-question-id="${escapeRegex(question.id)}"[^>]*>.*?</a>`, 
        'g'
      );
      cleanTemplate = cleanTemplate.replace(anchorRegex, `{{${cleanPlaceholder}}}`);
    }
  });
  
  // Transform questions: update placeholder names
  const cleanQuestions: QuestionOut[] = questions.map(question => ({
    id: question.id,
    placeholder: placeholderMap.get(question.id) || question.placeholder,
    prompt: question.prompt
  }));
  
  return {
    cleanTemplate,
    cleanQuestions
  };
}

/**
 * Escape special regex characters
 */
function escapeRegex(string: string): string {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Add professional styling to custom agent templates
 */
export function addProfessionalStyling(template: string): string {
  // Check if template already has DOCTYPE and html structure
  if (template.includes('<!DOCTYPE') || template.includes('<html')) {
    return template;
  }
  
  // Add professional styling wrapper
  const styledTemplate = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Custom Report</title>
  <style>
    /* Page setup */
    @page { size: A4; margin: 1in; }
    body {
      font-family: 'Calibri', 'Arial', sans-serif;
      font-size: 11pt;
      color: #333;
      line-height: 1.4;
      margin: 0;
      padding: 20px;
    }
    
    /* Headers */
    h1 {
      font-size: 18pt;
      color: #1a365d;
      padding-bottom: 8px;
      margin-bottom: 20px;
    }
    
    h2 {
      font-size: 14pt;
      color: #2d3748;
      margin-top: 24px;
      margin-bottom: 12px;
    }
    
    h3 {
      font-size: 12pt;
      color: #4a5568;
      margin-top: 18px;
      margin-bottom: 8px;
    }
    
    /* Paragraphs */
    p {
      margin-bottom: 12px;
    }
    
    /* Lists */
    ul, ol {
      margin-bottom: 12px;
      padding-left: 24px;
    }
    
    li {
      margin-bottom: 4px;
    }
    
    /* Tables */
    table {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 16px;
      font-size: 10pt;
    }
    
    th, td {
      border: 1px solid #cbd5e0;
      padding: 8px 12px;
      text-align: left;
    }
    
    th {
      background-color: #f7fafc;
      font-weight: bold;
      color: #2d3748;
    }
    
    /* Professional spacing */
    .section {
      margin-bottom: 24px;
    }
    
    /* Print styles */
    @media print {
      body { margin: 0; padding: 0.5in; }
      h1 { page-break-after: avoid; }
      h2, h3 { page-break-after: avoid; }
      table { page-break-inside: avoid; }
    }
  </style>
</head>
<body>
  ${template}
</body>
</html>`;

  return styledTemplate;
}
