"""
Template Ingest Service

Provider-aware template normalization:
- Gemini handles high-quality multimodal template normalization.
- OpenAI-compatible mode sends the original uploaded file to a multimodal model
  through the configured OpenAI-compatible file-input API.
- Basic mode handles simple DOCX/HTML conversion without AI.
- Disabled mode lets local/enterprise deployments avoid a hard Gemini dependency.
- Sanitizes HTML and CSS for security.
- Returns blank template with default CSS as fallback when AI cannot normalize.
"""

import base64
import io
import json
import logging
import os
import re
import tempfile
from typing import Tuple, Optional, Set, Dict

from app.config import (
    GEMINI_API_KEY,
    OPENAI_COMPATIBLE_API_KEY,
    OPENAI_COMPATIBLE_BASE_URL,
    OPENAI_COMPATIBLE_TIMEOUT_SECONDS,
    TEMPLATE_INGEST_MODEL_NAME,
    TEMPLATE_INGEST_PROVIDER,
)
from app.constants.default_template_css import DEFAULT_TEMPLATE_CSS
from app.schemas import TemplateIngestResponse

logger = logging.getLogger(__name__)


class TemplateIngestService:
    """Service for provider-aware template normalization."""
    
    # Prompt for high-capability multimodal template normalization.
    NORMALIZATION_PROMPT = """You are an expert document template normalizer for Attenly, a legal/enterprise document automation platform.

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
   - **Page breaks**: If the source document contains page breaks, preserve them using the exact HTML comment format: `<!-- pagebreak -->`
     - This is TinyMCE's standard pagebreak format
     - Do NOT use `<div class="page-break">`, `<hr>`, or any other format
     - Place the `<!-- pagebreak -->` comment on its own line where the page break should occur
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

    RENDERED_IMAGE_PROMPT_SUFFIX = """

--------------------------------
RENDERED PAGE IMAGE INPUT
--------------------------------

