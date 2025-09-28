import type { Quote } from '../types';

export interface PageSection {
  pageNumber: number;
  content: string;
  startPosition: number;
  endPosition: number;
}

// Extended Quote interface to include new precise quote extraction fields
export interface ExtendedQuote extends Quote {
  exact_text?: string;
  precise_page?: number;
}

// Common stop words to filter out
export const STOP_WORDS = new Set([
  'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'an', 'a',
  'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
  'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can',
  'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her',
  'us', 'them', 'my', 'your', 'his', 'its', 'our', 'their', 'what', 'which', 'who', 'when', 'where', 'why', 'how'
]);

export interface TextMatchResult {
  index: number;
  length: number;
  isExactMatch: boolean;
}

// Priority-based text matching with exact match first
export const findTextMatch = (
  fullText: string,
  searchText: string,
  pageSections: PageSection[],
  currentQuote: Quote
): TextMatchResult | null => {
  // Strategy 1: Exact match anywhere in document (HIGHEST PRIORITY)
  const exactIndex = fullText.indexOf(searchText);
  if (exactIndex !== -1) {
    console.log('Found exact match for:', searchText);
    return { index: exactIndex, length: searchText.length, isExactMatch: true };
  }

  // Strategy 2: Page-aware exact match (within specified page)
  const pageExactMatch = findPageAwareExactMatch(fullText, searchText, pageSections, currentQuote);
  if (pageExactMatch) {
    console.log('Found page-aware exact match for:', searchText);
    return { ...pageExactMatch, isExactMatch: true };
  }

  // Strategy 3: Word sequence match (only if exact fails)
  const wordMatch = findWordSequenceMatch(fullText, searchText);
  if (wordMatch) {
    console.log('Found word sequence match for:', searchText);
    return { ...wordMatch, isExactMatch: false };
  }

  // Strategy 4: Multi-word combination (last resort)
  const multiWordMatch = findMultiWordCombination(fullText, searchText);
  if (multiWordMatch) {
    console.log('Found multi-word combination match for:', searchText);
    return { ...multiWordMatch, isExactMatch: false };
  }

  console.warn('No match found for:', searchText);
  return null;
};

// Find exact match within the specified page
export const findPageAwareExactMatch = (
  fullText: string,
  searchText: string,
  pageSections: PageSection[],
  currentQuote: Quote
): { index: number; length: number } | null => {
  const extendedQuote = currentQuote as ExtendedQuote;
  let targetPage = extendedQuote.precise_page;

  if (!targetPage) {
    const pageRangeMatch = currentQuote.page_range.match(/(\d+)/);
    if (pageRangeMatch) {
      targetPage = parseInt(pageRangeMatch[1]);
    }
  }

  if (!targetPage) return null;

  // Find the page section
  const targetSection = pageSections.find(section => section.pageNumber === targetPage);
  if (!targetSection) return null;

  // Extract text from the target page
  const pageText = fullText.substring(targetSection.startPosition, targetSection.endPosition);

  // Look for exact match within this page
  const pageIndex = pageText.indexOf(searchText);
  if (pageIndex !== -1) {
    // Convert page-relative index to document-relative index
    return {
      index: targetSection.startPosition + pageIndex,
      length: searchText.length
    };
  }

  return null;
};

// Find word sequence allowing for spacing differences
export const findWordSequenceMatch = (
  fullText: string,
  searchText: string
): { index: number; length: number } | null => {
  const searchWords = searchText.trim().split(/\s+/).filter(word => word.length > 0);
  if (searchWords.length === 0) return null;

  // Create a regex pattern that allows flexible whitespace between words
  const regexPattern = searchWords
    .map(word => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) // Escape special regex chars
    .join('\\s+'); // Allow one or more whitespace characters between words

  const regex = new RegExp(regexPattern, 'gi');
  const match = regex.exec(fullText);

  if (match) {
    return { index: match.index, length: match[0].length };
  }

  return null;
};

// Find multi-word combinations (2-3 words together)
export const findMultiWordCombination = (
  fullText: string,
  searchText: string
): { index: number; length: number } | null => {
  const words = searchText.trim().split(/\s+/).filter(word =>
    word.length > 2 && !STOP_WORDS.has(word.toLowerCase())
  );

  if (words.length < 2) return null;

  // Try 3-word combinations first
  if (words.length >= 3) {
    for (let i = 0; i <= words.length - 3; i++) {
      const combination = words.slice(i, i + 3).join('\\s+');
      const regex = new RegExp(combination, 'gi');
      const match = regex.exec(fullText);
      if (match) {
        return { index: match.index, length: match[0].length };
      }
    }
  }

  // Try 2-word combinations
  for (let i = 0; i <= words.length - 2; i++) {
    const combination = words.slice(i, i + 2).join('\\s+');
    const regex = new RegExp(combination, 'gi');
    const match = regex.exec(fullText);
    if (match) {
      return { index: match.index, length: match[0].length };
    }
  }

  return null;
};
