"""
WeasyPrint PDF Generator Service

Professional PDF generation service that converts HTML templates to 
pixel-perfect PDFs using WeasyPrint, preserving all CSS styling, colors, 
layouts, and visual elements exactly as they appear in the browser.
"""

import logging
import re
import html
import json
from io import BytesIO
from typing import Dict, Any, List, Optional, Union
from weasyprint import HTML, CSS
from bs4 import BeautifulSoup
from markupsafe import Markup
from app.schemas import Agent, QuestionOut, AnswerType, ColumnDefinition
from app.services.template_security import restricted_weasyprint_url_fetcher

logger = logging.getLogger(__name__)


class WeasyPrintPDFGenerator:
    """Professional PDF generator using WeasyPrint for pixel-perfect HTML-to-PDF conversion"""

    def __init__(self):
        self.quote_counter = 1

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters"""
        return html.escape(str(text)) if text else ""

    def _render_string_answer(self, answer: str) -> str:
        """Render a string answer (default behavior), preserving newlines"""
        if not answer:
            return ""
        # Escape HTML and convert newlines to <br> tags for PDF rendering
        escaped = self._escape_html(answer)
        return Markup(escaped.replace('\n', '<br>'))

    def _render_list_answer(self, answer: Union[List[str], str]) -> str:
        """
        Render a list answer as HTML <li> elements.

        Returns <li>item1</li><li>item2</li>... (template provides <ul> wrapper)
        """
        # Handle case where LLM returned a string instead of array
        if isinstance(answer, str):
            try:
                parsed = json.loads(answer)
                if isinstance(parsed, list):
                    answer = parsed
                else:
                    # Not a list, wrap as single item
                    return f"<li>{self._escape_html(answer)}</li>"
            except json.JSONDecodeError:
                # Fallback: treat as single item
                return f"<li>{self._escape_html(answer)}</li>"

        if not answer or not isinstance(answer, list):
            return "<li>No items found</li>"

        # Render each item as <li>
        html_items = []
        for item in answer:
            safe_item = self._escape_html(str(item))
            html_items.append(f"<li>{safe_item}</li>")

        return "\n    ".join(html_items)

    def _render_table_answer(self, answer: Union[List[Dict], str],
                              columns: List[ColumnDefinition]) -> str:
        """
        Render a table answer as HTML <thead> and <tbody>.

        Returns complete table inner content:
        <thead><tr><th>Header1</th>...</tr></thead>
        <tbody><tr><td>value1</td>...</tr>...</tbody>
        """
        # Handle case where LLM returned a string instead of array
        if isinstance(answer, str):
            try:
                parsed = json.loads(answer)
                if isinstance(parsed, list):
                    answer = parsed
                else:
                    return self._render_table_error("Invalid table data format")
            except json.JSONDecodeError:
                return self._render_table_error("Failed to parse table data")

        if not answer or not isinstance(answer, list):
            return self._render_table_error("No table data found")

        if not columns:
            return self._render_table_error("Table columns not defined")

        # Build thead
        header_cells = "".join([
            f"<th>{self._escape_html(col.header)}</th>"
            for col in columns
        ])
        thead = f"<thead>\n      <tr>\n        {header_cells}\n      </tr>\n    </thead>"

        # Build tbody
        rows = []
        for row_data in answer:
            if not isinstance(row_data, dict):
                continue

            cells = []
            for col in columns:
                value = row_data.get(col.key, "")
                safe_value = self._escape_html(str(value)) if value else ""
                cells.append(f"<td>{safe_value}</td>")

            rows.append(f"<tr>\n        {''.join(cells)}\n      </tr>")

        tbody_content = "\n      ".join(rows) if rows else "<tr><td colspan=\"{}\">No data</td></tr>".format(len(columns))
        tbody = f"<tbody>\n      {tbody_content}\n    </tbody>"

        return f"{thead}\n    {tbody}"

    def _render_table_error(self, message: str) -> str:
        """Render error message for failed table parsing"""
        safe_message = self._escape_html(message)
        return f"<thead><tr><th>Error</th></tr></thead><tbody><tr><td>{safe_message}</td></tr></tbody>"

    def _render_answer(self, answer_data: Dict[str, Any],
                       question: Optional[QuestionOut]) -> str:
        """
        Route to appropriate renderer based on answer_type.

        Args:
            answer_data: The answer data from report_data['answers'][placeholder]
            question: The question definition with answer_type (None for backwards compat)

        Returns:
            HTML string for the answer
        """
        answer = answer_data.get("answer", "")

        # Default to string rendering if no question provided (backwards compatibility)
        if question is None:
            return self._render_string_answer(str(answer) if answer else "")

        if question.answer_type == AnswerType.LIST:
            return self._render_list_answer(answer)

        elif question.answer_type == AnswerType.TABLE:
            return self._render_table_answer(answer, question.columns or [])

        else:  # STRING (default)
            return self._render_string_answer(str(answer) if answer else "")

    def generate_pdf_report(self, agent: Agent, report_data: Dict[str, Any],
                          with_references: bool = False) -> bytes:
        """
        Generate pixel-perfect PDF report from HTML template

        Args:
            agent: Agent configuration with HTML template and CSS
            report_data: Report data with answers and quotes
            with_references: Whether to include reference section

        Returns:
            PDF content as bytes
        """
        try:
            # Reset quote counter for this document
            self.quote_counter = 1

            # Populate HTML template with answers and references
            # Pass questions for answer_type-aware rendering
            populated_html = self._populate_html_template(
                agent.reportTemplate,
                report_data,
                with_references,
                questions=agent.questions
            )

            # Add reference section if requested
            if with_references:
                populated_html = self._add_reference_section(populated_html, report_data)

            # Convert TinyMCE pagebreak comments to styled elements
            populated_html = self._convert_pagebreak_comments(populated_html)

            # Inject CSS into HTML for PDF rendering
            populated_html = self._inject_css(populated_html, agent)

            pdf_bytes = HTML(
                string=populated_html,
                url_fetcher=restricted_weasyprint_url_fetcher,
            ).write_pdf(
                presentational_hints=True,  # Respect HTML styling
                optimize_images=True  # Optimize for smaller file size
            )
            
            logger.info(f"Successfully generated pixel-perfect PDF report for agent: {agent.name}")
            return pdf_bytes

        except Exception as e:
            logger.exception("Failed to generate PDF report")
            raise ValueError(f"PDF generation failed: {str(e)}")

    def _populate_html_template(self, template_html: str, report_data: Dict[str, Any],
                              with_references: bool,
                              questions: Optional[List[QuestionOut]] = None) -> str:
        """Populate HTML template with answers and proper reference formatting"""
        populated_html = template_html
        answers = report_data.get('answers', {})

        # Build question lookup by placeholder for answer_type info
        question_lookup: Dict[str, QuestionOut] = {}
        if questions:
            for q in questions:
                question_lookup[q.placeholder] = q

        # Reset quote counter
        self.quote_counter = 1

        # Replace placeholders with answers and references
        for placeholder, answer_data in answers.items():
            placeholder_pattern = f"{{{{{placeholder}}}}}"

            if placeholder_pattern in populated_html:
                # Get question definition for answer_type
                question = question_lookup.get(placeholder)

                # Render answer based on type
                answer_html = self._render_answer(answer_data, question)

                quotes = answer_data.get("quotes", [])

                # Only add reference superscripts for STRING answers
                # Tables and lists have their own quote handling via 'target' field
                should_add_refs = (
                    question is None or
                    question.answer_type == AnswerType.STRING
                )

                if quotes and answer_html and should_add_refs and with_references:
                    # Only add reference numbers when downloading WITH references
                    references = [f'[{self.quote_counter + i}]' for i in range(len(quotes))]
                    reference_text = ' '.join(references)
                    answer_with_refs = f"{answer_html} {reference_text}"
                else:
                    # No reference numbers when downloading WITHOUT references
                    answer_with_refs = answer_html

                populated_html = populated_html.replace(placeholder_pattern, answer_with_refs)
                self.quote_counter += len(quotes)

        return populated_html

    def _convert_pagebreak_comments(self, html_content: str) -> str:
        """
        Convert TinyMCE pagebreak HTML comments to styled div elements.

        TinyMCE's pagebreak plugin outputs <!-- pagebreak --> comments by default.
        This method converts them to <div class="mce-pagebreak"></div> elements
        that can be styled with CSS for proper page breaks in PDF output.

        Args:
            html_content: HTML string that may contain pagebreak comments

        Returns:
            HTML string with pagebreak comments converted to div elements
        """
        # TinyMCE default pagebreak format
        pagebreak_comment = '<!-- pagebreak -->'
        pagebreak_element = '<div class="mce-pagebreak"></div>'

        # Replace all pagebreak comments with styled elements
        converted = html_content.replace(pagebreak_comment, pagebreak_element)

        # Also handle variations (case-insensitive, with extra whitespace)
        converted = re.sub(
            r'<!--\s*pagebreak\s*-->',
            pagebreak_element,
            converted,
            flags=re.IGNORECASE
        )

        return converted

    def _add_reference_section(self, html_content: str, report_data: Dict[str, Any]) -> str:
        """Add professional reference section to HTML before PDF generation"""
        
        # Collect all quotes from answers
        reference_counter = 1
        references_html = []
        answers = report_data.get('answers', {})
        document_context = report_data.get('document_context', {})
        documents = document_context.get('documents', {})
        
        for answer_data in answers.values():
            quotes = answer_data.get('quotes', [])
            for quote in quotes:
                # Get document name using correct field mapping
                document_id = quote.get('document_id', '')
                document_name = 'Unknown Document'
                
                # Look up the actual filename from document context
                if document_id and document_id in documents:
                    document_name = documents[document_id].get('filename', 'Unknown Document')
                
                page_info = quote.get('page_range', 'Page N/A')
                quote_text = quote.get('text', '')
                
                # Create reference entry HTML
                reference_html = f'<div class="reference-item">'
                reference_html += f'<strong>[{reference_counter}]</strong> '
                reference_html += f'<strong>{document_name}</strong> - {page_info}'
                
                # Add quote text if available
                if quote_text:
                    quote_preview = quote_text[:200] + "..." if len(quote_text) > 200 else quote_text
                    reference_html += f'<br><em>"{quote_preview}"</em>'
                
                reference_html += '</div>'
                references_html.append(reference_html)
                reference_counter += 1
        
        # If no references found
        if not references_html:
            references_html.append('<div class="reference-item">No references available.</div>')
        
        # Create reference section HTML with styling
        reference_section = '''
        <div style="page-break-before: always; margin-top: 30px;">
            <h2 style="font-size: 16pt; margin-bottom: 20px; border-bottom: 2px solid #333; padding-bottom: 8px;">References</h2>
            <div class="references-container">
                ''' + '\n'.join(references_html) + '''
            </div>
        </div>
        
        <style>
            .reference-item {
                margin-bottom: 12px;
                padding: 8px 0;
                font-size: 10pt;
                line-height: 1.4;
            }
            .reference-item strong {
                color: #333;
            }
            .reference-item em {
                color: #666;
                font-style: italic;
                margin-left: 20px;
                display: block;
                margin-top: 4px;
            }
            .references-container {
                margin-top: 12px;
            }
        </style>
        '''
        
        # Insert reference section before closing body tag
        if '</body>' in html_content:
            html_content = html_content.replace('</body>', reference_section + '</body>')
        else:
            # Fallback: append to end of HTML
            html_content += reference_section
        
        return html_content

    def _inject_css(self, html_content: str, agent: Agent) -> str:
        """
        Inject CSS into HTML for PDF rendering.

        Extracts both body content AND embedded CSS from full HTML documents.
        Combines with essential page rules for consistent PDF output.

        Args:
            html_content: The populated HTML content (may be body fragment or full HTML doc)
            agent: Agent with CSS configuration

        Returns:
            Complete HTML document with CSS injected
        """
        from app.constants.default_template_css import DEFAULT_TEMPLATE_CSS

        # Essential PDF page rules (always applied first)
        base_css = """
