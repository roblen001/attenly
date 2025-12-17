// EditorStep.tsx
import React, { useRef, useState, useMemo, useEffect } from 'react';
import { Editor } from '@tinymce/tinymce-react';
import type { Question, Quote } from '../../types';
import AITestingModal from './AITestingModal';
import './EditorStep.css';

interface EditorStepProps {
  reportTemplate: string;
  reportTemplateCss?: string;
  initialTemplateHtml?: string;
  questions: Question[];
  onTemplateChange: (template: string) => void;
  onTemplateCssChange?: (css: string) => void;
  onQuestionsChange: (questions: Question[]) => void;
  onBack: () => void;
  onNext: () => void;
}

// TinyMCE Configuration Constants
const EDITOR_HEIGHT = 500;
const BOOKMARK_TYPE = 2;
const BOOKMARK_NORMALIZED = true;

const TINYMCE_PLUGINS = [
  'advlist', 'autolink', 'lists', 'link', 'image', 'charmap', 'preview',
  'anchor', 'searchreplace', 'visualblocks', 'code', 'fullscreen',
  'insertdatetime', 'media', 'table', 'help', 'wordcount', 'paste',
  'textcolor', 'colorpicker', 'hr', 'pagebreak', 'nonbreaking',
  'template', 'save', 'directionality', 'visualchars', 'emoticons',
  'noneditable'
];

const TINYMCE_TOOLBAR = [
  'undo redo | blocks fontfamily fontsize | bold italic underline strikethrough | alignleft aligncenter alignright alignjustify',
  'outdent indent | numlist bullist | forecolor backcolor removeformat | pagebreak | charmap emoticons | fullscreen preview save print',
  'insertfile image media template link anchor codesample | ltr rtl'
].join(' | ');

const EXTENDED_VALID_ELEMENTS =
  "a[class|data-question-id|href|role|tabindex|aria-label|contenteditable],sup[class|data-quote-index],div[class|data-mce-type]";

/**
 * Convert <!-- pagebreak --> HTML comments to visible div elements for TinyMCE editing.
 * TinyMCE strips HTML comments by default, so we convert them to visible elements.
 */
const convertPagebreakCommentsToElements = (html: string): string => {
  return html.replace(
    /<!--\s*pagebreak\s*-->/gi,
    '<div class="mce-pagebreak" data-mce-type="pagebreak">&nbsp;</div>'
  );
};

/**
 * Convert mce-pagebreak div elements back to <!-- pagebreak --> HTML comments for storage.
 * This ensures the stored format matches TinyMCE's default pagebreak output.
 */
const convertPagebreakElementsToComments = (html: string): string => {
  return html.replace(
    /<div[^>]*class="[^"]*mce-pagebreak[^"]*"[^>]*>.*?<\/div>/gi,
    '<!-- pagebreak -->'
  );
};

const EDITOR_CONTENT_STYLE = `
  body { 
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
                 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue',
                 sans-serif; 
    font-size: 14px; 
    line-height: 1.6;
  }
  a.ai-placeholder {
    background-color: #e3f2fd;
    border: 2px dashed #2196f3;
    padding: 4px 8px;
    border-radius: 4px;
    color: #1976d2;
    font-weight: 500;
    cursor: pointer;
    text-decoration: none;
  }
  a.ai-placeholder:hover {
    background-color: #bbdefb;
  }
  a.ai-placeholder:focus {
    outline: 2px solid #888;
    outline-offset: 2px;
  }
  a.ai-locked {
    user-select: none;
  }
  /* Page break styling - visible in editor */
  .mce-pagebreak {
    display: block;
    border: 0;
    border-top: 1px dashed #666;
    margin: 15px 0;
    padding: 0;
    height: 1px;
    cursor: default;
    page-break-after: always;
  }
  .mce-pagebreak::before {
    content: 'Page Break';
    display: block;
    text-align: center;
    font-size: 10px;
    color: #666;
    background: #f5f5f5;
    padding: 2px 8px;
    margin: -10px auto 0;
    width: fit-content;
    border-radius: 3px;
  }
`;

const DEFAULT_TEMPLATE = {
  title: 'Basic Report Template',
  description: 'A simple report template to get started',
  content: `
    <h1>{{Report Title}}</h1>
    <h2>Executive Summary</h2>
    <p>{{Executive Summary}}</p>
    
    <h2>Key Findings</h2>
    <ul>
      <li>{{Key Finding 1}}</li>
      <li>{{Key Finding 2}}</li>
      <li>{{Key Finding 3}}</li>
    </ul>
    
    <h2>Detailed Analysis</h2>
    <p>{{Detailed Analysis}}</p>
    
    <h2>Recommendations</h2>
    <p>{{Recommendations}}</p>
  `
};

