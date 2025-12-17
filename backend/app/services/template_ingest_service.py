"""
Template Ingest Service

AI-powered template normalization using Gemini 2.5 Pro:
- Converts uploaded templates (DOCX/PDF/HTML) into clean, structured HTML + CSS
- Uses Gemini 2.5 Pro for high-quality normalization
- Falls back to Mammoth for DOCX if Gemini fails
- Sanitizes HTML and CSS for security
- Returns blank template with default CSS as fallback
"""

import io
import json
import logging
import os
import re
import tempfile
from typing import Tuple, Optional, Set, Dict
import google.generativeai as genai
import mammoth
import nh3
import tinycss2
from bs4 import BeautifulSoup

from app.config import GEMINI_API_KEY, TEMPLATE_INGEST_MODEL_NAME
from app.constants.default_template_css import DEFAULT_TEMPLATE_CSS
from app.schemas import TemplateIngestResponse
from app.services.credit_service import get_credit_service

logger = logging.getLogger(__name__)


class TemplateIngestService:
    """Service for AI-powered template normalization"""
    
    # Gemini prompt for template normalization (from user specification)
    GEMINI_PROMPT = """You are an expert document template normalizer for Attenly, a legal/enterprise document automation platform.

You are given a single attached file TEMPLATE_FILE (DOCX, PDF, or HTML) that represents a report/template. Your job is to:

1. **Faithfully recreate the document’s structure** in HTML, as close as possible to the original (section order, nesting, tables, lists, and overall layout).
2. **Replace instance-specific content** (names, dates, numbers, addresses, IDs, client/matter-specific details) with neutral placeholders.
3. **Output syntactically correct HTML and CSS** that fit Attenly’s constrained schema.

Your output MUST be a single JSON object with exactly this shape and no extra keys:

{"html_body":"...","css":"..."}

Use double quotes for all keys and string values. Do NOT wrap the JSON in markdown, backticks, or add any explanations or text before or after it.

--------------------------------
ABSOLUTE REPRODUCTION RULES
--------------------------------

Your highest priority is **faithful reproduction of TEMPLATE_FILE**:

- **DO NOT INVENT OR ADD ANYTHING** that is not clearly present in the source.
  - Do NOT add new sections, headings, paragraphs, tables, lists, callouts, issues, disclaimers, or signature blocks that were not in TEMPLATE_FILE.
  - Do NOT merge, split, summarize, or reorder sections.
  - Do NOT “improve” the template, shorten it, or expand it.
- Preserve:
  - The **order of sections** and headings.
  - The **number and order of paragraphs, bullet points, numbered items, and table rows/columns**.
  - The **relative hierarchy** (e.g., main section vs. subsection) as closely as possible.
- You may normalize **only**:
  - Minor whitespace and line-break noise.
  - Obvious Word/PDF artifacts (e.g., unnecessary nested spans, inline styles) as long as the logical structure and content stay the same.

If something in the source is ambiguous, choose the interpretation that **changes the original structure the least** and never drop content.

--------------------------------
ALLOWED TRANSFORMATIONS
--------------------------------

You are allowed to change ONLY these things:

1. **HTML syntax / schema mapping**
   - Convert the original document into a single HTML fragment whose top-level element is:

     <div class="attenly-template report-wrapper"> ... </div>

   - Inside this fragment, use only these standard HTML tags:
     - `div, p, span, strong, em, h1, h2, h3, ul, ol, li, table, thead, tbody, tr, th, td, br, hr`
   - Only use the following CSS classes in `html_body` (no others unless absolutely unavoidable for faithful reproduction):
     - `report-wrapper` (outer container)
     - `report-header`
     - `firm-block`
     - `firm-name`
     - `firm-details`
     - `report-meta-title`
     - `report-title`
     - `report-subtitle`
     - `meta-table`
     - `section`
     - `section-title`
     - `section-body`
     - `callout`
     - `risk-level-high`
     - `risk-level-medium`
     - `risk-level-low`
     - `issues-table`
     - `signature-block`
     - `signature-row`
     - `signature`
     - `signature-line`
     - `signature-label`
   - **Only apply a class if there is a clear, corresponding element in TEMPLATE_FILE.**
     - Example: if there is no issues table in the source, do NOT create a `.issues-table`.

2. **Placeholders for instance-specific content**
   - Keep **all generic/legal boilerplate text, headings, and explanatory sentences exactly as in the source**.
   - Replace **only** concrete, document-specific values with neutral placeholders in square brackets.
     - Examples:
       - Company/firm names → `[FIRM NAME]`, `[COMPANY NAME]`
       - People’s names → `[PERSON NAME]`
       - Client/matter identifiers → `[CLIENT NAME]`, `[MATTER DESCRIPTION]`, `[FILE NUMBER]`
       - Addresses → `[Street Address]`, `[City]`, `[Province/State]`, `[Postal Code]`
       - Dates → `[YYYY-MM-DD]`
       - Numbers (account numbers, corporate numbers, share counts, invoice numbers) → `[NUMBER]` or more specific placeholders if obvious from context.
   - **Do NOT introduce new placeholders that correspond to sections or fields not present in the original.**
     - If the source has 3 issues, your output must have exactly 3 issue items (with their text replaced by placeholders where needed), not “Issue 1/2/3/4” etc.
   - Preserve punctuation and sentence structure while selectively swapping in placeholders:
     - Example: `HarbourTech Analytics Inc. was incorporated on March 15, 2016.` →
       `[COMPANY NAME] was incorporated on [YYYY-MM-DD].`

3. **CSS styling**
   - The `css` value must be a string containing only raw CSS rules (no `<style>` tags, no HTML).
   - It will be used as TinyMCE `content_style` / `content_css`.
   - It MUST style at minimum:
     - `body`
     - `.report-wrapper`
     - `.report-header`
     - `.firm-block`
     - `.firm-name`
     - `.firm-details`
     - `.report-meta-title`
     - `.report-title`
     - `.report-subtitle`
     - `.meta-table`, `.meta-table th`, `.meta-table td`
     - `.section`, `.section-title`, `.section-body`
     - `.callout`
     - `.risk-level-high`, `.risk-level-medium`, `.risk-level-low`
     - `.issues-table`, `.issues-table th`, `.issues-table td`
     - `.signature-block`, `.signature-row`, `.signature`, `.signature-line`, `.signature-label`
   - Assume:
     - White background
     - Dark text
     - `font-family: "Calibri", Arial, sans-serif;`
     - Base font size around 11pt
     - Subtle borders, spacing, and backgrounds suitable for a professional legal/business report.
   - Do NOT use:
     - `@import`
     - External URLs
     - `expression()` or any JavaScript-related features.

--------------------------------
SECTION / ISSUE HANDLING
--------------------------------

- **Headings and sections**
  - Use the section headings from TEMPLATE_FILE **as they appear**, except for very minor case/punctuation normalization (e.g., `executive summary` → `Executive Summary`).
  - Do NOT introduce example headings like “Executive Summary”, “Background”, “Issues Identified”, “Legal Analysis”, “Conclusions & Recommendations”, or “Documents Reviewed” unless there is a clear, matching heading in the source.
  - If a section appears in the source, it must appear in the output in the same order.

- **Issues / findings / tables**
  - If TEMPLATE_FILE has issues/findings listed as bullets, numbered lists, or table rows, preserve:
    - The number of items
    - Their order
    - Whether they are in a list or a table
  - Replace only the specific content of each issue with placeholders as needed, but:
    - Do NOT create new issues
    - Do NOT merge or split issues
    - Do NOT add generic example issues

--------------------------------
HTML_BODY REQUIREMENTS
--------------------------------

In `html_body`:

- Output a single HTML fragment (no `<!DOCTYPE>`, `<html>`, `<head>`, `<body>`, `<style>`, `<script>`, `<iframe>`, or JavaScript).
- The top-level element MUST be:

  <div class="attenly-template report-wrapper"> ... </div>

- Use simple, editable structure with minimal nesting, because a human will edit it in TinyMCE.
- Do NOT include HTML comments.
- Ensure all tags are properly closed and nesting is valid.

--------------------------------
CSS REQUIREMENTS
--------------------------------

In `css`:

- Only raw CSS rules (no `<style>` tags).
- Target the selectors listed above.
- Use neutral, professional, readable styling appropriate for a legal/business report.
- **CRITICAL - Page Margins**: Do NOT add margins or padding to:
  - `body` (use `margin: 0; padding: 0;`)
  - `.report-wrapper` (use `margin: 0; padding: 0;`)
  - Page margins are handled separately by PDF generation using @page rule
  - Only use internal spacing (margin/padding) on section elements INSIDE the wrapper

--------------------------------
FALLBACK BEHAVIOUR
--------------------------------

If you cannot produce a reasonable template because:
- the file is unstructured,
- mostly images,
- or does not resemble a reusable template at all,

then return exactly:

{"html_body":"","css":""}

and nothing else.

--------------------------------
FINAL OUTPUT FORMAT
--------------------------------

Finally, output only the JSON object:

{"html_body":"...","css":"..."}

- Ensure it is valid JSON.
- Properly escape any double quotes and newlines inside the strings.
- Do NOT add any other keys.
- Do NOT add any text before or after the JSON.
"""
    
    def __init__(self):
        """Initialize with Gemini 2.5 Pro client"""
        if not GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not configured. Template ingestion will fail.")
        
        genai.configure(api_key=GEMINI_API_KEY)
        self.model_name = TEMPLATE_INGEST_MODEL_NAME
        logger.info(f"TemplateIngestService initialized with model: {self.model_name}")
    
    def process_template_file(
        self,
        content: bytes,
        filename: str,
        user_id: Optional[str] = None
    ) -> TemplateIngestResponse:
        """
        Main orchestrator for template processing

        Args:
            content: File content as bytes
            filename: Original filename
            user_id: Optional user ID for credit tracking

        Returns:
            TemplateIngestResponse with HTML, CSS, and metadata
        """
        warnings = []
        file_type = self._detect_file_type(filename)

        logger.info(f"Processing template: {filename} (type: {file_type})")

        try:
            # Try Gemini normalization first
            html_body, css = self._normalize_with_gemini(content, file_type, filename, user_id)
            
            if html_body and css:
                # Success with Gemini
                logger.info(f"Successfully processed template with Gemini: {filename}")
                return TemplateIngestResponse(
                    success=True,
                    html_body=html_body,
                    css=css,
                    source="gemini",
                    warnings=warnings
                )
            else:
                # Gemini returned empty - try fallback for DOCX
                if file_type == 'docx':
                    logger.warning(f"Gemini returned empty for {filename}, trying Mammoth fallback")
                    warnings.append("AI normalization returned empty, using basic DOCX conversion")
                    html_body = self._fallback_to_mammoth(content)
                    
                    if html_body:
                        return TemplateIngestResponse(
                            success=True,
                            html_body=html_body,
                            css=DEFAULT_TEMPLATE_CSS,
                            source="mammoth",
                            warnings=warnings
                        )
                
                # No valid output - return blank template
                logger.warning(f"Could not process template {filename}, returning blank template")
                warnings.append("Template could not be processed, using blank template")
                html_body, css = self._create_blank_template()
                return TemplateIngestResponse(
                    success=True,
                    html_body=html_body,
                    css=css,
                    source="blank",
                    warnings=warnings
                )
                
        except Exception as e:
            logger.error(f"Error processing template {filename}: {str(e)}", exc_info=True)
            
            # Try Mammoth fallback for DOCX
            if file_type == 'docx':
                try:
                    logger.info(f"Attempting Mammoth fallback after error for {filename}")
                    warnings.append(f"AI normalization failed: {str(e)}. Using basic DOCX conversion.")
                    html_body = self._fallback_to_mammoth(content)
                    
                    if html_body:
                        return TemplateIngestResponse(
                            success=True,
                            html_body=html_body,
                            css=DEFAULT_TEMPLATE_CSS,
                            source="mammoth",
                            warnings=warnings
                        )
                except Exception as fallback_error:
                    logger.error(f"Mammoth fallback also failed: {str(fallback_error)}")
            
            # Return error response
            return TemplateIngestResponse(
                success=False,
                html_body="",
                css="",
                source="error",
                error=f"Failed to process template: {str(e)}",
                warnings=warnings
            )
    
    def _detect_file_type(self, filename: str) -> str:
        """Detect file type from filename"""
        filename_lower = filename.lower()
        if filename_lower.endswith('.pdf'):
            return 'pdf'
        elif filename_lower.endswith('.docx'):
            return 'docx'
        elif filename_lower.endswith('.html') or filename_lower.endswith('.htm'):
            return 'html'
        else:
            return 'unknown'
    
    def _normalize_with_gemini(
        self,
        file_content: bytes,
        file_type: str,
        filename: str,
        user_id: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Call Gemini 2.5 Pro with strict prompt, return (html_body, css)

        Args:
            file_content: File content as bytes
            file_type: Type of file ('pdf', 'docx', 'html')
            filename: Original filename
            user_id: Optional user ID for credit tracking

        Returns:
            Tuple of (html_body, css) - empty strings if failed
        """
        temp_file_path = None
        try:
            model = genai.GenerativeModel(self.model_name)
            
            # Gemini's upload_file() requires a file path, not BytesIO
            # Write content to temporary file
            logger.info(f"Writing file content to temporary file: {filename}")
            
            # Determine file extension for temp file
            file_extensions = {
                'pdf': '.pdf',
                'docx': '.docx',
                'html': '.html'
            }
            file_ext = file_extensions.get(file_type, '.tmp')
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='wb', suffix=file_ext, delete=False) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
            
            logger.info("Temporary file created for Gemini processing")
            
            # Determine MIME type
            mime_types = {
                'pdf': 'application/pdf',
                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'html': 'text/html'
            }
            mime_type = mime_types.get(file_type, 'application/octet-stream')
            
            # Upload file to Gemini using file path
            logger.info(f"Uploading file to Gemini: {filename}")
            uploaded_file = genai.upload_file(
                temp_file_path,
                mime_type=mime_type
            )
            
            # Generate content with prompt
            logger.info(f"Calling Gemini {self.model_name} for template normalization")
            response = model.generate_content([self.GEMINI_PROMPT, uploaded_file])

            # Track credit usage if user_id provided
            if user_id and hasattr(response, 'usage_metadata') and response.usage_metadata:
                try:
                    credit_service = get_credit_service()
                    input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
                    output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0

                    cost_cad = credit_service.calculate_cost(self.model_name, input_tokens, output_tokens)

                    credit_service.consume_credits_sync(
                        user_id=user_id,
                        cost_cad=cost_cad,
                        operation_type="llm_template",
                        model=self.model_name,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        metadata={"filename": filename, "file_type": file_type}
                    )

                    logger.info(f"Template credit usage: {cost_cad:.6f} CAD ({input_tokens} in, {output_tokens} out)")
                except Exception as e:
                    logger.warning(f"Failed to track template credits: {e}")

            # Parse response
            response_text = response.text.strip()
            logger.debug(f"Gemini response: {response_text[:500]}...")
            
            # Try to parse JSON
            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                # Extract content between ```json and ``` or ``` and ```
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if match:
                    response_text = match.group(1)
                else:
                    # Try without code blocks
                    response_text = response_text.replace('```json', '').replace('```', '').strip()
            
            # Parse JSON
            result = json.loads(response_text)
            
            # Extract html_body and css
            html_body = result.get('html_body', '')
            css = result.get('css', '')
            
            # Validate and sanitize
            if html_body and css:
                html_body = self._sanitize_html(html_body)
                css = self._sanitize_css(css)
                logger.info("Successfully normalized template with Gemini")
                return html_body, css
            else:
                logger.warning("Gemini returned empty html_body or css")
                return '', ''
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini JSON response: {str(e)}")
            return '', ''
        except Exception as e:
            logger.error(f"Gemini normalization failed: {str(e)}", exc_info=True)
            return '', ''
        finally:
            # Clean up temporary file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    logger.debug("Temporary file deleted")
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file: {str(e)}")
    
    def _fallback_to_mammoth(self, docx_content: bytes) -> str:
        """
        DOCX fallback processing, returns HTML only (no CSS)
        
        Args:
            docx_content: DOCX file content
            
        Returns:
            HTML string (empty if failed)
        """
        try:
            logger.info("Using Mammoth for DOCX conversion")
            result = mammoth.convert_to_html(io.BytesIO(docx_content))
            html = result.value
            
            # Wrap in standard template structure
            wrapped_html = f'<div class="attenly-template report-wrapper">{html}</div>'
            
            # Sanitize
            sanitized = self._sanitize_html(wrapped_html)
            
            logger.info("Successfully converted DOCX with Mammoth")
            return sanitized
            
        except Exception as e:
            logger.error(f"Mammoth conversion failed: {str(e)}")
            return ''
    
    def _create_blank_template(self) -> Tuple[str, str]:
        """
        Return blank HTML template + default CSS
        
        Returns:
            Tuple of (html_body, css)
        """
        html_body = '''<div class="attenly-template report-wrapper">
  <div class="report-header">
    <div class="firm-block">
      <div class="firm-name">[FIRM NAME]</div>
      <div class="firm-details">[Street Address, City, Province, Postal Code]</div>
    </div>
    <div class="report-meta-title">Professional Report</div>
    <h1 class="report-title">[Report Title]</h1>
    <div class="report-subtitle">[Report Subtitle or Matter Description]</div>
  </div>
  
  <table class="meta-table">
    <tr>
      <th>Client</th>
      <td>[Client Name]</td>
    </tr>
    <tr>
      <th>Matter</th>
      <td>[Matter Description]</td>
    </tr>
    <tr>
      <th>Date</th>
      <td>[YYYY-MM-DD]</td>
    </tr>
  </table>
  
  <div class="section">
    <h2 class="section-title">Executive Summary</h2>
    <div class="section-body">
      <p>[Brief overview of the matter and key findings.]</p>
    </div>
  </div>
  
  <div class="section">
    <h2 class="section-title">Background</h2>
    <div class="section-body">
      <p>[Contextual information about the matter.]</p>
    </div>
  </div>
  
  <div class="section">
    <h2 class="section-title">Analysis</h2>
    <div class="section-body">
      <p>[Detailed analysis and findings.]</p>
    </div>
  </div>
  
  <div class="section">
    <h2 class="section-title">Recommendations</h2>
    <div class="section-body">
      <p>[Actionable recommendations based on analysis.]</p>
    </div>
  </div>
  
  <div class="signature-block">
    <div class="signature-row">
      <div class="signature">
        <div class="signature-line"></div>
        <div class="signature-label">[Name]<br/>[Title]</div>
      </div>
    </div>
  </div>
</div>'''
        
        return html_body, DEFAULT_TEMPLATE_CSS
    
    # Allowlist of safe HTML tags for template content
    ALLOWED_HTML_TAGS: Set[str] = {
        # Structure
        'div', 'span', 'p', 'br', 'hr',
        # Headings
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        # Text formatting
        'strong', 'em', 'b', 'i', 'u', 's', 'sub', 'sup', 'mark',
        # Lists
        'ul', 'ol', 'li',
        # Tables
        'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'colgroup', 'col',
        # Links and media
        'a', 'img',
        # Semantic
        'header', 'footer', 'section', 'article', 'aside', 'nav', 'main',
        # Other
        'blockquote', 'pre', 'code', 'address',
    }

    # Allowlist of safe HTML attributes per tag
    # Note: 'rel' is NOT included for 'a' tags because we use link_rel parameter
    # in nh3.clean() which automatically adds rel="noopener noreferrer"
    ALLOWED_HTML_ATTRIBUTES: Dict[str, Set[str]] = {
        '*': {'class', 'id', 'style', 'title', 'lang', 'dir'},
        'a': {'href', 'target'},  # rel is handled by link_rel parameter
        'img': {'src', 'alt', 'width', 'height', 'loading'},
        'table': {'border', 'cellpadding', 'cellspacing', 'width'},
        'th': {'colspan', 'rowspan', 'scope', 'width'},
        'td': {'colspan', 'rowspan', 'width', 'height'},
        'col': {'span', 'width'},
        'colgroup': {'span'},
        'ol': {'start', 'type', 'reversed'},
        'li': {'value'},
    }

    def _sanitize_html(self, html: str) -> str:
        """
        Security validation for HTML output using nh3 allowlist approach.

        Uses strict allowlist of tags and attributes to prevent XSS attacks.
        Blocks dangerous URL schemes (javascript:, vbscript:, data:).
        Fails closed - returns empty string on error.

        Args:
            html: HTML string to sanitize

        Returns:
            Sanitized HTML string, or empty string on error
        """
        if not html or not html.strip():
            return ""

        try:
            # nh3 uses a different attribute format - convert our format
            # nh3 expects: {"*": {"class", "id"}, "a": {"href"}, ...}
            sanitized = nh3.clean(
                html,
                tags=self.ALLOWED_HTML_TAGS,
                attributes=self.ALLOWED_HTML_ATTRIBUTES,
                link_rel="noopener noreferrer",  # Add rel to all links for security
                url_schemes={'http', 'https', 'mailto'},  # Block javascript:, vbscript:, data:
            )

            return sanitized

        except Exception as e:
            logger.error(f"HTML sanitization failed: {str(e)}")
            # Fail closed - return empty string, not original HTML
            return ""
    
    # Dangerous at-rules that should be blocked
    BLOCKED_CSS_AT_RULES: Set[str] = {'import', 'charset', 'namespace'}

    # Safe at-rules that are allowed
    ALLOWED_CSS_AT_RULES: Set[str] = {'media', 'page', 'font-face', 'keyframes', '-webkit-keyframes', 'supports'}

    # Dangerous CSS properties (case-insensitive)
    BLOCKED_CSS_PROPERTIES: Set[str] = {'behavior', '-moz-binding', 'expression'}

    # Dangerous value patterns (compiled regex for performance)
    BLOCKED_CSS_VALUE_PATTERNS = [
        re.compile(r'javascript\s*:', re.IGNORECASE),
        re.compile(r'vbscript\s*:', re.IGNORECASE),
        re.compile(r'expression\s*\(', re.IGNORECASE),
    ]

    def _normalize_css_unicode_escapes(self, text: str) -> str:
        """
        Normalize CSS unicode escapes to actual characters.
        Prevents bypass attacks like \\6a\\61\\76\\61 = "java"

        Args:
            text: CSS text that may contain unicode escapes

        Returns:
            Text with unicode escapes converted to characters
        """
        def replace_escape(match):
            hex_str = match.group(1)
            try:
                return chr(int(hex_str, 16))
            except (ValueError, OverflowError):
                return ''

        # CSS unicode escape: backslash + 1-6 hex digits + optional whitespace
        return re.sub(r'\\([0-9a-fA-F]{1,6})\s?', replace_escape, text)

    def _css_value_is_safe(self, value: str) -> bool:
        """
        Check if a CSS value is safe (no dangerous patterns).

        Args:
            value: CSS property value to check

        Returns:
            True if safe, False if dangerous
        """
        # Normalize unicode escapes before checking
        normalized = self._normalize_css_unicode_escapes(value)
        # Also remove CSS comments which could be used for bypass
        normalized = re.sub(r'/\*.*?\*/', '', normalized, flags=re.DOTALL)
        # Remove whitespace variations
        normalized_compact = re.sub(r'\s+', '', normalized)

        for pattern in self.BLOCKED_CSS_VALUE_PATTERNS:
            if pattern.search(normalized) or pattern.search(normalized_compact):
                return False

        return True

    def _sanitize_css(self, css: str) -> str:
        """
        Security validation for CSS output using tinycss2 parser.

        Uses parser-based approach to properly handle:
        - Unicode escape bypasses (\\6a\\61\\76\\61 = "java")
        - CSS comment bypasses (java/**/script:)
        - Whitespace variations

        Fails closed - returns empty string on error.

        Args:
            css: CSS string to sanitize

        Returns:
            Sanitized CSS string, or empty string on error
        """
        if not css or not css.strip():
            return ""

        try:
            # Parse CSS using tinycss2
            rules = tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)

            safe_rules = []
            for rule in rules:
                sanitized_rule = self._sanitize_css_rule(rule)
                if sanitized_rule:
                    safe_rules.append(sanitized_rule)

            return '\n'.join(safe_rules)

        except Exception as e:
            logger.error(f"CSS sanitization failed: {str(e)}")
            # Fail closed - return empty string, not original CSS
            return ""

    def _sanitize_css_rule(self, rule) -> Optional[str]:
        """
        Sanitize an individual CSS rule.

        Args:
            rule: tinycss2 rule object

        Returns:
            Serialized safe CSS rule, or None if blocked
        """
        if rule.type == 'error':
            # Skip parse errors
            return None

        elif rule.type == 'at-rule':
            at_keyword = rule.at_keyword.lower()

            # Block dangerous at-rules
            if at_keyword in self.BLOCKED_CSS_AT_RULES:
                logger.warning(f"Blocked dangerous CSS at-rule: @{at_keyword}")
                return None

            # Allow safe at-rules
            if at_keyword in self.ALLOWED_CSS_AT_RULES:
                return tinycss2.serialize([rule])

            # Block unknown at-rules for safety
            logger.warning(f"Blocked unknown CSS at-rule: @{at_keyword}")
            return None

        elif rule.type == 'qualified-rule':
            # This is a regular CSS rule (selector { declarations })
            return self._sanitize_css_qualified_rule(rule)

        return None

    def _sanitize_css_qualified_rule(self, rule) -> Optional[str]:
        """
        Sanitize a qualified CSS rule (selector { properties }).

        Args:
            rule: tinycss2 qualified rule object

        Returns:
            Serialized safe CSS rule, or None if all properties blocked
        """
        try:
            # Serialize selector
            selector = tinycss2.serialize(rule.prelude).strip()

            # Parse and filter declarations
            declarations = tinycss2.parse_declaration_list(rule.content)
            safe_declarations = []

            for decl in declarations:
                if decl.type == 'declaration':
                    prop_name = decl.name.lower()

                    # Skip blocked properties
                    if prop_name in self.BLOCKED_CSS_PROPERTIES:
                        logger.warning(f"Blocked dangerous CSS property: {prop_name}")
                        continue

                    # Serialize and check value
                    value = tinycss2.serialize(decl.value).strip()

                    # Check for dangerous patterns in value
                    if self._css_value_is_safe(value):
                        important = ' !important' if decl.important else ''
                        safe_declarations.append(f"  {decl.name}: {value}{important};")
                    else:
                        logger.warning(f"Blocked dangerous CSS value in property {prop_name}")

            if safe_declarations:
                return f"{selector} {{\n" + "\n".join(safe_declarations) + "\n}"

            return None

        except Exception as e:
            logger.warning(f"Error sanitizing CSS rule: {str(e)}")
            return None