You are receiving rendered page images from TEMPLATE_FILE because this endpoint
accepts vision inputs rather than native file inputs. Treat the images as the
source of truth. Preserve visual order, layout, headings, lists, tables, page
breaks, and placeholders as faithfully as possible.
"""
    
    def __init__(self):
        """Initialize the configured template ingest provider."""
        self.provider = TEMPLATE_INGEST_PROVIDER
        self.model_name = TEMPLATE_INGEST_MODEL_NAME

        if self.provider == "gemini" and not GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not configured. Gemini template ingestion will fail.")
        if self.provider == "openai_compatible" and not OPENAI_COMPATIBLE_BASE_URL:
            logger.warning(
                "OPENAI_COMPATIBLE_BASE_URL not configured. OpenAI-compatible template ingestion will fail."
            )

        logger.info(
            "TemplateIngestService initialized with provider=%s model=%s",
            self.provider,
            self.model_name if self.provider in {"gemini", "openai_compatible"} else "n/a",
        )
    
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

        logger.info(
            "Processing template: %s (type=%s provider=%s)",
            filename,
            file_type,
            self.provider,
        )

        if self.provider == "disabled":
            return self._disabled_response()

        if self.provider == "basic":
            return self._process_with_basic_converter(content, file_type, filename, warnings)

        if self.provider == "openai_compatible":
            return self._process_with_openai_compatible(content, file_type, filename, user_id, warnings)

        if self.provider != "gemini":
            return TemplateIngestResponse(
                success=False,
                html_body="",
                css="",
                source="error",
                error=(
                    f"Template ingest provider '{self.provider}' is not supported by this runtime. "
                    "Use 'gemini', 'openai_compatible', 'basic', or 'disabled'."
                ),
                warnings=warnings,
            )

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
                    return self._process_with_basic_converter(content, file_type, filename, warnings)
                
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
                    return self._process_with_basic_converter(content, file_type, filename, warnings)
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

    def _disabled_response(self) -> TemplateIngestResponse:
        return TemplateIngestResponse(
            success=False,
            html_body="",
            css="",
            source="disabled",
            error=(
                "Template upload ingestion is disabled by server configuration. "
                "Build templates directly in the editor, set TEMPLATE_INGEST_PROVIDER=basic "
                "for simple DOCX/HTML conversion, or configure a high-capability multimodal "
                "template ingest provider."
            ),
            warnings=[],
        )

    def _process_with_basic_converter(
        self,
        content: bytes,
        file_type: str,
        filename: str,
        warnings: list[str],
    ) -> TemplateIngestResponse:
        """Process simple templates without AI."""
        if file_type == "docx":
            html_body = self._fallback_to_mammoth(content)
            if html_body:
                return TemplateIngestResponse(
                    success=True,
                    html_body=html_body,
                    css=DEFAULT_TEMPLATE_CSS,
                    source="mammoth",
                    warnings=warnings,
                )

            return TemplateIngestResponse(
                success=False,
                html_body="",
                css="",
                source="error",
                error="Basic DOCX template conversion failed.",
                warnings=warnings,
            )

        if file_type == "html":
            html_body = self._fallback_to_html(content)
            if html_body:
                return TemplateIngestResponse(
                    success=True,
                    html_body=html_body,
                    css=DEFAULT_TEMPLATE_CSS,
                    source="html",
                    warnings=warnings,
                )

            return TemplateIngestResponse(
                success=False,
                html_body="",
                css="",
                source="error",
                error="Basic HTML template conversion failed.",
                warnings=warnings,
            )

        return TemplateIngestResponse(
            success=False,
            html_body="",
            css="",
            source="error",
            error=(
                f"Basic template ingestion cannot process '{filename}'. "
                "PDF and layout-heavy template ingestion requires a high-capability "
                "multimodal model provider."
            ),
            warnings=warnings,
        )

    def _normalize_with_openai_compatible(
        self,
        file_content: bytes,
        file_type: str,
        filename: str,
        user_id: Optional[str],
        warnings: list[str],
    ) -> Tuple[str, str]:
        """Normalize the uploaded file through OpenAI-compatible multimodal inputs."""
        if not OPENAI_COMPATIBLE_BASE_URL:
            raise ValueError("OPENAI_COMPATIBLE_BASE_URL is required for template ingestion")

        attempts = [
            (
                "Responses file input",
                lambda: self._normalize_with_openai_responses_file(file_content, file_type, filename),
            ),
            (
                "Chat Completions file input",
                lambda: self._normalize_with_openai_chat_file(file_content, file_type, filename),
            ),
            (
                "Chat Completions image input",
                lambda: self._normalize_with_openai_chat_images(file_content, file_type, filename, warnings),
            ),
        ]

        rejected_shapes = []
        for name, attempt in attempts:
            try:
                return attempt()
            except Exception as exc:
                if not self._is_openai_request_shape_rejection(exc):
                    raise
                rejected_shapes.append(f"{name}: {exc}")
                logger.info("OpenAI-compatible template input shape rejected: %s", name)

        raise ValueError(
            "The configured OpenAI-compatible template ingest endpoint rejected all "
            "supported multimodal request shapes. Tried original file input through "
            "Responses, original file input through Chat Completions, and rendered "
            f"page images through Chat Completions. Details: {'; '.join(rejected_shapes)}"
        )

    def _normalize_with_openai_responses_file(
        self,
        file_content: bytes,
        file_type: str,
        filename: str,
    ) -> Tuple[str, str]:
        """Send the original uploaded file through the OpenAI Responses file-input shape."""
        payload = {
            "model": self.model_name,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "filename": filename,
                            "file_data": self._file_data_url(file_content, file_type),
                        },
                        {
                            "type": "input_text",
                            "text": self.NORMALIZATION_PROMPT,
                        },
                    ],
                }
            ],
            "temperature": 0,
        }

        data = self._post_openai_compatible_json("/responses", payload)
        response_text = self._extract_responses_text(data)
        return self._parse_template_json(response_text)

    def _normalize_with_openai_chat_images(
        self,
        file_content: bytes,
        file_type: str,
        filename: str,
        warnings: list[str],
    ) -> Tuple[str, str]:
        """Render pages to images for OpenAI-compatible vision chat endpoints."""
        image_urls = self._render_file_to_image_data_urls(file_content, file_type, filename, warnings)
        content_parts = [
            {
                "type": "text",
                "text": (
                    f"{self.NORMALIZATION_PROMPT}\n"
                    f"{self.RENDERED_IMAGE_PROMPT_SUFFIX}\n\n"
                    f"Filename: {filename}\nDetected file type: {file_type}"
                ),
            }
        ]
        content_parts.extend(
            {
                "type": "image_url",
                "image_url": {
                    "url": image_url,
                    "detail": "high",
                },
            }
            for image_url in image_urls
        )

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": content_parts}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        response_text, usage = self._call_openai_compatible_chat(payload)
        logger.info(
            "OpenAI-compatible chat-image template ingest usage for %s: prompt=%s completion=%s",
            filename,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )
        return self._parse_template_json(response_text)

    def _normalize_with_openai_chat_file(
        self,
        file_content: bytes,
        file_type: str,
        filename: str,
    ) -> Tuple[str, str]:
        """Send the original uploaded file through Chat Completions file content parts."""
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "file",
                            "file": {
                                "filename": filename,
                                "file_data": self._file_data_url(file_content, file_type),
                            },
                        },
                        {
                            "type": "text",
                            "text": self.NORMALIZATION_PROMPT,
                        },
                    ],
                }
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        response_text, usage = self._call_openai_compatible_chat(payload)
        logger.info(
            "OpenAI-compatible chat-file template ingest usage for %s: prompt=%s completion=%s",
            filename,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )
        return self._parse_template_json(response_text)

    def _parse_template_json(self, response_text: str) -> Tuple[str, str]:
        result = json.loads(self._clean_json_response(response_text))
        html_body = result.get("html_body", "")
        css = result.get("css", "")

        if html_body and css:
            html_body = self._sanitize_html(html_body)
            css = self._sanitize_css(css)
            logger.info("Successfully normalized template with OpenAI-compatible provider")
            return html_body, css

        return "", ""

    def _render_file_to_image_data_urls(
        self,
        file_content: bytes,
        file_type: str,
        filename: str,
        warnings: list[str],
    ) -> list[str]:
        """Render supported template uploads into page images for vision-only gateways."""
        if file_type == "pdf":
            return self._render_pdf_to_image_data_urls(file_content, filename)

        if file_type == "html":
            warnings.append(
                "HTML template upload is being rendered to page images for the configured "
                "vision model. Native file-input mode usually preserves source structure better."
            )
            pdf_content = self._html_to_pdf(file_content.decode("utf-8", errors="ignore"))
            return self._render_pdf_to_image_data_urls(pdf_content, filename)

        if file_type == "docx":
            warnings.append(
                "DOCX template upload is being converted to HTML and rendered to page images "
                "for the configured vision model. Native file-input mode usually preserves DOCX "
                "structure better."
            )
            html = self._docx_to_html(file_content)
            pdf_content = self._html_to_pdf(html)
            return self._render_pdf_to_image_data_urls(pdf_content, filename)

        raise ValueError(f"Unsupported template file type for OpenAI-compatible image input: {file_type}")

    def _docx_to_html(self, docx_content: bytes) -> str:
        try:
            import mammoth

            result = mammoth.convert_to_html(io.BytesIO(docx_content))
            html = result.value.strip()
            if not html:
                raise ValueError("DOCX conversion produced empty HTML")
            return html
        except Exception as exc:
            raise ValueError(f"Failed to render DOCX template for vision input: {exc}") from exc

    def _html_to_pdf(self, html: str) -> bytes:
        try:
            from weasyprint import HTML

            return HTML(string=html).write_pdf()
        except Exception as exc:
            raise ValueError(f"Failed to render HTML template for vision input: {exc}") from exc

    def _render_pdf_to_image_data_urls(self, pdf_content: bytes, filename: str) -> list[str]:
        try:
            import fitz

            doc = fitz.open(stream=pdf_content, filetype="pdf")
            try:
                image_urls: list[str] = []
                for page_index, page in enumerate(doc, start=1):
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    png_bytes = pixmap.tobytes("png")
                    encoded = base64.b64encode(png_bytes).decode("ascii")
                    image_urls.append(f"data:image/png;base64,{encoded}")
                    if page_index >= 5:
                        break
                if not image_urls:
                    raise ValueError("PDF did not contain renderable pages")
                return image_urls
            finally:
                doc.close()
        except Exception as exc:
            raise ValueError(f"Failed to render {filename} for vision input: {exc}") from exc

    def _mime_type_for_file_type(self, file_type: str) -> str:
        mime_types = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "html": "text/html",
        }
        return mime_types.get(file_type, "application/octet-stream")

    def _file_data_url(self, file_content: bytes, file_type: str) -> str:
        encoded = base64.b64encode(file_content).decode("ascii")
        return f"data:{self._mime_type_for_file_type(file_type)};base64,{encoded}"

    def _openai_compatible_url(self, path: str) -> str:
        base_url = OPENAI_COMPATIBLE_BASE_URL.rstrip("/")
        for suffix in ("/chat/completions", "/responses"):
            if base_url.endswith(suffix):
                base_url = base_url[: -len(suffix)]
                break
        return f"{base_url}{path}"

    def _openai_compatible_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if OPENAI_COMPATIBLE_API_KEY:
            headers["Authorization"] = f"Bearer {OPENAI_COMPATIBLE_API_KEY}"
        return headers

    def _post_openai_compatible_json(self, path: str, payload: dict) -> dict:
        import httpx

        with httpx.Client(timeout=OPENAI_COMPATIBLE_TIMEOUT_SECONDS) as client:
            response = client.post(
                self._openai_compatible_url(path),
                headers=self._openai_compatible_headers(),
                json=payload,
            )
            response.raise_for_status()

        return response.json()

    def _call_openai_compatible_chat(self, payload: dict) -> Tuple[str, Dict[str, int]]:
        import httpx

        with httpx.Client(timeout=OPENAI_COMPATIBLE_TIMEOUT_SECONDS) as client:
            response = client.post(
                self._openai_compatible_url("/chat/completions"),
                headers=self._openai_compatible_headers(),
                json=payload,
            )

            if response.status_code in {400, 422}:
                logger.info(
                    "OpenAI-compatible template provider rejected response_format; retrying without it"
                )
                fallback_payload = dict(payload)
                fallback_payload.pop("response_format", None)
                response = client.post(
                    self._openai_compatible_url("/chat/completions"),
                    headers=self._openai_compatible_headers(),
                    json=fallback_payload,
                )

            response.raise_for_status()

        data = response.json()
        usage = data.get("usage") or {}
        return self._extract_chat_text(data), {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
        }

    def _extract_chat_text(self, data: dict) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("OpenAI-compatible chat response did not include choices")

        message = choices[0].get("message", {})
        content = message.get("content") or choices[0].get("text") or ""
        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                if isinstance(part, dict)
                else str(part)
                for part in content
            )
        if not content:
            raise ValueError("OpenAI-compatible template response did not include content")

        return str(content)

    def _extract_responses_text(self, data: dict) -> str:
        output_text = data.get("output_text")
        if output_text:
            return str(output_text)

        text_parts: list[str] = []
        for item in data.get("output") or []:
            if not isinstance(item, dict):
                continue
            content = item.get("content") or []
            if isinstance(content, dict):
                content = [content]
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict) and part.get("text"):
                    text_parts.append(str(part["text"]))

        if text_parts:
            return "".join(text_parts)
        if data.get("choices"):
            return self._extract_chat_text(data)

        raise ValueError("OpenAI-compatible Responses result did not include output text")

    def _is_openai_request_shape_rejection(self, exc: Exception) -> bool:
        """Return true when an endpoint rejects one multimodal request shape."""
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        return status_code in {400, 404, 405, 415, 422}

    def _clean_json_response(self, response_text: str) -> str:
        response_text = response_text.strip()
        if response_text.startswith("```"):
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
            if match:
                return match.group(1)
            response_text = response_text.replace("```json", "").replace("```", "").strip()
        return response_text

    def _process_with_openai_compatible(
        self,
        content: bytes,
        file_type: str,
        filename: str,
        user_id: Optional[str],
        warnings: list[str],
    ) -> TemplateIngestResponse:
        try:
            html_body, css = self._normalize_with_openai_compatible(
                content,
                file_type,
                filename,
                user_id,
                warnings,
            )

            if html_body and css:
                return TemplateIngestResponse(
                    success=True,
                    html_body=html_body,
                    css=css,
                    source="openai_compatible",
                    warnings=warnings,
                )

            return TemplateIngestResponse(
                success=False,
                html_body="",
                css="",
                source="error",
                error=(
                    "OpenAI-compatible template normalization returned empty output. "
                    "Use a stronger multimodal template-ingest model or simplify the template."
                ),
                warnings=warnings,
            )
        except Exception as exc:
            logger.error("OpenAI-compatible template ingestion failed: %s", exc, exc_info=True)
            return TemplateIngestResponse(
                success=False,
                html_body="",
                css="",
                source="error",
                error=(
                    f"OpenAI-compatible template ingestion failed: {exc}. "
                    "Configure a multimodal OpenAI-compatible model endpoint for smart template ingestion, "
                    "or set TEMPLATE_INGEST_PROVIDER=basic for simple DOCX/HTML conversion."
                ),
                warnings=warnings,
            )
    
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
            import google.generativeai as genai

            genai.configure(api_key=GEMINI_API_KEY)
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
            response = model.generate_content([self.NORMALIZATION_PROMPT, uploaded_file])

            # Track credit usage if user_id provided
            if user_id and hasattr(response, 'usage_metadata') and response.usage_metadata:
                try:
                    from app.services.credit_service import get_credit_service

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
            import mammoth

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

    def _fallback_to_html(self, html_content: bytes) -> str:
        """
        Basic HTML fallback processing, returns sanitized HTML only.

        Args:
            html_content: Raw HTML file content

        Returns:
            Sanitized HTML fragment wrapped in the standard template container
        """
        try:
            from bs4 import BeautifulSoup

            logger.info("Using basic HTML template conversion")
            html = html_content.decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")

            for element in soup(["script", "style", "iframe", "object", "embed"]):
                element.decompose()

            source = soup.body if soup.body else soup
            body_html = "".join(str(child) for child in source.contents).strip()

            if not body_html:
                return ""

            if "attenly-template" not in body_html:
                body_html = f'<div class="attenly-template report-wrapper">{body_html}</div>'

            sanitized = self._sanitize_html(body_html)
            logger.info("Successfully converted HTML with basic sanitizer")
            return sanitized

        except Exception as e:
            logger.error(f"Basic HTML conversion failed: {str(e)}")
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

    # Placeholder for preserving pagebreak comments during sanitization
    PAGEBREAK_PLACEHOLDER = '___ATTENLY_PAGEBREAK_PLACEHOLDER___'

    def _sanitize_html(self, html: str) -> str:
        """
        Security validation for HTML output using nh3 allowlist approach.

        Uses strict allowlist of tags and attributes to prevent XSS attacks.
        Blocks dangerous URL schemes (javascript:, vbscript:, data:).
        Preserves TinyMCE pagebreak comments (<!-- pagebreak -->).
        Fails closed - returns empty string on error.

        Args:
            html: HTML string to sanitize

        Returns:
            Sanitized HTML string, or empty string on error
        """
        if not html or not html.strip():
            return ""

        try:
            import nh3

            # Preserve pagebreak comments before sanitization (nh3 strips comments)
            # Use case-insensitive replacement for variations
            preserved = re.sub(
                r'<!--\s*pagebreak\s*-->',
                self.PAGEBREAK_PLACEHOLDER,
                html,
                flags=re.IGNORECASE
            )

            # nh3 uses a different attribute format - convert our format
            # nh3 expects: {"*": {"class", "id"}, "a": {"href"}, ...}
            sanitized = nh3.clean(
                preserved,
                tags=self.ALLOWED_HTML_TAGS,
                attributes=self.ALLOWED_HTML_ATTRIBUTES,
                link_rel="noopener noreferrer",  # Add rel to all links for security
                url_schemes={'http', 'https', 'mailto'},  # Block javascript:, vbscript:, data:
            )

            # Restore pagebreak comments after sanitization
            sanitized = sanitized.replace(self.PAGEBREAK_PLACEHOLDER, '<!-- pagebreak -->')

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
            import tinycss2

            # Parse CSS using tinycss2
            rules = tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)

            safe_rules = []
            for rule in rules:
                sanitized_rule = self._sanitize_css_rule(rule, tinycss2)
                if sanitized_rule:
                    safe_rules.append(sanitized_rule)

            return '\n'.join(safe_rules)

        except Exception as e:
            logger.error(f"CSS sanitization failed: {str(e)}")
            # Fail closed - return empty string, not original CSS
            return ""

    def _sanitize_css_rule(self, rule, tinycss2_module) -> Optional[str]:
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
                return tinycss2_module.serialize([rule])

            # Block unknown at-rules for safety
            logger.warning(f"Blocked unknown CSS at-rule: @{at_keyword}")
            return None

        elif rule.type == 'qualified-rule':
            # This is a regular CSS rule (selector { declarations })
            return self._sanitize_css_qualified_rule(rule, tinycss2_module)

        return None

    def _sanitize_css_qualified_rule(self, rule, tinycss2_module) -> Optional[str]:
        """
        Sanitize a qualified CSS rule (selector { properties }).

        Args:
            rule: tinycss2 qualified rule object

        Returns:
            Serialized safe CSS rule, or None if all properties blocked
        """
        try:
            # Serialize selector
            selector = tinycss2_module.serialize(rule.prelude).strip()

            # Parse and filter declarations
            declarations = tinycss2_module.parse_declaration_list(rule.content)
            safe_declarations = []

            for decl in declarations:
                if decl.type == 'declaration':
                    prop_name = decl.name.lower()

                    # Skip blocked properties
                    if prop_name in self.BLOCKED_CSS_PROPERTIES:
                        logger.warning(f"Blocked dangerous CSS property: {prop_name}")
                        continue

                    # Serialize and check value
                    value = tinycss2_module.serialize(decl.value).strip()

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