/* Essential PDF page rules */
@page {
    size: letter;
    margin: 0.75in;
}

/* TinyMCE page breaks - multiple selectors for all variations */
.mce-pagebreak,
hr.mce-pagebreak,
div.mce-pagebreak,
[data-mce-type="pagebreak"] {
    page-break-after: always !important;
    break-after: page !important;
    display: block !important;
    height: 0 !important;
    border: none !important;
    margin: 0 !important;
    padding: 0 !important;
    visibility: hidden !important;
}

/* Generic page break class */
.page-break {
    page-break-after: always !important;
    break-after: page !important;
    display: block;
    height: 0;
}

/* Text flow rules */
p, li {
    orphans: 2;
    widows: 2;
}

/* Table flow rules - allow tables to split across pages but keep rows intact */
table {
    page-break-inside: auto;
}

tr {
    page-break-inside: avoid;
    page-break-after: auto;
}

thead {
    display: table-header-group;
}

tfoot {
    display: table-footer-group;
}

/* Preserve whitespace and newlines in content */
p, span, td, li {
    white-space: pre-wrap;
    word-wrap: break-word;
}
"""

        # Extract embedded CSS and body from full HTML documents
        template_css = ""
        body_content = html_content

        if '<html' in html_content.lower():
            # Use BeautifulSoup to parse HTML safely (avoids regex DoS vulnerabilities)
            soup = BeautifulSoup(html_content, 'html.parser')

            # Extract CSS from <style> tags
            style_tags = soup.find_all('style')
            if style_tags:
                template_css = '\n'.join(tag.string for tag in style_tags if tag.string)
                logger.info("Extracted embedded CSS from template HTML")

            # Extract body content
            body_tag = soup.find('body')
            if body_tag:
                # Get inner HTML of body tag
                body_content = ''.join(str(child) for child in body_tag.children).strip()
                logger.info("Extracted body content from full HTML document")

        # Determine content CSS:
        # 1. If agent has reportTemplateCss, use it (custom agents with separate CSS)
        # 2. Else if template has embedded CSS, use it (prebuilt agents)
        # 3. Else use DEFAULT_TEMPLATE_CSS (fallback)
        if hasattr(agent, 'reportTemplateCss') and agent.reportTemplateCss:
            content_css = agent.reportTemplateCss
            logger.info("Using custom CSS from agent.reportTemplateCss")
        elif template_css:
            content_css = template_css
            logger.info("Using embedded CSS from template HTML")
        else:
            content_css = DEFAULT_TEMPLATE_CSS
            logger.info("Using DEFAULT_TEMPLATE_CSS (fallback)")

        # Combine base rules + content CSS
        final_css = base_css + "\n" + content_css

        # Build clean HTML document with .report-html wrapper for CSS selector matching
        complete_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
{final_css}
    </style>
</head>
<body>
<div class="report-html">
{body_content}
</div>
</body>
</html>"""

        return complete_html


# Global WeasyPrint PDF generator instance
pdf_generator = WeasyPrintPDFGenerator()