const EditorStep: React.FC<EditorStepProps> = ({
  reportTemplate,
  reportTemplateCss = '',
  initialTemplateHtml,
  questions,
  onTemplateChange,
  onTemplateCssChange,
  onQuestionsChange,
  onBack,
  onNext
}) => {
  const editorRef = useRef<any>(null);
  const [isAIModalOpen, setIsAIModalOpen] = useState(false);
  const [editingQuestion, setEditingQuestion] = useState<Question | null>(null);
  const [isCssEditorOpen, setIsCssEditorOpen] = useState(false);
  const [localCss, setLocalCss] = useState(reportTemplateCss);

  // Refs to fix stale closure issue in TinyMCE event handlers
  const questionsRef = useRef(questions);
  const setEditingQuestionRef = useRef(setEditingQuestion);
  const setIsAIModalOpenRef = useRef(setIsAIModalOpen);

  // Update local CSS when prop changes
  useEffect(() => {
    setLocalCss(reportTemplateCss);
  }, [reportTemplateCss]);

  // Keep refs updated with current values
  useEffect(() => {
    questionsRef.current = questions;
  }, [questions]);

  useEffect(() => {
    setEditingQuestionRef.current = setEditingQuestion;
  }, [setEditingQuestion]);

  useEffect(() => {
    setIsAIModalOpenRef.current = setIsAIModalOpen;
  }, [setIsAIModalOpen]);

  // Keep a local ref to the latest html
  const latestHtmlRef = useRef(reportTemplate);

  // Bookmark ref to preserve cursor position when opening modals
  const bookmarkRef = useRef<any>(null);

  useEffect(() => {
    latestHtmlRef.current = reportTemplate;
  }, [reportTemplate]);

  const rememberCaret = () => {
    const editor = editorRef.current;
    if (editor && editor.initialized) {
      bookmarkRef.current = editor.selection.getBookmark(
        BOOKMARK_TYPE,
        BOOKMARK_NORMALIZED
      );
    }
  };

  const handleAddAIAbility = () => {
    rememberCaret(); // Save cursor position before opening modal
    setEditingQuestion(null);
    setIsAIModalOpen(true);
  };

  const handleEditQuestion = (question: Question) => {
    rememberCaret(); // Save cursor position before opening modal
    setEditingQuestion(question);
    setIsAIModalOpen(true);
  };

  const escapeHtml = (text: string) => {
    return text.replace(/[&<>"']/g, (c) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    }[c]!));
  };

  const safeEditorAction = (action: () => void) => {
    const editor = editorRef.current;
    if (editor && editor.initialized) {
      const selection = editor.selection.getRng();
      try {
        action();
        editor.selection.setRng(selection);
      } catch (e) {
        // Selection restore failed, run action without restore
        action();
      }
    }
  };

  const handleAddToTemplate = (
    questionText: string,
    answer: string,
    quotes: Quote[]
  ) => {
    const currentQuestions = questionsRef.current;
    const editing = editingQuestion;

    const placeholder = `{{${questionText}}}`;
    const references =
      quotes.length > 0 ? ` [${quotes.map((_, i) => i + 1).join('][')}]` : '';

    if (editing && currentQuestions.some((q) => q.id === editing.id)) {
      // Update existing question
      const updatedQuestions = currentQuestions.map((q) =>
        q.id === editing.id
          ? { ...q, prompt: questionText, exampleAnswer: answer, exampleQuotes: quotes }
          : q
      );
      onQuestionsChange(updatedQuestions);

      // Update the placeholder in the editor
      safeEditorAction(() => {
        const editor = editorRef.current;
        const content = editor.getContent();
        const newHtml = `<a href="#" class="ai-placeholder mceNonEditable ai-locked" data-question-id="${
          editing.id
        }" role="button" tabindex="0" contenteditable="false">${escapeHtml(
          placeholder
        )}${references}</a>`;

        const updatedContent = content.replace(
          new RegExp(`<a[^>]*data-question-id="${editing.id}"[^>]*>.*?</a>`, 'g'),
          newHtml
        );
        editor.setContent(updatedContent);
      });
    } else {
      // Add new question
      const questionId = `q_${Date.now()}_${Math.random()
        .toString(36)
        .substr(2, 9)}`;

      safeEditorAction(() => {
        const editor = editorRef.current;

        if (bookmarkRef.current) {
          editor.focus();
          try {
            editor.selection.moveToBookmark(bookmarkRef.current);
          } catch {
            // Bookmark restore failed, continue without it
          }
        }

        const html = `<a href="#" class="ai-placeholder mceNonEditable ai-locked" data-question-id="${questionId}" role="button" tabindex="0" contenteditable="false">${escapeHtml(
          placeholder
        )}${references}</a>&nbsp;`;
        editor.insertContent(html);

        const node = editor.dom.select(
          `a[data-question-id="${questionId}"]`
        )[0];
        if (node) {
          editor.selection.select(node);
          editor.selection.collapse(false);
        }

        bookmarkRef.current = null;
      });

      const newQuestion: Question = {
        id: questionId,
        placeholder,
        prompt: questionText,
        exampleAnswer: answer,
        exampleQuotes: quotes
      };

      const newQuestionsList = [...currentQuestions, newQuestion];
      onQuestionsChange(newQuestionsList);
    }
  };

  const handleAIModalClose = () => {
    setIsAIModalOpen(false);
    setEditingQuestion(null);
  };

  const editorConfig = useMemo(
    () => ({
      height: EDITOR_HEIGHT,
      menubar: true,
      plugins: TINYMCE_PLUGINS,
      toolbar: TINYMCE_TOOLBAR,
      extended_valid_elements: EXTENDED_VALID_ELEMENTS,
      noneditable_class: 'ai-locked',
      // 🔧 KEY FIX: merge base editor CSS + template CSS
      content_style: `
        ${EDITOR_CONTENT_STYLE}
        ${reportTemplateCss || ''}
      `,
      setup: (editor: any) => {
        const getAnchorIds = () => {
          const ed = editorRef.current;
          if (!ed) return [];
          const anchors = ed.dom.select('a.ai-placeholder');
          return anchors.map((n: any) => ed.dom.getAttrib(n, 'data-question-id'));
        };

        const syncQuestionsWithDom = () => {
          const ed = editorRef.current;
          if (!ed) return;

          const anchorIds = getAnchorIds();
          const currLen = questionsRef.current.length;

          // Guard: only prune when we have at least one question and at least one anchor
          if (currLen === 0 || anchorIds.length === 0) {
            return;
          }

          const idsInDom = new Set(anchorIds);
          const newList = questionsRef.current.filter((q) =>
            idsInDom.has(q.id)
          );
          if (newList.length !== questionsRef.current.length) {
            onQuestionsChange(newList);
          }
        };

        const handlePlaceholderClick = (e: any) => {
          const node = e.target as Element;
          const placeholder = editor.dom.getParent(node, 'a.ai-placeholder');
          const isActivateKey =
            e.type === 'keydown' && (e.key === 'Enter' || e.key === ' ');

          if (placeholder && (e.type === 'click' || isActivateKey)) {
            e.preventDefault();
            const questionId = editor.dom.getAttrib(
              placeholder,
              'data-question-id'
            );
            const question = questionsRef.current.find(
              (q) => q.id === questionId
            );
            if (question) {
              setEditingQuestionRef.current(question);
              setIsAIModalOpenRef.current(true);
            }
          }
        };

        const handleKeydown = (e: any) => {
          // Activate if Enter/Space on anchor
          handlePlaceholderClick(e);

          if (e.key !== 'Backspace' && e.key !== 'Delete') return;
          const ed = editorRef.current;
          const node = ed.selection.getNode();
          const anchor = ed.dom.getParent(node, 'a.ai-placeholder');
          if (anchor) {
            e.preventDefault();
            const id = ed.dom.getAttrib(anchor, 'data-question-id');

            const next = anchor.nextSibling;
            if (
              next &&
              next.nodeType === 3 &&
              /\u00A0|\s/.test(next.nodeValue || '')
            ) {
              next.parentNode?.removeChild(next);
            }
            ed.dom.remove(anchor);

            const newList = questionsRef.current.filter((q) => q.id !== id);
            onQuestionsChange(newList);
          }
        };

        const handleInput = () => {
          // Convert pagebreak elements back to comments for storage
          const rawHtml = editor.getContent({ format: 'html' });
          latestHtmlRef.current = convertPagebreakElementsToComments(rawHtml);
        };

        const handleBlur = () => {
          // Ensure pagebreaks are converted to comments before saving
          const rawHtml = editor.getContent({ format: 'html' });
          const htmlWithComments = convertPagebreakElementsToComments(rawHtml);
          latestHtmlRef.current = htmlWithComments;
          onTemplateChange(htmlWithComments);
        };

        editor.on('click', handlePlaceholderClick);
        editor.on('keydown', handleKeydown);
        editor.on('input', syncQuestionsWithDom);
        editor.on('keyup', (e: any) => {
          if (e.key === 'Backspace' || e.key === 'Delete') syncQuestionsWithDom();
        });
        editor.on('Remove', syncQuestionsWithDom);
        editor.on('input', handleInput);
        editor.on('blur', handleBlur);

        editor.on('remove', () => {
          editor.off('click', handlePlaceholderClick);
          editor.off('keydown', handleKeydown);
          editor.off('input', syncQuestionsWithDom);
          editor.off('keyup', syncQuestionsWithDom);
          editor.off('Remove', syncQuestionsWithDom);
          editor.off('input', handleInput);
          editor.off('blur', handleBlur);
        });
      },
      paste_data_images: true,
      image_advtab: true,
      importcss_append: true,
      file_picker_types: 'image',
      file_picker_callback: (callback: any, value: any, meta: any) => {
        if (meta.filetype === 'image') {
          const input = document.createElement('input');
          input.setAttribute('type', 'file');
          input.setAttribute('accept', 'image/*');
          input.addEventListener('change', (e: Event) => {
            const target = e.target as HTMLInputElement;
            const file = target.files?.[0];
            if (file) {
              const reader = new FileReader();
              reader.addEventListener('load', () => {
                callback(reader.result as string, { alt: file.name });
              });
              reader.readAsDataURL(file);
            }
          });
          input.click();
        }
      },
      templates: [DEFAULT_TEMPLATE]
    }),
    [reportTemplateCss, onQuestionsChange, onTemplateChange]
  );

  return (
    <div className="editor-step">
      <div className="editor-header">
        <h2>Create Report Template</h2>
        <p>
          Design your report template using the rich text editor. Use the
          &quot;🤖 Add AI Ability&quot; button to insert data extraction
          points. Note: your questions should be general enough so they work on
          other files too.
        </p>

        <button
          className="add-ai-ability-btn"
          onMouseDown={(e) => e.preventDefault()} // keep focus in TinyMCE
          onClick={handleAddAIAbility}
        >
          🤖 Add AI Ability
        </button>
      </div>

      <div className="editor-container">
        <Editor
          apiKey={import.meta.env.VITE_TINYMCE_API_KEY}
          id="attenly-editor"
          onInit={(evt, editor) => {
            editorRef.current = editor;
            // Priority: reportTemplate (existing/edited) > initialTemplateHtml (from DOCX) > empty
            const contentToLoad = reportTemplate || initialTemplateHtml || '';
            if (contentToLoad) {
              // Convert pagebreak comments to visible elements before loading into editor
              const contentWithVisiblePagebreaks = convertPagebreakCommentsToElements(contentToLoad);
              editor.setContent(contentWithVisiblePagebreaks);
            }
          }}
          initialValue={convertPagebreakCommentsToElements(reportTemplate || initialTemplateHtml || '')}
          init={editorConfig}
        />
      </div>

      {/* Advanced CSS Editor (Collapsible) */}
      {onTemplateCssChange && (
        <div className="css-editor-section">
          <button
            className="css-editor-toggle"
            onClick={() => setIsCssEditorOpen(!isCssEditorOpen)}
            type="button"
          >
            <span className="toggle-icon">
              {isCssEditorOpen ? '▼' : '▶'}
            </span>
            Advanced CSS (for power users)
          </button>

          {isCssEditorOpen && (
            <div className="css-editor-content">
              <p className="css-editor-hint">
                Customize the styling of your template. Changes apply to PDF
                generation.
              </p>
              <textarea
                className="css-editor-textarea"
                value={localCss}
                onChange={(e) => setLocalCss(e.target.value)}
                onBlur={() => onTemplateCssChange(localCss)}
                placeholder="/* Add custom CSS here... */"
                spellCheck={false}
                rows={10}
              />
            </div>
          )}
        </div>
      )}

      <div className="editor-actions">
        <button className="btn-secondary" onClick={onBack}>
          Back
        </button>
        <button
          className="btn-primary"
          disabled={questions.length === 0}
          onClick={() => {
            const ed = editorRef.current;
            const rawHtml = ed
              ? ed.getContent({ format: 'html' })
              : latestHtmlRef.current;
            // Convert pagebreak elements back to comments for storage
            const html = convertPagebreakElementsToComments(rawHtml);
            if (html !== reportTemplate) {
              onTemplateChange(html);
            }
            onNext();
          }}
        >
          Finalize
        </button>
      </div>

      {/* AI Testing Modal */}
      <AITestingModal
        isOpen={isAIModalOpen}
        onClose={handleAIModalClose}
        onAddToTemplate={handleAddToTemplate}
        agentId="test-agent"
        existingQuestion={editingQuestion?.prompt}
        existingAnswer={editingQuestion?.exampleAnswer}
        existingQuotes={editingQuestion?.exampleQuotes}
      />
    </div>
  );
};

export default EditorStep;
